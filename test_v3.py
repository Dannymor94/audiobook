#!/usr/bin/env python3
"""Throwaway: same as test_v2 but with lead-in applied to short fragments.
Current config threshold=55; this script raises it in-memory to 40 (task asks ≥40).
Actually 55 already covers ≤40, so we just apply it properly this time.
"""
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
from audiobook import paths
from audiobook.synth import load_model, load_latents, synthesize, _SAMPLE_RATE
from audiobook.chunker import _split_sentences
from audiobook.pronounce import load_table, respell
from audiobook import leadin

with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Use config as-is (max_chars=55). Fragment 6 (21 chars) fires at 55.
cfg = config

c_info = leadin.carrier(cfg)
print(f"Lead-in: phrase={c_info[0]!r}  max_chars={c_info[1]}")

SECTION = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
MANIFEST = Path(f"out/sections/{SECTION}/manifest.jsonl")
LATENTS_PATH = Path("ref/ref1.latents_1.7b.pt")
TEMPERATURE = config["model"]["temperature"]
LANGUAGE = config["model"]["language"]
SENTENCE_MS = config.get("pauses_ms", {}).get("sentence", 350)
cap_cfg = config.get("render", {})
cap_base_ms = cap_cfg.get("cap_base_ms", 3000)
cap_ms_per_char = cap_cfg.get("cap_ms_per_char", 100)
cap_margin = cap_cfg.get("cap_margin", 1.5)
sentinel = config.get("model", {}).get("sentinel", "")
MAX_CHARS = 120
OUT_DIR = Path("out/test_v3")
OUT_DIR.mkdir(parents=True, exist_ok=True)

table = load_table()
print(f"Pronounce table: {len(table)} entries")


def split_to_max(text: str, max_chars: int) -> list[str]:
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


# load first ~60s chunks
raw_chunks = []
total_ms = 0
for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
    c = json.loads(line)
    total_ms += c.get("duration_ms", 0) + c.get("pause_after_ms", 0)
    raw_chunks.append(c)
    if total_ms >= 60_000:
        break
print(f"Source chunks: {len(raw_chunks)} (~{total_ms/1000:.0f}s)")

frags = []
for c in raw_chunks:
    parts = split_to_max(c["text"], MAX_CHARS)
    pause = c.get("pause_after_ms", 0)
    for i, p in enumerate(parts):
        frags.append((p, pause if i == len(parts) - 1 else SENTENCE_MS, c["id"]))
print(f"Fragments after split (max {MAX_CHARS}): {len(frags)}")

print("Loading 1.7B model...")
t0 = time.time()
model = load_model(device="cpu")
latents = load_latents(LATENTS_PATH)
print(f"  ready in {time.time()-t0:.1f}s")

print(f"\n{'frag':5} {'src':6} {'chars':5} {'leadin':6} {'dur_s':6} {'wall_s':7} {'rtf':5}  text")
print("-" * 80)

wavs = []
t_render = time.time()
for i, (text, pause_ms, src) in enumerate(frags, 1):
    phrase = leadin.fires(text, cfg)
    base = leadin.pad(text, phrase) if phrase else text
    synth_text = respell(base, table)
    if phrase:
        print(f"  [lead-in frag {i}] {len(text)}ch: {text!r}")
    if synth_text != base:
        pass  # respell note already printed in test_v2

    # cap based on padded length
    padded_len = len(synth_text)
    max_tok = int((cap_base_ms + padded_len * cap_ms_per_char) * cap_margin * 12 / 1000)

    t0 = time.time()
    for attempt in range(3):
        seed = 42 + i + attempt * 1000
        try:
            wav = synthesize(model, synth_text, latents, seed, TEMPERATURE, LANGUAGE,
                             max_new_tokens=max_tok)
            if phrase:
                wav = leadin.trim_carrier(wav, synth_text, phrase)
            break
        except leadin.TrimFailed as e:
            print(f"  trim_carrier attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print(f"  WARNING: using raw (uncut) wav for frag {i}")
        except Exception as e:
            print(f"  FAILED frag {i}: {e}")
            wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)
            break

    wall = time.time() - t0
    dur_s = len(wav) / _SAMPLE_RATE
    rtf = wall / dur_s if dur_s > 0 else 0
    li_flag = "YES" if phrase else "no"
    print(f"{i:5d} {src:6} {len(text):5d} {li_flag:6} {dur_s:6.1f} {wall:7.1f} {rtf:5.2f}  {text[:38]!r}")
    wavs.append(wav)
    if pause_ms > 0:
        wavs.append(np.zeros(int(_SAMPLE_RATE * pause_ms / 1000), dtype=np.float32))

wall_total = time.time() - t_render
audio_total = sum(len(w) for w in wavs) / _SAMPLE_RATE
peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
print(f"\nTotal: {wall_total:.1f}s wall  {audio_total:.1f}s audio  RTF={wall_total/audio_total:.2f}x  RAM={peak_gb:.1f}GB")

combined = np.concatenate(wavs)
wav_path = OUT_DIR / "v3.wav"
mp3_path = OUT_DIR / "v3.mp3"
wf.write(str(wav_path), _SAMPLE_RATE, combined)
ffmpeg = str(paths.ffmpeg())
ret = os.system(
    f'{ffmpeg} -y -i {wav_path} '
    f'-af loudnorm=I=-19:TP=-2:LRA=9 -ar 44100 -b:a 192k {mp3_path} 2>/dev/null'
)
wav_path.unlink(missing_ok=True)
if ret == 0:
    print(f"MP3: {mp3_path}")
else:
    print(f"ffmpeg failed exit={ret}")
