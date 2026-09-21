"""Stage 2 — pick voice reference.

Synthesises the same test passage with every candidate in ref/candidates/,
saves latents alongside the candidate wav, writes output wavs to out/ref_test/.
Prints a timing table. Does NOT pick a winner.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore

from audiobook import paths
from audiobook.device import pick_device
from audiobook.synth import compute_latents, load_model, save_latents, synthesize

_SAMPLE_RATE = 24000

# ── passage ──────────────────────────────────────────────────────────────────
_PASSAGE_FILE = (
    paths.TEXT
    / "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu.acc.txt"
)

# Lines 1-3 (1-indexed) of the acc.txt: first 3 plain narrative paragraphs.
_PASSAGE_LINE_SLICE = slice(0, 3)


def _load_passage() -> list[str]:
    lines = _PASSAGE_FILE.read_text(encoding="utf-8").splitlines()
    return [l for l in lines if l.strip()][_PASSAGE_LINE_SLICE]


# ── main ─────────────────────────────────────────────────────────────────────

def run(config: dict) -> int:
    device = pick_device()
    seed: int = config["model"]["seed"]
    temperature: float = config["model"]["temperature"]
    language: str = config["model"]["language"]

    candidates = sorted((paths.REF / "candidates").glob("*.wav"))
    if not candidates:
        print("ERROR: no .wav files in ref/candidates/")
        return 1

    out_dir = paths.OUT / "ref_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    passage_paras = _load_passage()
    passage = " ".join(passage_paras)
    print(f"Passage ({len(passage)} chars, {_PASSAGE_FILE.name} lines 1-3):")
    print(f"  {passage[:200]}")
    if len(passage) > 200:
        print(f"  …({len(passage) - 200} more chars)")
    print()
    print(f"Device: {device}  seed={seed}  temperature={temperature}")
    print(f"Candidates: {len(candidates)}")
    print()
    print("Loading XTTS-v2…")
    model = load_model(device)
    print("Model loaded.\n")

    header = f"{'Candidate':<14} {'Duration':>10} {'Wall time':>10} {'RTF':>7}"
    print(header)
    print("─" * len(header))

    rows: list[tuple[str, float, float, float]] = []
    for wav_path in candidates:
        name = wav_path.stem
        latents_path = wav_path.parent / f"{name}.latents.pt"

        latents = compute_latents(model, wav_path)
        save_latents(latents, latents_path)

        # Synthesise each paragraph separately to stay within XTTS token limits,
        # then concatenate. A 100ms silence separates paragraphs.
        silence = np.zeros(int(_SAMPLE_RATE * 0.1), dtype=np.float32)
        t0 = time.perf_counter()
        parts: list[np.ndarray] = []
        for para in passage_paras:
            parts.append(synthesize(model, para, latents, seed, temperature, language))
            parts.append(silence)
        wav = np.concatenate(parts[:-1])  # drop trailing silence
        wall_time = time.perf_counter() - t0

        duration = len(wav) / _SAMPLE_RATE
        rtf = wall_time / duration if duration > 0 else float("inf")

        out_path = out_dir / f"{name}.wav"
        sf.write(str(out_path), wav, _SAMPLE_RATE, subtype="PCM_16")

        print(f"{name:<14} {duration:>9.1f}s {wall_time:>9.1f}s {rtf:>7.2f}x")
        rows.append((name, duration, wall_time, rtf))

    print()
    avg_rtf = sum(r[3] for r in rows) / len(rows)
    print(f"Average RTF: {avg_rtf:.2f}x")
    print(f"Output: {out_dir}")
    print()
    print("Full passage:")
    print(passage)
    return 0
