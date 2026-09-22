"""Master stage: section.wav -> highpass 80 Hz -> two-pass loudnorm
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


def _loudnorm_measure(ff: str, src: Path, I: float, tp: float, lra: float) -> dict:
    """Pass 1: run loudnorm in analysis mode, parse its JSON report."""
    af = f"highpass=f=80,loudnorm=I={I}:TP={tp}:LRA={lra}:print_format=json"
    p = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af", af, "-f", "null", "-"],
                       capture_output=True, text=True)
    err = p.stderr
    start = err.rfind("{")
    end = err.rfind("}")
    if start == -1 or end == -1:
        raise SystemExit(f"loudnorm analysis failed:\n{err[-500:]}")
    return json.loads(err[start:end + 1])


def master_section(sec_dir: Path, config: dict) -> tuple[Path, dict]:
    ff = _ff()
    src = sec_dir / "section.wav"
    if not src.exists():
        raise SystemExit(f"нет section.wav: {src}")
    m = config["master"]
    I, tp, lra = float(m["lufs"]), float(m["true_peak"]), 11.0
    sr = int(m["sample_rate"])
    hp = int(m["highpass_hz"])

    meas = _loudnorm_measure(ff, src, I, tp, lra)
    # Pass 2: apply with measured values (accurate, near-linear normalization).
    af = (
        f"highpass=f={hp},"
        f"loudnorm=I={I}:TP={tp}:LRA={lra}:"
        f"measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
        f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
        f"offset={meas['target_offset']}:linear=true"
    )
    out = sec_dir / "section.mp3"
    subprocess.run(
        [ff, "-hide_banner", "-y", "-i", str(src), "-af", af, "-ar", str(sr),
         "-c:a", "libmp3lame", "-b:a", "192k", "-id3v2_version", "3", str(out)],
        capture_output=True, text=True, check=True,
    )
    return out, meas


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


def run(config: dict, section: str | None = None) -> int:
    if not section:
        raise SystemExit("master: --section обязателен")
    sec_dir = paths.OUT / "sections" / section
    out, meas = master_section(sec_dir, config)
    lufs, peak = measure_lufs(out)
    peak_dbfs = 20 * (peak and __import__("math").log10(peak)) if peak else float("-inf")
    print(f"section={section}  -> {out}")
    print(f"loudnorm input: {meas['input_i']} LUFS, TP {meas['input_tp']} dBTP")
    print(f"final mp3: {lufs:.2f} LUFS (target {config['master']['lufs']}), "
          f"peak {peak:.4f} ({peak_dbfs:.2f} dBFS){'  CLIPPING' if peak >= 1.0 else ''}")
    return 0
