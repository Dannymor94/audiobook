#!/usr/bin/env python3
"""Throwaway: test three heading splits for ch13. Tail rendered once, reused."""
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

SECTION = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstu"
MANIFEST = Path(f"out/sections/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/manifest.jsonl")
LATENTS_PATH = Path("ref/ref1.latents_1.7b.pt")
TEMPERATURE = config["model"]["temperature"]
LANGUAGE = config["model"]["language"]
cap_cfg = config.get("render", {})
cap_base_ms = cap_cfg.get("cap_base_ms", 3000)
cap_ms_per_char = cap_cfg.get("cap_ms_per_char", 100)
cap_margin = cap_cfg.get("cap_margin", 1.5)
SENTENCE_MS = config.get("pauses_ms", {}).get("sentence", 350)
OUT_DIR = Path("out/head_test")
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
                print(f"    WARNING: using raw wav for {text[:30]!r}")
        except Exception as e:
            print(f"    FAILED {text[:30]!r}: {e}")
            wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)
            break
    wall = time.time() - t0
    dur_s = len(wav) / _SAMPLE_RATE
    li = "LI" if phrase else "  "
    print(f"  {li} {len(text):3d}ch {dur_s:5.1f}s wall={wall:.0f}s  {text!r}")
    return wav

def silence(ms):
    return np.zeros(int(_SAMPLE_RATE * ms / 1000), dtype=np.float32)

def write_mp3(label, wavs):
    combined = np.concatenate(wavs)
    wav_path = OUT_DIR / f"{label}.wav"
    mp3_path = OUT_DIR / f"{label}.mp3"
    wf.write(str(wav_path), _SAMPLE_RATE, combined)
    ffmpeg = str(paths.ffmpeg())
    ret = os.system(
        f'{ffmpeg} -y -i {wav_path} '
        f'-af loudnorm=I=-19:TP=-2:LRA=9 -ar 44100 -b:a 192k {mp3_path} 2>/dev/null'
    )
    wav_path.unlink(missing_ok=True)
    if ret == 0:
        print(f"  MP3: {mp3_path}")
    else:
        print(f"  ffmpeg failed exit={ret}")

# ── load chunks ────────────────────────────────────────────────────────────────
raw_chunks = []
total_ms = 0
for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
    c = json.loads(line)
    total_ms += c.get("duration_ms", 0) + c.get("pause_after_ms", 0)
    raw_chunks.append(c)
    if total_ms >= 60_000:
        break
print(f"Source chunks: {len(raw_chunks)}")

heading_chunk = raw_chunks[0]  # "Глава тринадцатая. Базовый навык: «Я тебя чувствую»"
tail_chunks = raw_chunks[1:]
HEAD_PAUSE_MS = heading_chunk.get("pause_after_ms", 1500)  # pause after heading section

print("Loading 1.7B model...")
t0 = time.time()
model = load_model(device="cpu")
latents = load_latents(LATENTS_PATH)
print(f"  ready in {time.time()-t0:.1f}s\n")

# ── render tail once ───────────────────────────────────────────────────────────
print("=== Rendering common tail (chunks 2-7) ===")
tail_wavs = []
frag_i = 100  # seed offset, well away from heading seeds
for c in tail_chunks:
    parts = split_to_max(c["text"], 120)
    pause = c.get("pause_after_ms", 0)
    for j, p in enumerate(parts):
        frag_i += 1
        wav = render_frag(p, frag_i, model, latents)
        tail_wavs.append(wav)
        p_ms = pause if j == len(parts) - 1 else SENTENCE_MS
        if p_ms > 0:
            tail_wavs.append(silence(p_ms))

# ── variant a: heading as one chunk ───────────────────────────────────────────
print("\n=== Variant a: one heading chunk ===")
wav_a = render_frag(heading_chunk["text"], 10, model, latents)
wavs_a = [wav_a, silence(HEAD_PAUSE_MS)] + tail_wavs
write_mp3("head_a", wavs_a)

# ── variant b: split at period ─────────────────────────────────────────────────
print("\n=== Variant b: 'Глава тринадцатая.' + 'Базовый навык: «Я тебя чувствую»' ===")
b1 = "Глава тринадцатая."
b2 = "Базовый навык: «Я тебя чувствую»"
wav_b1 = render_frag(b1, 20, model, latents)
wav_b2 = render_frag(b2, 21, model, latents)
wavs_b = [wav_b1, silence(900), wav_b2, silence(HEAD_PAUSE_MS)] + tail_wavs
write_mp3("head_b", wavs_b)

# ── variant c: three parts ─────────────────────────────────────────────────────
print("\n=== Variant c: three parts ===")
c1 = "Глава тринадцатая."
c2 = "Базовый навык:"
c3 = "«Я тебя чувствую»"
wav_c1 = render_frag(c1, 30, model, latents)
wav_c2 = render_frag(c2, 31, model, latents)
wav_c3 = render_frag(c3, 32, model, latents)
wavs_c = [wav_c1, silence(900), wav_c2, silence(400), wav_c3, silence(HEAD_PAUSE_MS)] + tail_wavs
write_mp3("head_c", wavs_c)

peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
print(f"\nPeak RAM: {peak_gb:.1f} GB")
print("FILES:")
for lbl in ("head_a", "head_b", "head_c"):
    print(f"  {OUT_DIR}/{lbl}.mp3")
