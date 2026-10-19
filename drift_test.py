#!/usr/bin/env python3
"""Throwaway drift test: render first ~60s of ch13 with 1.7B at 3 max-length limits."""
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

with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

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
OUT_DIR = Path("out/drift_test")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def split_to_max(text: str, max_chars: int) -> list[str]:
    """Split text into parts of at most max_chars, respecting sentence boundaries."""
    if max_chars is None or len(text) <= max_chars:
        return [text]
    # try sentence boundaries first
    sents = _split_sentences(text)
    parts, buf = [], ""
    for s in sents:
        candidate = (buf + " " + s).strip() if buf else s
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                parts.append(buf)
            # sentence itself might be too long — split at word boundary
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


def build_fragments(chunks: list[dict], max_chars) -> list[tuple[str, int, str]]:
    """Return (text, pause_ms, source_id) triples."""
    frags = []
    for c in chunks:
        parts = split_to_max(c["text"], max_chars)
        pause = c.get("pause_after_ms", 0)
        for i, p in enumerate(parts):
            frags.append((p, pause if i == len(parts) - 1 else SENTENCE_MS, c["id"]))
    return frags


def render_variant(label: str, frags: list[tuple[str, int, str]], model, latents):
    print(f"\n{'='*60}")
    print(f"Variant: {label}  ({len(frags)} fragments)")
    print(f"{'frag':5} {'src':6} {'chars':5} {'dur_s':6} {'wall_s':7} {'rtf':5}  text")
    print(f"{'-'*70}")

    wavs = []
    t_start = time.time()
    rows = []
    for i, (text, pause_ms, src) in enumerate(frags, 1):
        seed_base = 42 + i  # deterministic but distinct per position
        max_tok = int((cap_base_ms + len(text) * cap_ms_per_char) * cap_margin * 12 / 1000)
        t0 = time.time()
        try:
            wav = synthesize(model, text, latents, seed_base, TEMPERATURE, LANGUAGE,
                             max_new_tokens=max_tok)
        except Exception as e:
            print(f"  FAILED frag {i}: {e}")
            wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)
        wall = time.time() - t0
        dur_s = len(wav) / _SAMPLE_RATE
        rtf = wall / dur_s if dur_s > 0 else 0
        print(f"{i:5d} {src:6} {len(text):5d} {dur_s:6.1f} {wall:7.1f} {rtf:5.2f}  {text[:40]!r}")
        rows.append((src, len(text), dur_s))
        wavs.append(wav)
        if pause_ms > 0:
            wavs.append(np.zeros(int(_SAMPLE_RATE * pause_ms / 1000), dtype=np.float32))

    wall_total = time.time() - t_start
    audio_total = sum(len(w) for w in wavs) / _SAMPLE_RATE
    rtf_total = wall_total / audio_total if audio_total > 0 else 0
    print(f"\nTotal render: {wall_total:.1f}s  audio: {audio_total:.1f}s  RTF: {rtf_total:.2f}x")

    combined = np.concatenate(wavs)
    wav_path = OUT_DIR / f"{label}.wav"
    wf.write(str(wav_path), _SAMPLE_RATE, combined)
    mp3_path = OUT_DIR / f"{label}.mp3"
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
    return rows, wall_total


# ── load chunks ────────────────────────────────────────────────────────────────
raw_chunks = []
total_ms = 0
for line in MANIFEST.read_text(encoding="utf-8").strip().split("\n"):
    c = json.loads(line)
    total_ms += c.get("duration_ms", 0) + c.get("pause_after_ms", 0)
    raw_chunks.append(c)
    if total_ms >= 60_000:
        break
print(f"Source chunks: {len(raw_chunks)} (~{total_ms/1000:.0f}s from 0.6B timings)")

# ── load model & latents ───────────────────────────────────────────────────────
print("Loading 1.7B model...")
t0 = time.time()
model = load_model(device="cpu")
latents = load_latents(LATENTS_PATH)
print(f"  ready in {time.time()-t0:.1f}s")

# ── run three variants ─────────────────────────────────────────────────────────
VARIANTS = [
    ("current", None),
    ("120",     120),
    ("80",      80),
]
summary = []
for label, max_chars in VARIANTS:
    frags = build_fragments(raw_chunks, max_chars)
    rows, wall = render_variant(label, frags, model, latents)
    summary.append((label, len(frags), wall))

# ── summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*40}")
print("SUMMARY")
print(f"{'variant':10} {'frags':6} {'wall_s':8}")
for label, nf, w in summary:
    print(f"{label:10} {nf:6d} {w:8.1f}s")
peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
print(f"Peak RAM: {peak_gb:.1f} GB")
print("FILES:")
for label, _, _ in summary:
    print(f"  {OUT_DIR}/{label}.mp3")
