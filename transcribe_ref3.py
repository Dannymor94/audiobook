#!/usr/bin/env python3
"""Transcribe ref3.wav using faster-whisper, print result."""
import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PYTHONUTF8"] = "1"

from faster_whisper import WhisperModel

wav = Path("ref/ref3.wav")
print(f"File: {wav}  size={wav.stat().st_size} bytes")

model = WhisperModel(str(Path("models/whisper/small")), device="cpu", compute_type="int8")
segments, info = model.transcribe(str(wav), language="ru", word_timestamps=True)

print(f"Detected language: {info.language} (prob={info.language_probability:.2f})")
print(f"Duration: {info.duration:.2f}s\n")

full = []
for seg in segments:
    print(f"[{seg.start:.2f}→{seg.end:.2f}] {seg.text.strip()}")
    full.append(seg.text.strip())

print("\n=== FULL TRANSCRIPT ===")
print(" ".join(full))
