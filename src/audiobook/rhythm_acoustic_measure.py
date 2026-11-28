"""Read-only local rhythm measurement on existing, exact-text paired recordings.

ASR word gaps are estimates, not forced-aligned pauses. No TTS, ASR inference,
audio edits, universal tempo thresholds or release decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics

from audiobook.stress_acoustic_calibration import word_windows
from audiobook.stress_consensus import WORD, VOWELS
from audiobook.rhythm_syntax import protected_commas

POLICY = "rhythm-paired-measurement-v1"
HEX = re.compile(r"[0-9a-f]{64}")
PUNCT = frozenset(",;:.!?…")


def frozen(path: Path, expected: str) -> bytes:
    if not HEX.fullmatch(expected) or path.is_symlink() or not path.is_file():
        raise ValueError("INVALID_FROZEN_FILE")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("DIGEST_MISMATCH:" + path.name)
    return data


def measure(text: str, words: list[dict], duration: float) -> dict:
    """All word identities/confidences must align; no first-match fallback."""
    matches = list(WORD.finditer(text))
    if len(matches) < 3:
        return dict(status="uncertain", reason="short_text")
    # Reject compounds, unexpanded numerals, abbreviations/foreign text and
    # ambiguous punctuation rather than claim timing for partial words.
    residual = WORD.sub("", text)
    if any(not c.isspace() and c not in ',;:.!?…«»“”"()[]' for c in residual):
        return dict(status="uncertain", reason="unsupported_text")
    if any(not any(v.lower() in VOWELS for v in m.group()) for m in matches):
        # Russian single-consonant prepositions are legitimate words.
        if any(m.group().lower() not in ("в", "к", "с")
               for m in matches if not any(v.lower() in VOWELS for v in m.group())):
            return dict(status="uncertain", reason="unsupported_abbreviation")
    windows = word_windows(text, words, duration)
    if windows is None or len(windows) != len(matches):
        return dict(status="uncertain", reason="lexical_or_timing_alignment")
    first, last = windows[1][0], windows[len(matches)][1]
    span = last-first
    syllables = sum(c.lower() in VOWELS for m in matches for c in m.group())
    word_time = sum(b-a for a,b in windows.values())
    if not 0 < word_time <= span + 1e-8:
        return dict(status="uncertain", reason="invalid_word_span")
    protected = protected_commas(text)
    gaps = []
    for i, (left,right) in enumerate(zip(matches, matches[1:]), 1):
        segment = text[left.end():right.start()]
        offsets = [left.end()+j for j,c in enumerate(segment) if c in PUNCT]
        if len(offsets) == 1 and offsets[0] not in protected:
            off = offsets[0]
            category = "comma" if text[off] == "," else "sentence" if text[off] in ".!?…" else "clause"
        elif not offsets and segment.isspace():
            off, category = None, "plain"
        else:
            off, category = None, "ambiguous"
        gaps.append(dict(after_word=i, offset=off, category=category,
                         start_s=windows[i][1], end_s=windows[i+1][0],
                         gap_ms=1000*(windows[i+1][0]-windows[i][1])))
    # Articulation proxy excludes between-word intervals, not silence inside
    # ASR word spans. Orthographic vowel counts approximate syllables.
    return dict(status="measured", words=len(matches), syllable_proxy=syllables,
                duration_s=duration, span_s=span, word_span_s=word_time,
                leading_ms=1000*first, trailing_ms=1000*(duration-last),
                words_per_min=60*len(matches)/span,
                syllables_per_span_s=syllables/span,
                syllables_per_word_span_s=syllables/word_time,
                gaps=gaps)


def quiet_fraction(wave, sample_rate: int, start_s: float, end_s: float) -> float | None:
    """Relative low-energy fraction in an ASR gap, NOT a silence/VAD verdict.

    10ms RMS windows, threshold -35dB relative to recording 95th-percentile
    frame RMS. Return None for gaps shorter than one full frame.
    """
    import numpy as np
    x = np.asarray(wave, dtype=np.float64)
    if (x.ndim != 1 or type(sample_rate) is not int or sample_rate < 8000
            or not len(x) or not np.isfinite(x).all()
            or not 0 <= start_s <= end_s <= len(x)/sample_rate):
        raise ValueError("INVALID_AUDIO_OR_GAP")
    hop = sample_rate//100
    n = len(x)//hop
    if not n:
        return None
    rms = np.sqrt(np.mean(x[:n*hop].reshape(n,hop)**2, axis=1))
    reference = float(np.percentile(rms,95))
    if reference <= 1e-9:
        return None
    a = math.ceil(start_s*sample_rate/hop)
    b = min(n, math.floor(end_s*sample_rate/hop))
    if a >= b:
        return None
    return float(np.mean(rms[a:b] <= reference*10**(-35/20)))


def compare(reference: dict, candidate: dict) -> dict:
    if reference["status"] != "measured" or candidate["status"] != "measured":
        return dict(status="uncertain", reference=reference.get("reason"),
                    candidate=candidate.get("reason"))
    keys = ("after_word","offset","category")
    rg, cg = reference["gaps"],candidate["gaps"]
    if (reference["words"],reference["syllable_proxy"]) != (candidate["words"],candidate["syllable_proxy"]) or [
            tuple(g[k] for k in keys) for g in rg] != [tuple(g[k] for k in keys) for g in cg]:
        raise ValueError("PAIR_TEXT_BOUNDARY_MISMATCH")
    boundaries = [dict(after_word=r["after_word"],offset=r["offset"],
                       category=r["category"],reference_gap_ms=r["gap_ms"],
                       candidate_gap_ms=c["gap_ms"],delta_ms=c["gap_ms"]-r["gap_ms"],
                       reference_quiet_fraction=r.get("quiet_fraction"),
                       candidate_quiet_fraction=c.get("quiet_fraction"))
                  for r,c in zip(rg,cg)]
    summaries = {}
    for category in ("plain","comma","clause","sentence","ambiguous"):
        ds = [g["delta_ms"] for g in boundaries if g["category"] == category]
        summaries[category] = dict(count=len(ds), median_delta_ms=statistics.median(ds) if ds else None)
    return dict(status="measured", boundaries=boundaries, categories=summaries,
                rate_delta_pct=100*(candidate["words_per_min"]/reference["words_per_min"]-1),
                word_span_rate_delta_pct=100*(candidate["syllables_per_word_span_s"]/
                                              reference["syllables_per_word_span_s"]-1))


def evaluate(manifest_bytes: bytes, plan: dict, audio_root: Path) -> tuple[dict,list]:
    """Pair inventory binds exact manifest text, both WAVs and existing ASR."""
    import numpy as np
    import soundfile as sf
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if plan["policy"] != POLICY or plan["manifest_sha256"] != digest:
        raise ValueError("PAIR_MANIFEST_MISMATCH")
    rows = [json.loads(l) for l in manifest_bytes.splitlines() if l.strip()]
    idx = {r["id"]:r for r in rows}
    pairs = plan["pairs"]
    if len(idx) != len(rows) or not 1 <= len(pairs) <= 64 or len({p["id"] for p in pairs}) != len(pairs):
        raise ValueError("PAIR_INVENTORY_MISMATCH")
    results = []
    snapshots = {}
    for p in pairs:
        cid = p["id"]
        row = idx[cid]
        if (row["hash"] != p["hash"] or row.get("status") != "done"
                or p.get("reference_text_independently_verified") is not True):
            raise ValueError("PAIR_SOURCE_IDENTITY_MISMATCH")
        arm_results = {}
        for arm in ("reference","candidate"):
            a = p[arm]
            name = a["wav"]
            if not re.fullmatch(r"[a-zA-Z0-9_-]+\.wav",name):
                raise ValueError("UNSAFE_WAV_NAME")
            path = audio_root/name
            if path in snapshots:
                raise ValueError("DUPLICATE_AUDIO_PATH")
            data = frozen(path,a["wav_sha256"])
            snapshots[path] = a["wav_sha256"]
            if a["asr"]["wav_sha256"] != a["wav_sha256"]:
                raise ValueError("ASR_AUDIO_MISMATCH")
            wav,sr = sf.read(io.BytesIO(data),dtype="float32")
            if wav.ndim != 1 or sr < 8000 or not 0 < len(wav) <= 60*sr or not np.isfinite(wav).all() or not np.any(wav):
                raise ValueError("INVALID_AUDIO")
            m = measure(row["text"],a["asr"]["words"],len(wav)/sr)
            for g in m.get("gaps",[]):
                g["quiet_fraction"] = quiet_fraction(wav,sr,g["start_s"],g["end_s"])
            arm_results[arm] = m
        if p["reference"]["wav_sha256"] == p["candidate"]["wav_sha256"]:
            raise ValueError("IDENTICAL_PAIR_AUDIO")
        results.append(dict(id=cid,hash=row["hash"],**arm_results,
                            comparison=compare(arm_results["reference"],arm_results["candidate"])))
    for path,d in snapshots.items():
        frozen(path,d)
    measured = [r["comparison"] for r in results if r["comparison"]["status"]=="measured"]
    summary = dict(policy=POLICY,manifest_sha256=digest,pairs=len(results),
                   measured=len(measured),uncertain=len(results)-len(measured),
                   median_rate_delta_pct=statistics.median(m["rate_delta_pct"] for m in measured) if measured else None,
                   release_ready=False)
    return summary,results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","plan","audio-root","out"):
        p.add_argument("--"+name,type=Path,required=True)
    for name in ("manifest","plan"):
        p.add_argument("--"+name+"-sha256",required=True)
    a = p.parse_args()
    from audiobook import paths
    out = a.out.resolve()
    if out.exists() or any(out.is_relative_to(r) for r in
                           (paths.ROOT.resolve(), paths.OUT.resolve(), a.audio_root.resolve())):
        raise ValueError("NEW_ISOLATED_OUTPUT_REQUIRED")
    manifest = frozen(a.manifest,a.manifest_sha256)
    plan = frozen(a.plan,a.plan_sha256)
    summary,results = evaluate(manifest,json.loads(plan),a.audio_root)
    if frozen(a.manifest,a.manifest_sha256)!=manifest or frozen(a.plan,a.plan_sha256)!=plan:
        raise ValueError("INPUTS_CHANGED")
    out.mkdir(mode=0o700,exist_ok=False)
    (out/"rhythm_PRIVATE.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
