"""Best-of-N takes for risky chunks, picked by whisper (used by qc).

Why: on 1.7B the stress/accent of a short phrase ("Глава тринадцатая.",
"Шаг второй.") and the odd garbled word ("тебья") are seed luck. Instead of a
human doing redo/accept for each, qc renders a few extra takes of exactly those
chunks and keeps the one whisper understands best.

Which chunks (config ``qc.takes``; absent or count ≤ 1 → off):
  * short: ``len(text) <= short_chars`` — headings, step labels;
  * unsure: some word longer than 4 letters has whisper probability
    ``< low_conf`` (garbled word);
  * clipped: the model's own output hit full scale (``peak >= clip_peak``) —
    the waveform was cut inside the model, mastering cannot undo it.
Locked chunks (accepted by ear) are never touched.

Takes live in ``<section>/takes/<id>__<hash12>/<seed>.wav``; the chunk's
current take is copied there before it is replaced, so nothing is ever
deleted and every take can be listened to. The chosen take's seed goes to the
manifest (``seed``); the chunk hash does not change, so no cache is reset.
Resumable: existing take files are reused, ``takes`` in the row counts them.

Pure helpers only — rendering/transcription is orchestrated by qc.run.
"""
from __future__ import annotations

from pathlib import Path

TAKE_STEP = 7919          # seed spacing; far from qc retries (+1) and pron-test (1009)
LONG_WORD_LEN = 4         # matches qc.SHORT_WORD_LEN: shorter words are routinely "unsure"


def settings(config: dict) -> dict | None:
    t = (config.get("qc") or {}).get("takes") or {}
    count = int(t.get("count", 1))
    if count <= 1:
        return None
    return {"count": count,
            "short_chars": int(t.get("short_chars", 40)),
            "low_conf": float(t.get("low_conf", 0.15)),
            "clip_peak": float(t.get("clip_peak", 0.999))}


def wav_peak(path) -> float:
    """Absolute sample peak of a (FLOAT) chunk wav."""
    import numpy as np
    import soundfile as sf
    data, _sr = sf.read(str(path), dtype="float32")
    return round(float(np.max(np.abs(data))), 4) if len(data) else 0.0


def word_stats(words: list[dict], norm) -> tuple[float, float]:
    """(min probability over words longer than 4 letters, mean over all words).
    ``norm`` maps a word to its normalized letters (qc._norm_word)."""
    ps = [w["p"] for w in words if norm(w["w"])]
    longs = [w["p"] for w in words if len(norm(w["w"])) > LONG_WORD_LEN]
    return (round(min(longs), 3) if longs else 1.0,
            round(sum(ps) / len(ps), 3) if ps else 0.0)


def reason(row: dict, s: dict) -> str | None:
    """Why this chunk deserves extra takes: "short" | "unsure" | "clipped" | None."""
    if row.get("locked") or row.get("status") != "done":
        return None
    if int(row.get("takes", 1)) >= s["count"]:
        return None
    if len(row.get("text", "")) <= s["short_chars"]:
        return "short"
    if float(row.get("min_p", 1.0)) < s["low_conf"]:
        return "unsure"
    if float(row.get("peak", 0.0)) >= s.get("clip_peak", 0.999):
        return "clipped"
    return None


def take_seeds(row: dict, s: dict) -> list[int]:
    """Seeds of the extra takes, fixed by ``take_base`` (the seed of the take
    qc started from) so a re-run asks for the same files."""
    base = int(row["take_base"])
    return [base + TAKE_STEP * k for k in range(1, s["count"])]


def take_dir(sec_dir: Path, row: dict) -> Path:
    return sec_dir / "takes" / f"{row['id']}__{row['hash'][:12]}"


CLIP_PEAK = 0.999


def score(m: dict, threshold: float, clip_peak: float = CLIP_PEAK) -> tuple:
    """Lower is better: passes CER, then not clipped, fewer unsure words, lower
    CER, higher worst-word probability, higher mean probability."""
    unsure = sum(1 for f in m.get("flag_words") or [] if f[3] == "conf")
    return (m["cer"] > threshold, float(m.get("peak", 0.0)) >= clip_peak, unsure,
            round(m["cer"], 3), -float(m.get("min_p", 1.0)), -float(m.get("mean_p", 0.0)))
