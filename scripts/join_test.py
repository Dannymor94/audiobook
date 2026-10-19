"""
Join artifact test: re-synth split sub-fragments, diagnose onset amplitudes,
assemble three ways with different fade settings.

    out/join_test/frags/      individual sub-fragment wavs
    out/join_test/20ms.mp3    current crossfade (20ms fade-in/out)
    out/join_test/5ms.mp3     short fade (5ms)
    out/join_test/none.mp3    butt-join, no fade (trim only)

Run on gamebox: uv run python scripts/join_test.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook import leadin, paths
from audiobook.assemble import _fade, _trim_silence
from audiobook.chunker import _split_sentences
from audiobook.master import master_section
from audiobook.pronounce import load_table, respell
from audiobook.synth import _SAMPLE_RATE, apply_sentinel, cap_params, seed_for_chunk
from audiobook.worker import TimeoutSynth

_SR = _SAMPLE_RATE
SEC = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
CHUNK_IDS = [f"{n:04d}" for n in range(15, 23)]
PAUSE_SENT = 350  # ms between sub-fragments within an original chunk


def _load_config() -> dict:
    import yaml  # type: ignore[import]
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _split_at_boundaries(text: str) -> list[str]:
    sents = _split_sentences(text)
    parts: list[str] = []
    for s in sents:
        segs = [x.strip() for x in s.split("—") if x.strip()]
        parts.extend(segs if len(segs) > 1 else [s])
    return [p for p in parts if p]


def _prep(text: str, config: dict, table: dict, sentinel: str) -> tuple[str, str | None]:
    phrase = leadin.fires(text, config)
    base = leadin.pad(text, phrase) if phrase else text
    rs = respell(base, table)
    return apply_sentinel(rs, sentinel), phrase


def _assemble(clips_with_pauses: list[tuple[np.ndarray, int]],
              fade_samples: int) -> np.ndarray:
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
    wav_path = var_dir / "section.wav"
    sf.write(str(wav_path), wav, _SR, subtype="PCM_16")
    mp3, _ = master_section(var_dir, config)
    dst = out_root / f"{name}.mp3"
    shutil.copy2(mp3, dst)
    return dst


def _onset_report(wav: np.ndarray, label: str) -> None:
    """Print amplitude in 10ms frames for first 60ms, before and after trim."""
    frame = int(_SR * 0.010)
    raw_frames = min(6, len(wav) // frame)
    raw_amps = [float(np.abs(wav[i*frame:(i+1)*frame]).max()) for i in range(raw_frames)]

    trimmed = _trim_silence(wav)
    tr_frames = min(6, len(trimmed) // frame)
    tr_amps = [float(np.abs(trimmed[i*frame:(i+1)*frame]).max()) for i in range(tr_frames)]

    raw_str = "  ".join(f"{a:.3f}" for a in raw_amps)
    tr_str = "  ".join(f"{a:.3f}" for a in tr_amps)
    print(f"    {label}")
    print(f"      raw  onset [10ms frames]: {raw_str}")
    print(f"      trim onset [10ms frames]: {tr_str}")
    # flag if first frame post-trim is quiet (likely pre-phonation survived)
    if tr_amps and tr_amps[0] < 0.05:
        print(f"      *** first trim frame quiet ({tr_amps[0]:.3f}) — onset may be residual ***")


def run() -> None:
    config = _load_config()
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    sec_dir = paths.OUT / "sections" / SEC
    manifest = _read_manifest(sec_dir / "manifest.jsonl")
    rows = {r["id"]: r for r in manifest}

    out_root = paths.OUT / "join_test"
    frags_dir = out_root / "frags"
    frags_dir.mkdir(parents=True, exist_ok=True)

    ordered = [rows[cid] for cid in CHUNK_IDS]
    rcfg = config.get("render", {})
    wcfg = {
        "device": "cpu",
        "latents_path": str((paths.ROOT / config["reference"]["path"]).with_suffix(".latents.pt")),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
    }

    # collect (wav, pause_ms, chunk_id, part_idx, text) for all sub-fragments
    Fragment = tuple  # (wav, pause_ms, chunk_id, part_idx, text)
    frags: list[Fragment] = []

    print("\n=== SYNTH sub-fragments ===")
    with TimeoutSynth(wcfg, rcfg.get("chunk_timeout_s", 600)) as engine:
        for row in ordered:
            parts = _split_at_boundaries(row["text"])
            base_seed = seed_for_chunk(row["hash"])
            print(f"  {row['id']}  {len(parts)} parts")
            for pi, part in enumerate(parts):
                seed = base_seed + pi
                synth_text, phrase = _prep(part, config, table, sentinel)
                kw = {"leadin": phrase} if phrase else {}
                wav = engine.synth(synth_text, seed, **kw)
                if wav is None:
                    raise SystemExit(f"timeout on {row['id']} part {pi}")
                is_last = pi == len(parts) - 1
                pause_ms = row["pause_after_ms"] if is_last else PAUSE_SENT
                frags.append((wav, pause_ms, row["id"], pi, part))
                # save individual wav
                frag_name = f"{row['id']}_p{pi:02d}.wav"
                sf.write(str(frags_dir / frag_name), wav, _SR, subtype="PCM_16")
                print(f"    p{pi}: {len(part):3d}ch  {len(wav)/_SR:.2f}s  {part!r}")

    # ── DIAGNOSTIC: onset of each fragment ──────────────────────────────────────
    print("\n=== ONSET DIAGNOSTIC (10ms amplitude frames, raw + after trim) ===")
    for i, (wav, pause_ms, cid, pi, text) in enumerate(frags):
        label = f"frag {i:02d}  [{cid} p{pi}]  {text[:35]!r}"
        _onset_report(wav, label)

    # also check tail of each N and onset of N+1 at join boundaries
    print("\n=== JOIN BOUNDARIES (tail of N, onset of N+1) ===")
    for i in range(len(frags) - 1):
        wav_n = frags[i][0]
        wav_n1 = frags[i+1][0]
        trimmed_n = _trim_silence(wav_n)
        # tail: last 50ms
        tail_start = max(0, len(trimmed_n) - int(_SR * 0.050))
        tail_amp = float(np.abs(trimmed_n[tail_start:]).max())
        # onset of N+1: first 50ms raw
        onset_end = min(len(wav_n1), int(_SR * 0.050))
        onset_amp = float(np.abs(wav_n1[:onset_end]).max())
        onset_trim = _trim_silence(wav_n1)
        onset_trim_amp = float(np.abs(onset_trim[:onset_end]).max()) if len(onset_trim) >= onset_end else 0.0
        n_text = frags[i][4][:20]
        n1_text = frags[i+1][4][:20]
        pause_here = frags[i][1]
        print(f"  [{i:02d}→{i+1:02d}] pause={pause_here}ms  "
              f"tail_max={tail_amp:.3f}  onset_raw_max={onset_amp:.3f}  onset_trim_max={onset_trim_amp:.3f}  "
              f"'{n_text}' → '{n1_text}'")

    # ── ASSEMBLE three ways ──────────────────────────────────────────────────────
    clips = [(wav, pause_ms) for wav, pause_ms, *_ in frags]

    for label, ms in [("20ms", 20), ("5ms", 5), ("none", 0)]:
        fs = int(_SR * ms / 1000)
        wav = _assemble(clips, fs)
        mp3 = _master_variant(label, wav, config, out_root)
        print(f"\n{label}.mp3 → {mp3}  ({len(wav)/_SR:.1f}s)")

    print("\n=== DONE ===")
    print(f"Output: {out_root}/{{20ms,5ms,none}}.mp3")
    print(f"Frags:  {frags_dir}/")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    run()
