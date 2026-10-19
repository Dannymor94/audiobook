#!/usr/bin/env python3
"""Throwaway: render first ~60s of ch13 with 1.7B model. Do not touch config.yaml."""
import json, os, sys, time, resource
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PYTHONUTF8"] = "1"

# Patch _QWEN_HUB_DIR to 1.7B BEFORE any module-level code in synth uses it.
import audiobook.synth as _synth_mod
_synth_mod._QWEN_HUB_DIR = Path("models/hf/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base")

import numpy as np
import yaml
from audiobook import paths
from audiobook.synth import load_model, load_latents, synthesize, _SAMPLE_RATE

with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

SECTION = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
MANIFEST = Path(f"out/sections/{SECTION}/manifest.jsonl")
LATENTS_PATH = Path(config["reference"]["path"]).with_suffix(".latents.pt")
TEMPERATURE = config["model"]["temperature"]
LANGUAGE = config["model"]["language"]
# cap params from config
cap_cfg = config.get("render", {})
cap_base_ms = cap_cfg.get("cap_base_ms", 3000)
cap_ms_per_char = cap_cfg.get("cap_ms_per_char", 100)
cap_margin = cap_cfg.get("cap_margin", 1.5)

# load first ~60s of chunks
chunks = []
total_ms = 0
for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
    c = json.loads(line)
    total_ms += c.get("duration_ms", 0) + c.get("pause_after_ms", 0)
    chunks.append(c)
    if total_ms >= 60_000:
        break
print(f"Chunks to render: {len(chunks)} (~{total_ms/1000:.0f}s by 0.6B timings)")

print("Loading 1.7B model...")
t0 = time.time()
model = load_model(device="cpu")
print(f"  loaded in {time.time()-t0:.1f}s")

# Latents are model-specific (hidden size differs between 0.6B and 1.7B).
# Compute fresh 1.7B latents from the reference wav; save alongside existing.
from audiobook.synth import compute_latents, save_latents
LATENTS_1_7B = LATENTS_PATH.parent / "ref1.latents_1.7b.pt"
REF_WAV = Path(config["reference"]["path"])
REF_TEXT_PATH = Path(config["reference"]["ref_text_path"])
ref_text = REF_TEXT_PATH.read_text(encoding="utf-8").strip()

if not LATENTS_1_7B.exists():
    print("Computing 1.7B latents from reference wav...")
    t_lat = time.time()
    latents = compute_latents(model, REF_WAV, ref_text)
    save_latents(latents, LATENTS_1_7B)
    print(f"  done in {time.time()-t_lat:.1f}s → {LATENTS_1_7B}")
else:
    print(f"Loading cached 1.7B latents from {LATENTS_1_7B}")
    latents = load_latents(LATENTS_1_7B)

wavs = []
render_start = time.time()
for c in chunks:
    seed = c.get("seed_override") or c["seed"]
    text = c["text"]
    max_tok = int((cap_base_ms + len(text) * cap_ms_per_char) * cap_margin * 12 / 1000)
    t_chunk = time.time()
    try:
        wav = synthesize(model, text, latents, seed, TEMPERATURE, LANGUAGE,
                         max_new_tokens=max_tok)
    except Exception as e:
        print(f"  FAILED {c['id']}: {e}")
        continue
    elapsed = time.time() - t_chunk
    audio_s = len(wav) / _SAMPLE_RATE
    print(f"  {c['id']}  {audio_s:.1f}s audio  {elapsed:.1f}s wall  RTF={elapsed/audio_s:.2f}x")
    wavs.append(wav)
    pause_ms = c.get("pause_after_ms", 0)
    if pause_ms > 0:
        wavs.append(np.zeros(int(_SAMPLE_RATE * pause_ms / 1000), dtype=np.float32))

render_wall = time.time() - render_start
audio_total = sum(len(w) for w in wavs) / _SAMPLE_RATE
peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024  # KB→GB on Linux

print(f"\n=== RESULTS ===")
print(f"Audio:    {audio_total:.1f}s")
print(f"Wall:     {render_wall:.1f}s")
print(f"RTF:      {render_wall/audio_total:.2f}x" if audio_total else "RTF: n/a")
print(f"Peak RAM: {peak_gb:.1f} GB")

if not wavs:
    print("No audio generated, exiting.")
    sys.exit(1)

combined = np.concatenate(wavs)

# master with ffmpeg loudnorm
import scipy.io.wavfile as wf
OUT_WAV = Path("/tmp/ch13_1.7b.wav")
OUT_MP3 = Path("/tmp/ch13_1.7b.mp3")
wf.write(str(OUT_WAV), _SAMPLE_RATE, combined)
print(f"WAV:      {OUT_WAV}  ({OUT_WAV.stat().st_size // 1024} KB)")

ffmpeg = str(paths.ffmpeg())
ret = os.system(
    f'{ffmpeg} -y -i {OUT_WAV} '
    f'-af loudnorm=I=-19:TP=-2:LRA=9 -ar 44100 -b:a 192k {OUT_MP3} 2>/tmp/ffmpeg_1.7b.log'
)
if ret == 0:
    print(f"MP3:      {OUT_MP3}")
else:
    print(f"ffmpeg failed (exit {ret}) — check /tmp/ffmpeg_1.7b.log")
