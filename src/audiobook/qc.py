"""QC stage: transcribe each rendered chunk with faster-whisper ("small",
CPU/int8), compare the transcript to the chunk's TEXT via CER on normalized
strings, re-synthesize failures with a new seed, and flag duration outliers.

Only one model is held in memory at a time: whisper is loaded for a transcribe
pass and released before the Qwen worker is spawned for a re-synth pass, and
vice versa (the machine is memory-bound).
"""
from __future__ import annotations

import gc
import json
import logging
import re
import statistics
import unicodedata
from pathlib import Path

from audiobook import paths

log = logging.getLogger(__name__)

_SR = 24000
_WHISPER_DIR = paths.MODELS / "whisper" / "small"

# Combining stress marks (acute/grave, both spacing-clones) and the RUAccent
# "+" marker. Stripped so an accented reference compares equal to a plain
# transcript. Note: we do NOT blanket-strip all combining marks (that would fold
# й→и via its breve); only these explicit stress marks.
_STRESS_MARKS = {0x0300, 0x0301, 0x0340, 0x0341}
_STRESS_TABLE = {c: None for c in _STRESS_MARKS}
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_DIGITS = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")


def _digits_to_words(m: re.Match) -> str:
    from num2words import num2words
    try:
        return " " + num2words(int(m.group()), lang="ru") + " "
    except Exception:
        return " "


def normalize_for_cer(text: str) -> str:
    """Normalize a string for CER comparison. Applied to BOTH the chunk text and
    the transcript so representation differences never inflate the distance:
    strip stress marks, ё→е, lowercase, numbers to one (word) form, drop
    punctuation, collapse whitespace.

    Numbers: the chunk text is already word-form (upstream normalization expands
    digits), but whisper writes digits ("13 глава", "50%"). Converting digit runs
    to Russian cardinal words — and "%" to "процентов" — puts both sides in word
    space so the representation alone never fails a chunk. A residual ordinal/case
    mismatch (тринадцать vs тринадцатая) is a few characters, not the whole token.
    ponytail: cardinal-only; ordinals left to their small CER residue."""
    t = unicodedata.normalize("NFC", text)
    t = t.translate(_STRESS_TABLE)
    t = t.replace("+", "")
    t = t.replace("ё", "е").replace("Ё", "Е")
    t = t.lower()
    t = t.replace("%", " процентов ")
    t = _DIGITS.sub(_digits_to_words, t)   # numbers to one (word) form
    t = _NON_WORD.sub(" ", t)              # drop punctuation
    t = t.replace("_", " ")
    return _SPACES.sub(" ", t).strip()


def _levenshtein(a: str, b: str) -> int:
    """Edit distance. Chunk texts are short (<~300 chars), so plain O(n·m) DP
    with a rolling row is fine — no dependency needed."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _stem_eq(a: str, b: str) -> bool:
    """Same numeral up to its ending: тринадцатый ~ тринадцатая, первый ~ первой."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= max(3, min(len(a), len(b)) - 3)


def _numbers_like_ref(hyp_text: str, ref_tokens: list[str]) -> str:
    """Write each digit run of the transcript the way the reference says it.

    Whisper writes "Глава 13", the book says "Глава тринадцатая". Cardinal
    expansion alone leaves "тринадцать" vs "тринадцатая" — 12% CER on a short
    heading, a false QC failure (ch13 chunk 0001). For each number try its
    cardinal and ordinal words; if they match reference tokens up to the
    ending, use the reference tokens verbatim. A genuinely different number
    (13 vs "четырнадцатая") does not match and still counts as an error."""
    from num2words import num2words

    def repl(m: re.Match) -> str:
        n = int(m.group())
        forms = []
        for kind in ("cardinal", "ordinal"):
            try:
                forms.append(num2words(n, lang="ru", to=kind).split())
            except Exception:
                pass
        for fw in forms:
            for i in range(len(ref_tokens) - len(fw) + 1):
                if all(_stem_eq(a, b) for a, b in zip(fw, ref_tokens[i:i + len(fw)])):
                    return " " + " ".join(ref_tokens[i:i + len(fw)]) + " "
        return " " + " ".join(forms[0]) + " " if forms else " "

    return _DIGITS.sub(repl, hyp_text)


def cer(ref_text: str, hyp_text: str) -> float:
    """Character error rate of a transcript against reference text, both put
    through normalize_for_cer first. 0.0 on two empty/identical normalizations.
    Numbers in the transcript are written as the reference words them."""
    ref = normalize_for_cer(ref_text)
    hyp = normalize_for_cer(_numbers_like_ref(hyp_text, ref.split()))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


# ── model + orchestration ──────────────────────────────────────────────────────

def load_whisper():
    """faster-whisper 'small', CPU/int8, from the local dir (offline)."""
    from faster_whisper import WhisperModel
    if not _WHISPER_DIR.exists():
        raise SystemExit(
            f"whisper weights missing: {_WHISPER_DIR}\n"
            "Download once with scripts described in README (then HF_HUB_OFFLINE=1)."
        )
    return WhisperModel(str(_WHISPER_DIR), device="cpu", compute_type="int8")


def transcribe(model, wav_path: Path) -> str:
    segments, _info = model.transcribe(str(wav_path), language="ru", beam_size=5)
    return " ".join(s.text.strip() for s in segments).strip()


def _release(model) -> None:
    del model
    gc.collect()


def qc_status(row: dict, threshold: float) -> str:
    """A locked chunk was accepted by ear (`accept`): QC records its CER but never
    queues it for re-synth — that would overwrite the human choice."""
    if row.get("locked"):
        return "done"
    return "qc_fail" if row["cer"] > threshold else "done"


def _ms_per_char(row: dict) -> float:
    n = max(1, len(row.get("text", "")))
    return round((row.get("duration_ms") or 0) / n, 1)


def run(config: dict, section: str | None = None) -> int:
    if not section:
        raise SystemExit("qc: --section обязателен")
    from audiobook.synth import _read_manifest, _write_manifest

    sec_dir = paths.OUT / "sections" / section
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"нет манифеста для секции {section}: {sec_dir}")
    chunks_dir = sec_dir / "chunks"
    rows = _read_manifest(manifest_path)
    threshold = float(config["qc"]["cer_threshold"])
    max_retries = int(config["qc"]["max_retries"])

    def has_wav(r: dict) -> bool:
        return (chunks_dir / f"{r['id']}.wav").exists()

    candidates = [r for r in rows
                  if has_wav(r) and r.get("status") in ("done", "qc_fail", "manual")]
    if not candidates:
        raise SystemExit(f"нет отрендеренных чанков для QC в {section}")

    # Phase 1 — transcribe every rendered chunk, CER vs the chunk TEXT (not the
    # pronounce respelling), store metrics. Whisper is the only model loaded here.
    wm = load_whisper()
    try:
        for r in candidates:
            txt = transcribe(wm, chunks_dir / f"{r['id']}.wav")
            r["transcript"] = txt
            r["cer"] = round(cer(r["text"], txt), 4)
            r["ms_per_char"] = _ms_per_char(r)
            r["status"] = qc_status(r, threshold)
    finally:
        _release(wm)
    _write_manifest(manifest_path, rows)

    # Duration outliers: ms/char > 1.8× section median — a cheap proxy for
    # runaways/drawn-out speech that CER alone can miss. A flag, not a status.
    rates = [r["ms_per_char"] for r in candidates if r.get("ms_per_char")]
    med = statistics.median(rates) if rates else 0.0
    for r in candidates:
        r["suspect"] = bool(med and r.get("ms_per_char", 0) > 1.8 * med)
    _write_manifest(manifest_path, rows)

    # Phase 2 — retry rounds. Each round: re-synth the CER failures with the next
    # seed (Qwen worker), then re-transcribe them (whisper). Models never overlap.
    from audiobook.pronounce import load_table
    from audiobook.synth import (
        _SAMPLE_RATE, prepare_synth_text, seed_for_chunk, worker_config,
    )
    from audiobook.worker import TimeoutSynth
    import soundfile as sf

    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    rcfg = config.get("render", {})
    wcfg = worker_config(config)  # variant + its latents, same as render
    timeout_s = rcfg.get("chunk_timeout_s", 120)

    recovered = 0
    for _tri in range(1, max_retries + 1):
        fails = [r for r in rows if r.get("status") == "qc_fail"]
        if not fails:
            break
        # Re-synth pass (Qwen only).
        with TimeoutSynth(wcfg, timeout_s) as eng:
            for r in fails:
                base = r.get("seed") or seed_for_chunk(r["hash"])
                new_seed = base + 1
                # Same pad→respell→sentinel as render, so a re-synth of a short
                # chunk keeps its lead-in (and gets the carrier trimmed off).
                synth_text, phrase = prepare_synth_text(r["text"], config, table, sentinel)
                wav = eng.synth(synth_text, new_seed, **({"leadin": phrase} if phrase else {}))
                if wav is None:  # capped/timeout — leave qc_fail, becomes manual
                    log.warning("qc re-synth failed (cap/timeout) chunk %s", r["id"])
                    continue
                wav_path = chunks_dir / f"{r['id']}.wav"
                tmp = wav_path.parent / (wav_path.name + ".part")
                sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="FLOAT", format="WAV")  # float: no clipping at write
                tmp.replace(wav_path)
                r["seed"] = new_seed
                r["duration_ms"] = round(len(wav) / _SAMPLE_RATE * 1000)
                r["ms_per_char"] = _ms_per_char(r)
        _write_manifest(manifest_path, rows)
        # Re-transcribe pass (whisper only).
        wm = load_whisper()
        try:
            for r in fails:
                txt = transcribe(wm, chunks_dir / f"{r['id']}.wav")
                r["transcript"] = txt
                r["cer"] = round(cer(r["text"], txt), 4)
                if r["cer"] <= threshold:
                    r["status"] = "done"
                    recovered += 1
        finally:
            _release(wm)
        _write_manifest(manifest_path, rows)

    # Exhausted retries → manual queue.
    manual = 0
    for r in rows:
        if r.get("status") == "qc_fail":
            r["status"] = "manual"
            manual += 1
    _write_manifest(manifest_path, rows)

    suspects = [r["id"] for r in candidates if r.get("suspect")]
    print(f"section={section}  chunks={len(candidates)}  "
          f"recovered={recovered}  manual={manual}  suspect={len(suspects)}")
    for r in rows:
        if r.get("status") == "manual":
            print(f"  MANUAL {r['id']} cer={r.get('cer')}: {r['text']!r}")
    if suspects:
        print(f"  suspect (ms/char > 1.8× median): {suspects}")
    return 0
