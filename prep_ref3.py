#!/usr/bin/env python3
"""Trim clipped start of ref3.wav, compute 1.7B latents with ICL transcript."""
import os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PYTHONUTF8"] = "1"

import audiobook.synth as _synth_mod
_synth_mod._QWEN_HUB_DIR = Path("models/hf/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base")

import numpy as np
import scipy.io.wavfile as wf
from audiobook.synth import load_model, compute_latents, save_latents

REF3_IN  = Path("ref/ref3.wav")
REF3_OUT = Path("ref/ref3_trim.wav")
LATENTS_OUT = Path("ref/ref3_trim.latents_1.7b.pt")

# Confirmed transcript (user-verified by ear):
REF3_TEXT = (
    "срывается, может накричать на дочь, на разбросанные фломастеры, "
    "так что сама потом рыдает в ванной, может нагрубить мужу без причины, "
    "а потом неделю ходить извиняться. Алёна не понимает, откуда это берётся, "
    "она же добрая, хорошая, правильная. Откуда эта злость?"
)

# Amplitude analysis: clipped vowel 0-220ms, silence 220-720ms, onset at ~720ms.
# Trim at 700ms to remove the clipped fragment and keep 20ms natural pre-silence.
TRIM_S = 0.700

sr, data = wf.read(str(REF3_IN))
trim_samples = int(TRIM_S * sr)
trimmed = data[trim_samples:]
wf.write(str(REF3_OUT), sr, trimmed)
dur_orig = len(data) / sr
dur_trim = len(trimmed) / sr
print(f"Trimmed {TRIM_S:.3f}s: {dur_orig:.2f}s → {dur_trim:.2f}s → {REF3_OUT}")

print(f"\nComputing 1.7B latents (ICL mode)...")
t0 = time.time()
model = load_model(device="cpu")
latents = compute_latents(model, REF3_OUT, ref_text=REF3_TEXT)
save_latents(latents, LATENTS_OUT)
print(f"  done in {time.time()-t0:.1f}s → {LATENTS_OUT}")
print(f"  size: {LATENTS_OUT.stat().st_size} bytes")
