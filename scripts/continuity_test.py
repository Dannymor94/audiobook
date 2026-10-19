"""
Rolling-context continuity test: render ch13 0015-0022 two ways.

  current  — cached wavs assembled as-is
  rolling  — each chunk re-synthesised conditioned on the previous chunk's
              audio tail (last 4 s) + its text, in Qwen ICL mode

out/continuity_test/{current,rolling}.mp3

Run on gamebox: uv run python scripts/continuity_test.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook import leadin, paths
from audiobook.assemble import _fade, _trim_silence
from audiobook.chunker import _split_sentences
from audiobook.master import master_section
from audiobook.pronounce import load_table, respell
from audiobook.synth import (
    _SAMPLE_RATE, _TERMINAL, _dict_to_items, _item_to_dict,
    apply_sentinel, cap_params, load_latents, load_model, max_tokens_for_text,
    seed_for_chunk, synthesize,
)

_SR = _SAMPLE_RATE
SEC = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
CHUNK_IDS = [f"{n:04d}" for n in range(15, 23)]  # 0015-0022
_ROLLING_TAIL_S = 4.0   # seconds of previous chunk audio used as ICL context
_CROSSFADE_MS = 0       # no fade: join_test showed it causes stutter


def _load_config() -> dict:
    import yaml  # type: ignore[import]
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _assemble(clips_with_pauses: list[tuple[np.ndarray, int]], fade_ms: int) -> np.ndarray:
    fade_samples = int(_SR * fade_ms / 1000)
    parts: list[np.ndarray] = []
    for i, (wav, pause_ms) in enumerate(clips_with_pauses):
        trimmed = _trim_silence(wav)
        last = i == len(clips_with_pauses) - 1
        parts.append(_fade(trimmed, fade_samples, leading=(i > 0), trailing=(not last)))
        if not last:
            parts.append(np.zeros(int(_SR * pause_ms / 1000), dtype=np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def _master_variant(name: str, wav: np.ndarray, config: dict, out_root: Path) -> Path:
    var_dir = out_root / name
    var_dir.mkdir(parents=True, exist_ok=True)
    sf.write(str(var_dir / "section.wav"), wav, _SR, subtype="PCM_16")
    mp3, _ = master_section(var_dir, config)
    dst = out_root / f"{name}.mp3"
    shutil.copy2(mp3, dst)
    return dst


def _rolling_latents(model, prev_wav: np.ndarray, prev_text: str,
                     tmp_path: Path) -> dict:
    """Compute ICL-mode latents from the tail of the previous chunk."""
    tail_start = max(0, len(prev_wav) - int(_SR * _ROLLING_TAIL_S))
    tail = prev_wav[tail_start:]
    sf.write(str(tmp_path), tail, _SR, subtype="PCM_16")
    # estimate the text that corresponds to the tail (last ~4s out of total)
    # rough heuristic: keep a proportional suffix of the text by characters
    total_s = len(prev_wav) / _SR
    frac = min(1.0, _ROLLING_TAIL_S / total_s) if total_s > 0 else 1.0
    n_keep = max(10, int(len(prev_text) * frac))
    tail_text = prev_text[-n_keep:]
    items = model.create_voice_clone_prompt(
        ref_audio=str(tmp_path),
        ref_text=tail_text,
        x_vector_only_mode=False,  # ICL mode: codec tokens as context
    )
    return {"items": [_item_to_dict(i) for i in items]}


def run() -> None:
    config = _load_config()
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    sec_dir = paths.OUT / "sections" / SEC
    manifest = _read_manifest(sec_dir / "manifest.jsonl")
    rows = {r["id"]: r for r in manifest}
    chunks_dir = sec_dir / "chunks"

    out_root = paths.OUT / "continuity_test"
    out_root.mkdir(parents=True, exist_ok=True)
    tmp_wav = out_root / "_rolling_ref_tmp.wav"

    ordered = [rows[cid] for cid in CHUNK_IDS]

    # ── CURRENT: read cached wavs ─────────────────────────────────────────────
    print("\n=== CURRENT: reading cached wavs ===")
    current_clips: list[tuple[np.ndarray, int]] = []
    for row in ordered:
        wav_path = chunks_dir / f"{row['id']}.wav"
        if not wav_path.exists():
            raise SystemExit(f"missing cached wav: {wav_path}")
        wav, _ = sf.read(str(wav_path), dtype="float32")
        current_clips.append((wav, row["pause_after_ms"]))
        print(f"  {row['id']}  {len(wav)/_SR:.2f}s  {row['text'][:50]!r}")

    current_wav = _assemble(current_clips, _CROSSFADE_MS)
    current_mp3 = _master_variant("current", current_wav, config, out_root)
    print(f"current.mp3 → {current_mp3}  ({len(current_wav)/_SR:.1f}s)")

    # ── ROLLING: re-synth with per-chunk rolling context ──────────────────────
    print("\n=== ROLLING: loading model ===")
    from audiobook.device import configure_cpu_threads
    configure_cpu_threads(workers=1)

    model = load_model("cpu")
    fixed_latents = load_latents(Path(config["reference"]["path"]).with_suffix(".latents.pt")
                                 if not Path(config["reference"]["path"]).with_suffix(".latents.pt").is_absolute()
                                 else Path(config["reference"]["path"]).with_suffix(".latents.pt"))
    # resolve relative path
    lat_path = paths.ROOT / config["reference"]["path"]
    lat_path = lat_path.with_suffix(".latents.pt")
    fixed_latents = load_latents(lat_path)

    rcfg = config.get("render", {})
    cap = cap_params(config)

    rolling_clips: list[tuple[np.ndarray, int]] = []
    prev_wav: np.ndarray | None = None
    prev_text: str | None = None

    # Seed the rolling context with the chunk BEFORE our window (0014) if cached.
    seed_chunk_path = chunks_dir / "0014.wav"
    if seed_chunk_path.exists():
        seed_wav, _ = sf.read(str(seed_chunk_path), dtype="float32")
        seed_row = rows.get("0014")
        if seed_row:
            prev_wav = seed_wav
            prev_text = seed_row["text"]
            print(f"  rolling seed: 0014  {len(seed_wav)/_SR:.2f}s  {seed_row['text'][:50]!r}")
    else:
        print("  rolling seed: using fixed reference (0014 not cached)")

    print("\n=== ROLLING: synthesising ===")
    for row in ordered:
        seed = seed_for_chunk(row["hash"])
        phrase = leadin.fires(row["text"], config)
        base = leadin.pad(row["text"], phrase) if phrase else row["text"]
        synth_text = apply_sentinel(respell(base, table), sentinel)

        # choose latents: rolling (ICL from prev chunk) or fixed
        if prev_wav is not None and prev_text is not None:
            t0 = time.perf_counter()
            try:
                lat = _rolling_latents(model, prev_wav, prev_text, tmp_wav)
                lat_ms = (time.perf_counter() - t0) * 1000
                lat_src = f"rolling (ICL from prev, {lat_ms:.0f}ms to compute)"
            except Exception as e:
                print(f"  WARNING: rolling latents failed ({e}), falling back to fixed")
                lat = fixed_latents
                lat_src = "fixed (fallback)"
        else:
            lat = fixed_latents
            lat_src = "fixed (no prev)"

        mnt = max_tokens_for_text(synth_text, **cap) if cap else None
        torch.manual_seed(seed)
        t0 = time.perf_counter()
        wav = synthesize(model, synth_text, lat, seed,
                         config["model"]["temperature"],
                         config["model"]["language"],
                         max_new_tokens=mnt)
        synth_ms = (time.perf_counter() - t0) * 1000

        # trim lead-in if fired
        if phrase:
            try:
                wav = leadin.trim_carrier(wav, synth_text, phrase)
            except leadin.TrimFailed as e:
                print(f"  WARNING: lead-in trim failed on {row['id']}: {e}")

        rolling_clips.append((wav, row["pause_after_ms"]))
        print(f"  {row['id']}  {len(wav)/_SR:.2f}s  synth={synth_ms:.0f}ms  lat={lat_src}")
        print(f"    text: {row['text'][:60]!r}")

        prev_wav = wav
        prev_text = row["text"]

    rolling_wav = _assemble(rolling_clips, _CROSSFADE_MS)
    rolling_mp3 = _master_variant("rolling", rolling_wav, config, out_root)
    print(f"\nrolling.mp3 → {rolling_mp3}  ({len(rolling_wav)/_SR:.1f}s)")

    tmp_wav.unlink(missing_ok=True)

    print("\n=== DONE ===")
    print(f"Output: {out_root}/{{current,rolling}}.mp3")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    run()
