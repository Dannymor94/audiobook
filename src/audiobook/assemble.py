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


def _trim_bounds(audio: np.ndarray, threshold: float = 0.01) -> tuple[int, int]:
    """[start, end) sample bounds after trimming leading/trailing 10 ms frames
    below the amplitude threshold."""
    frame = int(_SR * 0.010)
    if len(audio) < frame:
        return 0, len(audio)
    n = len(audio) // frame
    amps = np.abs(audio[: n * frame].reshape(n, frame)).max(axis=1)
    loud = np.where(amps > threshold)[0]
    if len(loud) == 0:
        return 0, len(audio)
    return int(loud[0] * frame), int((loud[-1] + 1) * frame)


def _trim_silence(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """Trim leading/trailing 10 ms frames below the amplitude threshold."""
    a, b = _trim_bounds(audio, threshold)
    return audio[a:b]


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


def preview_name(first: int | None) -> str:
    """Output stem: whole section → "section", first N chunks → "preview_firstN"
    (a separate file, so a preview never overwrites the full section)."""
    return "section" if first is None else f"preview_first{first}"


def assemble_section(sec_dir: Path, config: dict,
                     first: int | None = None) -> tuple[Path, list[dict]]:
    rows = _read_manifest(sec_dir / "manifest.jsonl")[:first]
    pending = [r["id"] for r in rows if r.get("status") != "done"]
    if pending:
        raise SystemExit(f"секция не досинтезирована, pending: {pending}")

    chunks_dir = sec_dir / "chunks"
    section, stats = join_chunks(rows, chunks_dir, config)
    out = sec_dir / f"{preview_name(first)}.wav"
    write_index(sec_dir / f"{preview_name(first)}.index.tsv", rows, stats)
    sf.write(str(out), section, _SR, subtype="FLOAT")  # float: no clipping before master
    return out, stats


INDEX_COLUMNS = ("id", "start_ms", "lead_ms", "hash16", "seed", "dur_ms")


def write_index(path: Path, rows: list[dict], stats: list[dict]) -> None:
    """<stem>.index.tsv: where each chunk sits in the section, plus the chunk's
    hash16 and seed — the audio identity suspects checks against the manifest
    (a qc re-take keeps the hash but changes the seed). Atomic write."""
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(INDEX_COLUMNS) + "\n")
        for row, st in zip(rows, stats):
            seed = row.get("seed_override") or row.get("seed") or ""
            f.write(f"{st['id']}\t{st['start_ms']}\t{st['lead_ms']}\t"
                    f"{str(row.get('hash', ''))[:16]}\t{seed}\t{st.get('trimmed_ms', '')}\n")
    tmp.replace(path)


def join_chunks(rows: list[dict], chunks_dir: Path,
                config: dict) -> tuple[np.ndarray, list[dict]]:
    """Trim edge silence of each <id>.wav, fade, insert pause_after_ms between
    chunks (the final trailing pause is dropped). Shared with ref_compare."""
    fade_samples = int(_SR * config.get("pauses_ms", {}).get("crossfade", 0) / 1000)
    parts: list[np.ndarray] = []
    stats: list[dict] = []
    pos = 0  # samples so far in the section
    for i, row in enumerate(rows):
        raw, sr = sf.read(str(chunks_dir / f"{row['id']}.wav"), dtype="float32")
        assert sr == _SR, f"unexpected sr {sr} in {row['id']}"
        a, b = _trim_bounds(raw)
        trimmed = raw[a:b]
        start_ms, lead_ms = round(pos / _SR * 1000), round(a / _SR * 1000)
        pos += len(trimmed) + (0 if i == len(rows) - 1
                               else int(_SR * row["pause_after_ms"] / 1000))
        last = i == len(rows) - 1
        parts.append(_fade(trimmed, fade_samples, leading=(i > 0), trailing=(not last)))
        if not last:  # inter-chunk pause; final trailing pause dropped for a clean tail
            parts.append(np.zeros(int(_SR * row["pause_after_ms"] / 1000), dtype=np.float32))
        stats.append({
            "id": row["id"], "chars": len(row["text"]),
            "raw_ms": round(len(raw) / _SR * 1000),
            "trimmed_ms": round(len(trimmed) / _SR * 1000),
            "peak": float(np.max(np.abs(raw))) if len(raw) else 0.0,
            # where the chunk starts in the section, and how much leading
            # silence was cut: chunk-time t → section-time start_ms - lead_ms + t
            "start_ms": start_ms, "lead_ms": lead_ms,
        })

    section = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return section, stats


def run(config: dict, section: str | None = None, first: int | None = None) -> int:
    if not section:
        raise SystemExit("assemble: --section обязателен")
    sec_dir = paths.OUT / "sections" / section
    out, stats = assemble_section(sec_dir, config, first)
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
