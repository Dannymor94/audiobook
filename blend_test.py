#!/usr/bin/env python3
"""Throwaway: check synth text for ? fragments, then render mix_calm and mix_blend."""
import json, os, time, resource
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"

import audiobook.synth as _synth_mod
_synth_mod._QWEN_HUB_DIR = Path("models/hf/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base")

import numpy as np
import torch
import scipy.io.wavfile as wf
import yaml
from audiobook import paths, leadin
from audiobook.synth import load_model, load_latents, synthesize, _SAMPLE_RATE
from audiobook.chunker import _split_sentences
from audiobook.pronounce import load_table, respell

with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

MANIFEST = Path("out/sections/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/manifest.jsonl")
TEMPERATURE = config["model"]["temperature"]
LANGUAGE = config["model"]["language"]
cap_cfg = config.get("render", {})
cap_base_ms = cap_cfg.get("cap_base_ms", 3000)
cap_ms_per_char = cap_cfg.get("cap_ms_per_char", 100)
cap_margin = cap_cfg.get("cap_margin", 1.5)
SENTENCE_MS = config.get("pauses_ms", {}).get("sentence", 350)
ENUM_MS = 250
HEAD_PAUSE_MS = 1500
MAX_CHARS = 180
OUT_DIR = Path("out/blend_test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

table = load_table()

_TERMINAL = set(".!?…:;")
_STRIP_QUOTES = str.maketrans("", "", "«»“”„‟")

def normalize_punct(text):
    t = text.translate(_STRIP_QUOTES).strip()
    if t and t[-1] not in _TERMINAL:
        t += "."
    return t

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

def render_frag(raw_text, seed, model, latents):
    text = normalize_punct(raw_text)
    phrase = leadin.fires(text, config)
    base = leadin.pad(text, phrase) if phrase else text
    synth_text = respell(base, table)
    max_tok = int((cap_base_ms + len(synth_text) * cap_ms_per_char) * cap_margin * 12 / 1000)
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
            print(f"    trim_carrier attempt {attempt+1} failed: {e}", flush=True)
            if attempt == 2:
                print(f"    WARNING: using raw wav for {raw_text[:30]!r}", flush=True)
        except Exception as e:
            print(f"    FAILED {raw_text[:30]!r}: {e}", flush=True)
            wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)
            break
    wall = time.time() - t0
    li = "LI" if phrase else "  "
    print(f"  {li} {len(raw_text):3d}ch {len(wav)/_SAMPLE_RATE:5.1f}s {wall:.0f}s", flush=True)
    return wav

def silence(ms):
    return np.zeros(int(_SAMPLE_RATE * ms / 1000), dtype=np.float32)

def write_mp3(name, wavs, wall_s):
    combined = np.concatenate(wavs)
    audio_s = len(combined) / _SAMPLE_RATE
    wav_path = OUT_DIR / f"{name}.wav"
    mp3_path = OUT_DIR / f"{name}.mp3"
    wf.write(str(wav_path), _SAMPLE_RATE, combined)
    ret = os.system(
        f'{paths.ffmpeg()} -y -i {wav_path} '
        f'-af loudnorm=I=-19:TP=-2:LRA=9 -ar 44100 -b:a 192k {mp3_path} 2>/dev/null'
    )
    wav_path.unlink(missing_ok=True)
    status = "MP3" if ret == 0 else f"ffmpeg fail={ret}"
    print(f"  {status}: {mp3_path}  {audio_s:.1f}s audio  {wall_s:.1f}s wall  RTF={wall_s/audio_s:.2f}x", flush=True)

# ── blend latents: cat ref_code + average ref_spk_embedding ──────────────────
REF3_TEXT = (
    "срывается, может накричать на дочь, на разбросанные фломастеры, "
    "так что сама потом рыдает в ванной, может нагрубить мужу без причины, "
    "а потом неделю ходить извиняться. Алёна не понимает, откуда это берётся, "
    "она же добрая, хорошая, правильная. Откуда эта злость?"
)

def blend_latents(lat_calm, lat_lively):
    """Build a single-item latents by concatenating ICL ref_codes and averaging speaker embeddings.
    The model sees both voice examples as one long ICL context."""
    ic, il = lat_calm["items"][0], lat_lively["items"][0]
    return {"items": [{
        "ref_code": torch.cat([ic["ref_code"], il["ref_code"]], dim=0),
        "ref_spk_embedding": (ic["ref_spk_embedding"].float() + il["ref_spk_embedding"].float()) / 2,
        "x_vector_only_mode": False,
        "icl_mode": True,
        "ref_text": ic["ref_text"] + " " + REF3_TEXT,
    }]}

# ── load chunks ───────────────────────────────────────────────────────────────
raw_chunks = []
total_ms = 0
for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
    c = json.loads(line)
    total_ms += c.get("duration_ms", 0) + c.get("pause_after_ms", 0)
    raw_chunks.append(c)
    if total_ms >= 300_000:
        break
print(f"Source chunks: {len(raw_chunks)} (~{total_ms/1000:.0f}s)", flush=True)

# ── build fragment list ───────────────────────────────────────────────────────
heading_frags = [
    ("Глава тринадцатая.", 900),
    ("Базовый навык:", 400),
    ("«Я тебя чувствую»", HEAD_PAUSE_MS),
]
tail_frags = []
for c in raw_chunks[1:]:
    parts = split_to_max(c["text"], MAX_CHARS)
    pause = c.get("pause_after_ms", 0)
    chunk_type = c.get("type", "")
    if chunk_type == "enum":
        pause = ENUM_MS
    for j, p in enumerate(parts):
        tail_frags.append((p, pause if j == len(parts) - 1 else SENTENCE_MS))

all_frags = heading_frags + tail_frags
print(f"Total fragments: {len(all_frags)}", flush=True)

# ── step 1: check synth text for ? fragments ─────────────────────────────────
TARGETS = ["Кто это будет", "В каком состоянии"]
print("\n=== SYNTH TEXT CHECK ===", flush=True)
for raw_text, _ in all_frags:
    if any(t in raw_text for t in TARGETS):
        text = normalize_punct(raw_text)
        phrase = leadin.fires(text, config)
        base = leadin.pad(text, phrase) if phrase else text
        synth_text = respell(base, table)
        print(f"  RAW:   {raw_text!r}", flush=True)
        print(f"  NORM:  {text!r}", flush=True)
        print(f"  SYNTH: {synth_text!r}", flush=True)
        print(f"  last_char_norm={text[-1]!r}  last_char_synth={synth_text[-1]!r}", flush=True)
        print(flush=True)
print("=== END CHECK ===\n", flush=True)

# ── step 2: load model + compute blend latents ───────────────────────────────
print("Loading 1.7B model...", flush=True)
t0 = time.time()
model = load_model(device="cpu")
print(f"  ready in {time.time()-t0:.1f}s\n", flush=True)

lat1 = load_latents(Path("ref/ref1.latents_1.7b.pt"))
lat3 = load_latents(Path("ref/ref3_trim.latents_1.7b.pt"))

lat_blend = blend_latents(lat1, lat3)
item0 = lat_blend["items"][0]
print(f"Blend: ref_code shape={tuple(item0['ref_code'].shape)}  "
      f"spk_emb shape={tuple(item0['ref_spk_embedding'].shape)}\n", flush=True)

VARIANTS = [
    ("mix_calm",  lat1),
    ("mix_blend", lat_blend),
]

timing = {}
for label, latents in VARIANTS:
    print(f"\n=== {label} ===", flush=True)
    t_var = time.time()
    wavs = []
    for i, (raw_text, pause_ms) in enumerate(all_frags, 1):
        print(f"[{i}/{len(all_frags)}] {raw_text[:55]!r}", flush=True)
        wav = render_frag(raw_text, 42 + i, model, latents)
        wavs.append(wav)
        if pause_ms > 0:
            wavs.append(silence(pause_ms))
    wall_s = time.time() - t_var
    write_mp3(label, wavs, wall_s)
    timing[label] = wall_s

peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
print(f"\nPeak RAM: {peak_gb:.1f} GB", flush=True)
print("Summary:", flush=True)
for lbl, ws in timing.items():
    print(f"  {lbl}: {ws:.1f}s ({ws/60:.1f} min)", flush=True)
print("FILES:", flush=True)
for label, _ in VARIANTS:
    print(f"  {OUT_DIR}/{label}.mp3", flush=True)
