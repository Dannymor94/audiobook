"""Master stage: section.wav -> highpass 80 Hz -> optional EQ -> two-pass loudnorm
(-19 LUFS / -3 dBTP) -> 44.1 kHz mp3 (ID3v2), 192 kbps CBR. Then measure the
true integrated loudness of the produced mp3 independently with pyloudnorm.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from audiobook import paths


def _ff() -> str:
    ff = paths.ffmpeg()
    if ff is None:
        raise SystemExit("ffmpeg не найден (bin/ или PATH)")
    return str(ff)


def _loudnorm_measure(ff: str, src: Path, I: float, tp: float, lra: float,
                      eq: str = "", highpass_hz: int = 80) -> dict:
    """Pass 1: run loudnorm in analysis mode, parse its JSON report. The filter
    chain before loudnorm must equal pass 2's, or the measurement is of
    different audio."""
    mid = f",{eq}" if eq else ""
    af = (f"highpass=f={int(highpass_hz)}{mid},"
          f"loudnorm=I={I}:TP={tp}:LRA={lra}:print_format=json")
    p = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af", af, "-f", "null", "-"],
                       capture_output=True, text=True)
    err = p.stderr
    start = err.rfind("{")
    end = err.rfind("}")
    if start == -1 or end == -1:
        raise SystemExit(f"loudnorm analysis failed:\n{err[-500:]}")
    return json.loads(err[start:end + 1])


def book_tags(config: dict, section: str) -> dict[str, str]:
    """ID3 tags of one chapter file from config ``book`` and the section's
    heading (text/blocks). Empty values are left out."""
    from audiobook.status import book_sections
    b = config.get("book") or {}
    skip = set((config.get("render") or {}).get("skip_sections") or [])
    order = [s for s in book_sections() if s not in skip]
    heading = ""
    jf = paths.TEXT / "blocks" / f"{section}.blocks.json"
    if jf.exists():
        with open(jf, encoding="utf-8") as f:
            heading = json.load(f).get("heading") or ""
    tags = {
        "title": heading or section,
        "album": str(b.get("title") or ""),
        "artist": str(b.get("author") or ""),
        "album_artist": str(b.get("author") or ""),
        "genre": "Audiobook",
        "comment": f"Читает: {b['narrator']}" if b.get("narrator") else "",
        "track": f"{order.index(section) + 1}/{len(order)}" if section in order else "",
    }
    return {k: v for k, v in tags.items() if v}


def cover_path(config: dict) -> Path | None:
    c = (config.get("book") or {}).get("cover")
    if not c:
        return None
    p = paths.ROOT / str(c)
    return p if p.exists() else None


def pad_filter(config: dict) -> str:
    """Silence at the head/tail of a chapter file (master.head_ms / tail_ms).
    Players butt files together; ACX asks for 1–5 s of room tone each end."""
    m = config.get("master") or {}
    h, t = int(m.get("head_ms") or 0), int(m.get("tail_ms") or 0)
    parts = []
    if h:
        parts.append(f"adelay=delays={h}:all=1")
    if t:
        parts.append(f"apad=pad_dur={t / 1000:g}")
    return ",".join(parts)


def master_section(sec_dir: Path, config: dict,
                   first: int | None = None) -> tuple[Path, dict]:
    """Book chapter: adds head/tail silence, ID3 tags and cover. Previews
    (--first) get the same treatment so they sound like the final file."""
    from audiobook.assemble import preview_name
    stem = preview_name(first)
    src = sec_dir / f"{stem}.wav"
    if not src.exists():
        raise SystemExit(f"нет {src.name}: {src}")
    out = sec_dir / f"{stem}.mp3"
    return out, master_wav(src, out, config, pad=True,
                           tags=book_tags(config, sec_dir.name), cover=cover_path(config))


def encode_args(ff: str, src: Path, out: Path, af: str, sr: int,
                tags: dict[str, str] | None = None, cover: Path | None = None) -> list[str]:
    cmd = [ff, "-hide_banner", "-y", "-i", str(src)]
    if cover:
        cmd += ["-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:v", "copy",
                "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
    cmd += ["-af", af, "-ar", str(sr), "-c:a", "libmp3lame", "-b:a", "192k",
            "-id3v2_version", "3"]
    for k, v in (tags or {}).items():
        cmd += ["-metadata", f"{k}={v}"]
    return cmd + ["-f", "mp3", str(out)]


def master_wav(src: Path, out: Path, config: dict, pad: bool = False,
               tags: dict[str, str] | None = None, cover: Path | None = None) -> dict:
    """highpass → config EQ → two-pass loudnorm → [head/tail silence] → 192k CBR
    mp3 with optional tags/cover. Written to a temp file and renamed. Returns the
    pass-1 loudnorm measurement."""
    ff = _ff()
    m = config["master"]
    # LRA above the input's keeps loudnorm in linear mode (no dynamic pumping)
    I, tp, lra = float(m["lufs"]), float(m["true_peak"]), float(m.get("lra", 11.0))
    sr = int(m["sample_rate"])
    hp = int(m["highpass_hz"])
    eq = m.get("eq_filters", "")

    meas = _loudnorm_measure(ff, src, I, tp, lra, eq, hp)
    # Pass 2: apply with measured values (accurate, near-linear normalization).
    mid = f",{eq}" if eq else ""
    af = (
        f"highpass=f={hp}{mid},"
        f"loudnorm=I={I}:TP={tp}:LRA={lra}:"
        f"measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
        f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
        f"offset={meas['target_offset']}:linear=true"
    )
    padf = pad_filter(config) if pad else ""
    if padf:
        af += "," + padf
    tmp = out.with_name(out.name + ".part")
    subprocess.run(encode_args(ff, src, tmp, af, sr, tags, cover),
                   capture_output=True, text=True, check=True)
    tmp.replace(out)
    return meas


def measure_lufs(mp3: Path, ff: str | None = None) -> tuple[float, float]:
    """Independent integrated-loudness + peak measurement of the final mp3."""
    import numpy as np
    import pyloudnorm as pyln
    import soundfile as sf

    ff = ff or _ff()
    wav = mp3.parent / (mp3.stem + ".measure.wav")
    subprocess.run([ff, "-hide_banner", "-y", "-i", str(mp3), str(wav)],
                   capture_output=True, check=True)
    data, sr = sf.read(str(wav), dtype="float32")
    wav.unlink(missing_ok=True)
    lufs = pyln.Meter(sr).integrated_loudness(data)
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    return lufs, peak


def run(config: dict, section: str | None = None, first: int | None = None) -> int:
    if not section:
        raise SystemExit("master: --section обязателен")
    sec_dir = paths.OUT / "sections" / section
    out, meas = master_section(sec_dir, config, first)
    lufs, peak = measure_lufs(out)
    peak_dbfs = 20 * (peak and __import__("math").log10(peak)) if peak else float("-inf")
    print(f"section={section}  -> {out}")
    print(f"loudnorm input: {meas['input_i']} LUFS, TP {meas['input_tp']} dBTP")
    print(f"final mp3: {lufs:.2f} LUFS (target {config['master']['lufs']}), "
          f"peak {peak:.4f} ({peak_dbfs:.2f} dBFS){'  CLIPPING' if peak >= 1.0 else ''}")
    return 0
