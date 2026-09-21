"""Assemble stage: trim edge silence -> pause by pause_after_ms -> 20 ms
crossfade at each join -> section.wav. Reads the section manifest; the chunk wavs
must already be synthesised (status 'done'). Writes out/sections/<sec>/section.wav.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from audiobook import paths

_SR = 24_000


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _trim_silence(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """Trim leading/trailing 10 ms frames below the amplitude threshold."""
    frame = int(_SR * 0.010)
    if len(audio) < frame:
        return audio
    n = len(audio) // frame
    amps = np.abs(audio[: n * frame].reshape(n, frame)).max(axis=1)
    loud = np.where(amps > threshold)[0]
    if len(loud) == 0:
        return audio
    return audio[loud[0] * frame: (loud[-1] + 1) * frame]


def _fade(clip: np.ndarray, samples: int, leading: bool, trailing: bool) -> np.ndarray:
    c = clip.copy()
    f = min(samples, len(c) // 4)
    if f <= 0:
        return c
    if leading:
        c[:f] *= np.linspace(0.0, 1.0, f, dtype=np.float32)
    if trailing:
        c[-f:] *= np.linspace(1.0, 0.0, f, dtype=np.float32)
    return c


def assemble_section(sec_dir: Path, config: dict) -> tuple[Path, list[dict]]:
    rows = _read_manifest(sec_dir / "manifest.jsonl")
    pending = [r["id"] for r in rows if r.get("status") != "done"]
    if pending:
        raise SystemExit(f"секция не досинтезирована, pending: {pending}")

    fade_samples = int(_SR * config["pauses_ms"]["crossfade"] / 1000)
    chunks_dir = sec_dir / "chunks"

    parts: list[np.ndarray] = []
    stats: list[dict] = []
    for i, row in enumerate(rows):
        raw, sr = sf.read(str(chunks_dir / f"{row['id']}.wav"), dtype="float32")
        assert sr == _SR, f"unexpected sr {sr} in {row['id']}"
        trimmed = _trim_silence(raw)
        last = i == len(rows) - 1
        parts.append(_fade(trimmed, fade_samples, leading=(i > 0), trailing=(not last)))
        if not last:  # inter-chunk pause; final trailing pause dropped for a clean tail
            parts.append(np.zeros(int(_SR * row["pause_after_ms"] / 1000), dtype=np.float32))
        stats.append({
            "id": row["id"], "chars": len(row["text"]),
            "raw_ms": round(len(raw) / _SR * 1000),
            "trimmed_ms": round(len(trimmed) / _SR * 1000),
            "peak": float(np.max(np.abs(raw))) if len(raw) else 0.0,
        })

    section = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    out = sec_dir / "section.wav"
    sf.write(str(out), section, _SR, subtype="PCM_16")
    return out, stats


def run(config: dict, section: str | None = None) -> int:
    if not section:
        raise SystemExit("assemble: --section обязателен")
    sec_dir = paths.OUT / "sections" / section
    out, stats = assemble_section(sec_dir, config)
    total_ms = sum(s["trimmed_ms"] for s in stats)
    peak = max((s["peak"] for s in stats), default=0.0)
    print(f"section={section}  chunks={len(stats)}  -> {out}")
    print(f"assembled audio (chunks, pre-pauses)={total_ms/1000:.1f}s  peak={peak:.3f}"
          f"{'  CLIPPING' if peak >= 1.0 else ''}")
    # flag chunks whose ms-per-char is an outlier (abnormal duration for length)
    speech = [s for s in stats if s["chars"] >= 20]
    if speech:
        mpc = [s["trimmed_ms"] / s["chars"] for s in speech]
        med = sorted(mpc)[len(mpc) // 2]
        for s, r in zip(speech, mpc):
            if med and (r > 1.8 * med or r < 0.5 * med):
                print(f"  ⚠ {s['id']}: {s['trimmed_ms']}ms / {s['chars']}ch = "
                      f"{r:.0f} ms/ch (median {med:.0f})")
    return 0
