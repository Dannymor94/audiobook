"""Слой 1: assemble/master на синтетике. Заполняется по мере появления модулей."""
from __future__ import annotations

import subprocess

import numpy as np
import pytest
import soundfile as sf

from audiobook import paths


def _sine(sec: float, sr: int = 24000, f: float = 440.0) -> np.ndarray:
    t = np.arange(int(sec * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)


@pytest.mark.skipif(paths.ffmpeg() is None, reason="нет ffmpeg")
def test_ffmpeg_loudnorm_hits_target(tmp_path):
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    sf.write(src, _sine(3.0), 24000)
    subprocess.run([str(paths.ffmpeg()), "-y", "-i", str(src), "-af",
                    "highpass=f=80,loudnorm=I=-19:TP=-3:LRA=11", "-ar", "44100", str(dst)],
                   check=True, capture_output=True)
    import pyloudnorm as pyln
    y, sr = sf.read(dst)
    lufs = pyln.Meter(sr).integrated_loudness(y)
    assert -21 <= lufs <= -17, lufs


def test_pause_math():
    """Каркас для assemble: 3 куска по 1 с + паузы 350/900 -> 4.25 с."""
    sr = 24000
    parts = [_sine(1.0), _sine(1.0), _sine(1.0)]
    pauses = [350, 900, 0]
    out = np.concatenate([np.concatenate([p, np.zeros(int(sr * ms / 1000), np.float32)])
                          for p, ms in zip(parts, pauses)])
    assert abs(len(out) / sr - 4.25) < 0.01
