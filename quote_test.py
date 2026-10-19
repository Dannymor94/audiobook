#!/usr/bin/env python3
"""Throwaway: test three variants of the quoted phrase at end of ch13 heading."""
import json, os, sys, time, resource
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
import yaml
from audiobook import paths, leadin
from audiobook.synth import load_model, load_latents, synthesize, _SAMPLE_RATE
from audiobook.chunker import _split_sentences
from audiobook.pronounce import load_table, respell

with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

MANIFEST = Path("out/sections/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/manifest.jsonl")
LATENTS_PATH = Path("ref/ref1.latents_1.7b.pt")
TEMPERATURE = config["model"]["temperature"]
LANGUAGE = config["model"]["language"]
cap_cfg = config.get("render", {})
cap_base_ms = cap_cfg.get("cap_base_ms", 3000)
cap_ms_per_char = cap_cfg.get("cap_ms_per_char", 100)
cap_margin = cap_cfg.get("cap_margin", 1.5)
SENTENCE_MS = config.get("pauses_ms", {}).get("sentence", 350)
OUT_DIR = Path("out/quote_test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

table = load_table()

def split_to_max(text, max_chars):
    if max_chars is None or len(text) <= max_chars:
        return [text]
    sents = _split_sentences(text)
    parts, buf = [], ""
    for s in sents:
        candidate = (buf + " " + s).strip() if buf else s
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                parts.append(buf)
            if len(s) <= max_chars:
                buf = s
            else:
                words = s.split()
                buf2 = ""
                for w in words:
                    cand2 = (buf2 + " " + w).strip() if buf2 else w
                    if len(cand2) <= max_chars:
                        buf2 = cand2
                    else:
                        if buf2:
                            parts.append(buf2)
                        buf2 = w
                buf = buf2
    if buf:
        parts.append(buf)
    return parts or [text]

def render_frag(text, seed, model, latents):
    phrase = leadin.fires(text, config)
    base = leadin.pad(text, phrase) if phrase else text
    synth_text = respell(base, table)
    padded_len = len(synth_text)
    max_tok = int((cap_base_ms + padded_len * cap_ms_per_char) * cap_margin * 12 / 1000)
    t0 = time.time()
    for attempt in range(3):
        s = seed + attempt * 1000
        try:
            wav = synthesize(model, synth_text, latents, s, TEMPERATURE, LANGUAGE,
                             max_new_tokens=max_tok)
            if phrase:
                wav = leadin.trim_carrier(wav, synth_text, phrase)
            break
        except leadin.TrimFailed as e:
            print(f"    trim_carrier attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print(f"    WARNING: using raw wav for {text!r}")
        except Exception as e:
            print(f"    FAILED {text!r}: {e}")
            wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)
            break
    wall = time.time() - t0
    li = "LI" if phrase else "  "
    print(f"  {li} {len(text):3d}ch {len(wav)/_SAMPLE_RATE:5.1f}s wall={wall:.0f}s  {text!r}")
    return wav

def silence(ms):
    return np.zeros(int(_SAMPLE_RATE * ms / 1000), dtype=np.float32)

def write_mp3(label, wavs):
    combined = np.concatenate(wavs)
    wav_path = OUT_DIR / f"{label}.wav"
    mp3_path = OUT_DIR / f"{label}.mp3"
    wf.write(str(wav_path), _SAMPLE_RATE, combined)
    ret = os.system(
        f'{paths.ffmpeg()} -y -i {wav_path} '
        f'-af loudnorm=I=-19:TP=-2:LRA=9 -ar 44100 -b:a 192k {mp3_path} 2>/dev/null'
    )
    wav_path.unlink(missing_ok=True)
    print(f"  MP3: {mp3_path}" if ret == 0 else f"  ffmpeg failed exit={ret}")

# ── load chunks ────────────────────────────────────────────────────────────────
raw_chunks = []
total_ms = 0
for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
    c = json.loads(line)
    total_ms += c.get("duration_ms", 0) + c.get("pause_after_ms", 0)
    raw_chunks.append(c)
    if total_ms >= 60_000:
        break
HEAD_PAUSE_MS = raw_chunks[0].get("pause_after_ms", 1500)
tail_chunks = raw_chunks[1:]

print("Loading 1.7B model...")
t0 = time.time()
model = load_model(device="cpu")
latents = load_latents(LATENTS_PATH)
print(f"  ready in {time.time()-t0:.1f}s\n")

# ── render shared parts ────────────────────────────────────────────────────────
print("=== Shared: heading parts 1+2 ===")
wav_h1 = render_frag("Глава тринадцатая.", 30, model, latents)
wav_h2 = render_frag("Базовый навык:", 31, model, latents)

print("\n=== Shared: tail (chunks 2-7) ===")
tail_wavs = []
for i, c in enumerate(tail_chunks):
    parts = split_to_max(c["text"], 120)
    pause = c.get("pause_after_ms", 0)
    for j, p in enumerate(parts):
        tail_wavs.append(render_frag(p, 100 + i * 10 + j, model, latents))
        p_ms = pause if j == len(parts) - 1 else SENTENCE_MS
        if p_ms > 0:
            tail_wavs.append(silence(p_ms))

def heading_prefix():
    return [wav_h1, silence(900), wav_h2, silence(400)]

# ── three quoted-phrase variants ───────────────────────────────────────────────
VARIANTS = [
    ("quote_a", "«Я тебя чувствую»"),
    ("quote_b", "Я тебя чувствую"),
    ("quote_c", "Я тебя чувствую."),
]

for label, quote_text in VARIANTS:
    print(f"\n=== Variant {label}: {quote_text!r} ===")
    seed = {"quote_a": 32, "quote_b": 33, "quote_c": 34}[label]
    wav_q = render_frag(quote_text, seed, model, latents)
    wavs = heading_prefix() + [wav_q, silence(HEAD_PAUSE_MS)] + tail_wavs
    write_mp3(label, wavs)

peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
print(f"\nPeak RAM: {peak_gb:.1f} GB")
print("FILES:")
for label, _ in VARIANTS:
    print(f"  {OUT_DIR}/{label}.mp3")
