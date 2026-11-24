"""Offline, occurrence-bound acoustic stress calibration; never release approval."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from audiobook.stress_consensus import WORD, VOWELS, fold
from audiobook.stress_coverage import build_ledger


def word_windows(text: str, heard: list[dict], duration: float) -> dict[int, tuple[float, float]] | None:
    """Conservative full-sequence lexical match, including repeated words.

    ASR boundaries are estimates, not forced phoneme alignment.
    """
    if not math.isfinite(duration) or duration <= 0:
        return None
    source = list(WORD.finditer(text))
    # No silent normalization of numbers, symbols, foreign scripts, etc.
    residual = WORD.sub("", text)
    if any(c.isalnum() or c.isalpha() or c in "+%$€₽\u0301" for c in residual):
        return None
    if len(source) != len(heard):
        return None
    windows = {}
    prev = 0.0
    for ordinal, (match, item) in enumerate(zip(source, heard), 1):
        raw = item["w"].strip().strip('.,!?;:…«»“”"()[]')
        if WORD.fullmatch(raw) is None or fold(raw) != fold(match.group()):
            return None
        start, end, confidence = (item[k] for k in ("s", "e", "p"))
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end, confidence)):
            return None
        if not (prev <= start < end <= duration and 0 <= confidence <= 1):
            return None
        prev = end
        if confidence >= 0.5:
            windows[ordinal] = (start, end)
    return windows


def expected_form(word: str, index: int) -> str:
    if (type(index) is not int or not 0 <= index < len(word)
            or word[index].lower() not in VOWELS or WORD.fullmatch(word) is None):
        raise ValueError("INVALID_EXPECTED_STRESS")
    plain = word.lower()
    if any(ch == "ё" and i != index for i, ch in enumerate(plain)):
        raise ValueError("CONFLICTING_YO")
    return plain[:index] + plain[index].upper() + plain[index + 1:]


def validate_controls(rows: list[dict], findings: list[dict], controls: list[dict]) -> dict:
    build_ledger(rows, findings)
    by_key = {(f["id"], f["ordinal"]): f for f in findings}
    if not controls:
        raise ValueError("NO_CONTROLS")
    result = {}
    for c in controls:
        key = (c["id"], c["ordinal"])
        if type(c["ordinal"]) is not int or key in result or key not in by_key:
            raise ValueError("CONTROL_IDENTITY")
        f = by_key[key]
        if (c["hash"], c["start"], c["end"], c["word"]) != (f["hash"], f["start"], f["end"], f["word"]):
            raise ValueError("CONTROL_IDENTITY")
        if c["gold"] not in ("correct", "wrong_stress", "lexical_error"):
            raise ValueError("UNKNOWN_GOLD")
        if re.fullmatch("[0-9a-f]{64}", c["wav_sha256"]) is None:
            raise ValueError("INVALID_AUDIO_DIGEST")
        if c["gold"] != "lexical_error":
            expected_form(c["word"], c["expected_index"])
        result[key] = c
    return result


def summarize(results: list[dict]) -> dict:
    counts = Counter((r["gold"], r["signal"]) for r in results)
    errors = sum(r["gold"] == "wrong_stress" for r in results)
    correct = sum(r["gold"] == "correct" for r in results)
    return {
        "controls": len(results),
        "known_stress_errors": errors,
        "known_correct": correct,
        "stress_errors_flagged": counts["wrong_stress", "stress_suspect"],
        "stress_errors_missed": counts["wrong_stress", "not_flagged"],
        "correct_false_flags": counts["correct", "stress_suspect"],
        "outcomes": {a + ":" + b: n for (a, b), n in sorted(counts.items())},
        "release_ready": False,
        "limitation": "Experimental heuristic on existing human-labeled controls; not a validated detector.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--audit-dir", type=Path, required=True)
    p.add_argument("--chunks-dir", type=Path, required=True)
    p.add_argument("--controls", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    manifest_bytes = a.manifest.read_bytes()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    meta = json.loads((a.audit_dir / "summary.json").read_text(encoding="utf-8"))
    if meta.get("source_kind") != "chunk_manifest" or meta.get("manifest_sha256") != digest:
        raise ValueError("STALE_AUDIT")
    rows = [json.loads(line) for line in manifest_bytes.decode("utf-8").splitlines() if line.strip()]
    findings_bytes = (a.audit_dir / "occurrences.jsonl").read_bytes()
    findings = [json.loads(line) for line in findings_bytes.decode("utf-8").splitlines() if line.strip()]
    controls_bytes = a.controls.read_bytes()
    controls = validate_controls(rows, findings, json.loads(controls_bytes))
    row_ids = {r["id"]: r for r in rows}
    audio_bytes = {}
    for c in controls.values():
        row_id = c["id"]
        if re.fullmatch("[0-9]+", row_id) is None or row_ids[row_id].get("status") != "done":
            raise ValueError("INVALID_AUDIO_ROW")
        if row_id not in audio_bytes:
            audio_bytes[row_id] = (a.chunks_dir / (row_id + ".wav")).read_bytes()
        if hashlib.sha256(audio_bytes[row_id]).hexdigest() != c["wav_sha256"]:
            raise ValueError("AUDIO_DIGEST_MISMATCH")
    import soundfile as sf
    from audiobook.phoneme_check import PhonemeModel, _to16k, analyze_iyU
    from audiobook.qc import load_whisper, transcribe_words

    # All inference uses local weights and private files. The operator must
    # additionally disable networking for the run.
    pm, wm = PhonemeModel(), load_whisper()
    results = []
    for row_id, data in audio_bytes.items():
        audio, sr = sf.read(io.BytesIO(data), dtype="float32")
        if audio.ndim != 1 or sr <= 0:
            raise ValueError("UNSUPPORTED_AUDIO")
        path = a.chunks_dir / (row_id + ".wav")
        if path.read_bytes() != data:
            raise ValueError("AUDIO_CHANGED")
        _text, heard = transcribe_words(wm, path)
        if path.read_bytes() != data:
            raise ValueError("AUDIO_CHANGED")
        windows = word_windows(row_ids[row_id]["text"], heard, len(audio) / sr)
        for (cid, ordinal), c in controls.items():
            if cid != row_id:
                continue
            r = dict(c, signal="uncertain", detail="lexical_control_not_stress")
            if windows is None:
                r.update(detail="lexical_or_timing_mismatch")
            elif c["gold"] != "lexical_error" and ordinal in windows:
                start, end = windows[ordinal]
                clip = audio[int(start * sr):int(end * sr)]
                if len(clip) >= sr * 0.1:
                    tokens, frames, rms = pm.phonemes_scored(_to16k(clip, sr))
                    result = analyze_iyU(expected_form(c["word"], c["expected_index"]), tokens, frames, rms)
                    verdict = result["verdict"]
                    signal = ("stress_suspect" if verdict in ("STRESS?", "bad")
                              else "not_flagged" if verdict == "ok" else "uncertain")
                    r.update(signal=signal, detail=verdict, features=result,
                             asr_start=start, asr_end=end)
                else:
                    r.update(detail="short_window")
            elif c["gold"] != "lexical_error":
                r.update(detail="low_asr_confidence")
            results.append(r)
    if a.manifest.read_bytes() != manifest_bytes or a.controls.read_bytes() != controls_bytes or (a.audit_dir / "occurrences.jsonl").read_bytes() != findings_bytes:
        raise ValueError("EVIDENCE_CHANGED")
    summary = summarize(results)
    summary.update(manifest_sha256=digest, audit_sha256=hashlib.sha256(findings_bytes).hexdigest(),
                   controls_sha256=hashlib.sha256(controls_bytes).hexdigest())
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (a.out / "controls_PRIVATE.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
