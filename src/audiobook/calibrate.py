"""Speed and pause calibration grids.

Grid 1 (ref_test2): All candidates, .norm.txt, speed=1.0 → out/ref_test2/<name>.wav
Grid 2 (speed_test): Candidate 01, speed ∈ {1.0, 0.95, 0.90, 0.85} → out/speed_test/<speed>.wav
Grid 3 (pause_test): Candidate 01, speed=0.95, sentence pause ∈ {350, 500, 650} ms
                     Edge-silence trimming before pause insertion. → out/pause_test/<ms>.wav

Constraints (CLAUDE.md / PROJECT §5.6):
  - .norm.txt only (no stress marks)
  - trim silence before inserting pauses
  - 20ms crossfade at joins
  - do NOT write to config.yaml
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore

from audiobook import paths
from audiobook.chunker import chunk_prose, _split_sentences
from audiobook.device import pick_device
from audiobook.synth import (
    apply_sentinel,
    compute_latents,
    load_latents,
    load_model,
    save_latents,
    synthesize,
)

_SR = 24_000
_FADE_SAMPLES = int(_SR * 0.020)   # 20 ms crossfade
_PARA_PAUSE_MS = 900

_NORM_FILE = (
    paths.TEXT / "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu.norm.txt"
)
_CANDIDATE_01 = paths.REF / "candidates" / "01.wav"
_LATENTS_01   = paths.REF / "candidates" / "01.latents.pt"


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_passage() -> list[str]:
    """First 3 non-empty lines from .norm.txt (heading + 2 paragraphs)."""
    lines = _NORM_FILE.read_text(encoding="utf-8").splitlines()
    return [l for l in lines if l.strip()][:3]


def _trim_silence(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """Trim leading/trailing frames below amplitude threshold (10 ms frames)."""
    frame = int(_SR * 0.010)
    if len(audio) < frame:
        return audio
    n_frames = len(audio) // frame
    amps = [float(np.max(np.abs(audio[i * frame:(i + 1) * frame])))
            for i in range(n_frames)]
    loud = [i for i, a in enumerate(amps) if a > threshold]
    if not loud:
        return audio
    return audio[loud[0] * frame:(loud[-1] + 1) * frame]


def _fade(clip: np.ndarray, leading: bool, trailing: bool) -> np.ndarray:
    """Apply 20 ms linear fade-in / fade-out in-place."""
    c = clip.copy()
    fade = min(_FADE_SAMPLES, len(c) // 4)
    if fade <= 0:
        return c
    if leading:
        c[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    if trailing:
        c[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return c


def _join(clips: list[np.ndarray], pause_samples: int) -> np.ndarray:
    """Concatenate clips: fade-out → silence → fade-in at each join."""
    if not clips:
        return np.array([], dtype=np.float32)
    parts: list[np.ndarray] = []
    for i, clip in enumerate(clips):
        parts.append(_fade(clip, leading=(i > 0), trailing=(i < len(clips) - 1)))
        if i < len(clips) - 1:
            parts.append(np.zeros(pause_samples, dtype=np.float32))
    return np.concatenate(parts)


def _get_latents_01(model) -> dict:
    if _LATENTS_01.exists():
        return load_latents(_LATENTS_01)
    lat = compute_latents(model, _CANDIDATE_01)
    save_latents(lat, _LATENTS_01)
    return lat


# ── grids ─────────────────────────────────────────────────────────────────────

def _grid1_ref_test2(model, passage: list[str], seed: int, temperature: float,
                     language: str) -> None:
    print("═" * 62)
    print("Grid 1 — candidate comparison (.norm.txt, speed=1.0)")
    print("═" * 62)
    out = paths.OUT / "ref_test2"
    out.mkdir(parents=True, exist_ok=True)

    candidates = sorted((paths.REF / "candidates").glob("*.wav"))
    if not candidates:
        print("  ERROR: ref/candidates/ is empty")
        return

    silence = np.zeros(int(_SR * 0.1), dtype=np.float32)
    hdr = f"  {'Candidate':<14} {'Duration':>10} {'Wall':>10} {'RTF':>7}"
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))

    for wav_path in candidates:
        name = wav_path.stem
        lat_path = wav_path.parent / f"{name}.latents.pt"
        latents = load_latents(lat_path) if lat_path.exists() \
            else compute_latents(model, wav_path)
        if not lat_path.exists():
            save_latents(latents, lat_path)

        t0 = time.perf_counter()
        parts = []
        for para in passage:
            parts.append(synthesize(model, para, latents, seed, temperature, language))
            parts.append(silence)
        wav = np.concatenate(parts[:-1])
        wall = time.perf_counter() - t0

        dur = len(wav) / _SR
        sf.write(str(out / f"{name}.wav"), wav, _SR, subtype="PCM_16")
        rtf = wall / dur if dur else float("inf")
        print(f"  {name:<14} {dur:>9.1f}s {wall:>9.1f}s {rtf:>7.2f}x")

    print(f"  → {out}\n")


def _grid2_speed_test(model, passage: list[str], seed: int, temperature: float,
                      language: str) -> None:
    print("═" * 62)
    print("Grid 2 — speed grid (candidate 01)")
    print("═" * 62)
    out = paths.OUT / "speed_test"
    out.mkdir(parents=True, exist_ok=True)

    latents = _get_latents_01(model)
    silence = np.zeros(int(_SR * 0.1), dtype=np.float32)
    speeds = [1.0, 0.95, 0.90, 0.85]

    hdr = f"  {'Speed':>7} {'Duration':>10} {'Wall':>10} {'RTF':>7}"
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))

    for speed in speeds:
        t0 = time.perf_counter()
        parts = []
        for para in passage:
            parts.append(synthesize(model, para, latents, seed, temperature,
                                    language, speed=speed))
            parts.append(silence)
        wav = np.concatenate(parts[:-1])
        wall = time.perf_counter() - t0

        dur = len(wav) / _SR
        rtf = wall / dur if dur else float("inf")
        fname = f"{speed:.2f}.wav"
        sf.write(str(out / fname), wav, _SR, subtype="PCM_16")
        print(f"  {speed:>7.2f} {dur:>9.1f}s {wall:>9.1f}s {rtf:>7.2f}x")

    # RTF note: slower speed → longer audio → lower RTF (compute cost is ~constant)
    print(f"  Note: RTF drops at lower speeds — same compute, more output seconds.")
    print(f"  → {out}\n")


def _grid3_pause_test(model, passage: list[str], seed: int, temperature: float,
                      language: str, sentinel: str) -> None:
    print("═" * 62)
    print("Grid 3 — pause grid (candidate 01, speed=0.95)")
    print("  Trim silence → insert pause → crossfade 20ms")
    print("═" * 62)
    out = paths.OUT / "pause_test"
    out.mkdir(parents=True, exist_ok=True)

    latents = _get_latents_01(model)

    # Split each paragraph into individual sentences so the grid has real
    # inter-sentence boundaries to test. chunk_prose packs sentences together
    # when paragraphs are short (< TARGET), leaving no "sent" boundaries.
    chunks: list[tuple[str, str]] = []
    for pi, para in enumerate(passage):
        sents = _split_sentences(para) or [para]
        last_para = (pi == len(passage) - 1)
        for si, sent in enumerate(sents):
            last_in_para = (si == len(sents) - 1)
            if last_in_para and not last_para:
                ptype = "para"
            elif last_in_para and last_para:
                ptype = "end"
            else:
                ptype = "sent"
            chunks.append((sent, ptype))

    print(f"  Chunks: {len(chunks)}")
    for txt, pt in chunks:
        print(f"    [{pt}] {txt[:72]}{'…' if len(txt) > 72 else ''}")
    print()

    # Synthesise all chunks once (shared across pause variants)
    print("  Synthesising chunks at speed=0.95…")
    raw_wavs: list[np.ndarray] = []
    for txt, _ in chunks:
        audio = synthesize(model, apply_sentinel(txt, sentinel),
                           latents, seed, temperature, language, speed=0.95)
        raw_wavs.append(audio)

    # Trim silence — §5.6: trim BEFORE pause insertion
    print("  Trimming silence…")
    trimmed: list[np.ndarray] = []
    trim_amounts_ms: list[float] = []
    for raw in raw_wavs:
        t = _trim_silence(raw)
        trimmed.append(t)
        trim_amounts_ms.append((len(raw) - len(t)) / _SR * 1000)

    avg_trim = sum(trim_amounts_ms) / len(trim_amounts_ms)
    # " ." produces only a prosodic pause (no phoneme), so it falls below the
    # silence threshold and is trimmed along with trailing silence.
    # avg_trimmed reflects trailing silence only; nothing extra is expected.
    print(f"  Avg trimmed per chunk: {avg_trim:.0f}ms  (trailing silence only for ' .' sentinel)")
    print()

    para_samples = int(_SR * _PARA_PAUSE_MS / 1000)

    for pause_ms in [350, 500, 650]:
        sent_samples = int(_SR * pause_ms / 1000)
        parts: list[np.ndarray] = []
        for i, (clip, (_, ptype)) in enumerate(zip(trimmed, chunks)):
            parts.append(_fade(clip,
                               leading=(i > 0),
                               trailing=(ptype != "end")))
            if ptype == "sent":
                parts.append(np.zeros(sent_samples, dtype=np.float32))
            elif ptype == "para":
                parts.append(np.zeros(para_samples, dtype=np.float32))
            # "end" → no trailing pause

        wav = np.concatenate(parts)
        dur = len(wav) / _SR
        sf.write(str(out / f"{pause_ms}.wav"), wav, _SR, subtype="PCM_16")
        print(f"  pause={pause_ms}ms  dur={dur:.1f}s  → {out / f'{pause_ms}.wav'}")

    print(f"  → {out}\n")


# ── entry point ───────────────────────────────────────────────────────────────

def run(config: dict) -> int:
    if not _NORM_FILE.exists():
        print(f"ERROR: passage file missing: {_NORM_FILE}")
        return 1
    if not _CANDIDATE_01.exists():
        print(f"ERROR: candidate 01 missing: {_CANDIDATE_01}")
        return 1

    seed: int = config["model"]["seed"]
    temperature: float = config["model"]["temperature"]
    language: str = config["model"]["language"]
    sentinel: str = config["model"].get("sentinel", "")

    passage = _load_passage()
    print(f"Passage ({len(passage)} lines from {_NORM_FILE.name}):")
    for i, l in enumerate(passage, 1):
        print(f"  [{i}] {l[:90]}{'…' if len(l) > 90 else ''}")
    print()

    device = pick_device()
    print(f"Device: {device}  seed={seed}  temperature={temperature}")
    print("Loading XTTS-v2…")
    model = load_model(device)
    print("Model loaded.\n")

    _grid1_ref_test2(model, passage, seed, temperature, language)
    _grid2_speed_test(model, passage, seed, temperature, language)
    _grid3_pause_test(model, passage, seed, temperature, language, sentinel)

    print("All grids complete.")
    return 0
