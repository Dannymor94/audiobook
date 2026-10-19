"""
Structural test: two experiments on ch13 chunks 0015-0022.

  EXPERIMENT 1 (sentinel): re-synth with sentinel forced on all terminal-punct chunks
  EXPERIMENT 2 (split): split at sentence + em-dash boundaries, synth sub-fragments

Variants assembled to out/structural_test/{current,sentinel,split,both}.mp3
+ per-word duration report for Experiment 1 (final-word truncation check).

Run on gamebox:  uv run python scripts/structural_test.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# must be importable after `uv run` from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook import leadin, paths
from audiobook.assemble import _fade, _trim_silence
from audiobook.chunker import _split_sentences
from audiobook.master import master_section, measure_lufs
from audiobook.pronounce import load_table, respell
from audiobook.synth import (
    _SAMPLE_RATE, _TERMINAL, apply_sentinel, cap_params, seed_for_chunk,
)
from audiobook.worker import TimeoutSynth

_SR = _SAMPLE_RATE   # 24000
SEC = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
CHUNK_IDS = [f"{n:04d}" for n in range(15, 23)]   # 0015-0022
PAUSE_SENT = 350   # ms between sub-fragments within an original chunk


def _load_config() -> dict:
    import yaml  # type: ignore[import]
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _split_at_boundaries(text: str) -> list[str]:
    """Split at depth-0 sentence boundaries AND em dashes."""
    sents = _split_sentences(text)
    parts: list[str] = []
    for s in sents:
        segs = [x.strip() for x in s.split("—") if x.strip()]
        parts.extend(segs if len(segs) > 1 else [s])
    return [p for p in parts if p]


def _prep(text: str, config: dict, table: dict, sentinel: str,
          force_sent: bool = False) -> tuple[str, str | None]:
    """Like prepare_synth_text but with optional forced sentinel."""
    phrase = leadin.fires(text, config)
    base = leadin.pad(text, phrase) if phrase else text
    rs = respell(base, table)
    if force_sent:
        synth_text = rs + sentinel
    else:
        synth_text = apply_sentinel(rs, sentinel)
    return synth_text, phrase


def _synth(engine, text: str, seed: int, config: dict, table: dict,
           sentinel: str, force_sent: bool = False) -> np.ndarray | None:
    synth_text, phrase = _prep(text, config, table, sentinel, force_sent)
    kw = {"leadin": phrase} if phrase else {}
    return engine.synth(synth_text, seed, **kw)


def _assemble(clips_with_pauses: list[tuple[np.ndarray, int]],
              fade_samples: int) -> np.ndarray:
    """clips_with_pauses = [(wav, pause_ms), ...]. Last pause is dropped."""
    parts: list[np.ndarray] = []
    for i, (wav, pause_ms) in enumerate(clips_with_pauses):
        trimmed = _trim_silence(wav)
        last = i == len(clips_with_pauses) - 1
        parts.append(_fade(trimmed, fade_samples, leading=(i > 0), trailing=(not last)))
        if not last:
            parts.append(np.zeros(int(_SR * pause_ms / 1000), dtype=np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def _master_variant(name: str, wav: np.ndarray, config: dict,
                    out_root: Path) -> Path:
    var_dir = out_root / name
    var_dir.mkdir(parents=True, exist_ok=True)
    wav_path = var_dir / "section.wav"
    sf.write(str(wav_path), wav, _SR, subtype="PCM_16")
    mp3, _ = master_section(var_dir, config)
    # copy to top-level for easy access
    dst = out_root / f"{name}.mp3"
    shutil.copy2(mp3, dst)
    return dst


# ── per-word duration report ──────────────────────────────────────────────────

def _word_report(row: dict, wav: np.ndarray, label: str) -> dict:
    """Whisper word-timestamp report: flag final word if ms/char < 45."""
    ts = leadin._word_ts(wav)
    if not ts:
        return {}
    report: dict[str, int] = {}
    for word, start, end in ts:
        dur_ms = round((end - start) * 1000)
        report[word] = dur_ms
    # flag final word
    last_word, last_start, last_end = ts[-1]
    dur_ms = round((last_end - last_start) * 1000)
    nch = len(last_word)
    flag = " !TRUNC" if nch and dur_ms / nch < 45 else ""
    report["_final"] = f"{last_word}={dur_ms}ms{flag}"
    return report


def run_experiment() -> None:
    config = _load_config()
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    sec_dir = paths.OUT / "sections" / SEC
    manifest = _read_manifest(sec_dir / "manifest.jsonl")
    rows = {r["id"]: r for r in manifest}
    chunks_dir = sec_dir / "chunks"

    out_root = paths.OUT / "structural_test"
    out_root.mkdir(parents=True, exist_ok=True)

    ordered = [rows[cid] for cid in CHUNK_IDS]
    rcfg = config.get("render", {})
    wcfg = {
        "device": "cpu",
        "latents_path": str((paths.ROOT / config["reference"]["path"]).with_suffix(".latents.pt")),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
    }
    fade_samples = int(_SR * config["pauses_ms"]["crossfade"] / 1000)

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

    current_wav = _assemble(current_clips, fade_samples)
    current_mp3 = _master_variant("current", current_wav, config, out_root)
    print(f"current.mp3 → {current_mp3}  ({len(current_wav)/_SR:.1f}s)")

    # ── SENTINEL / SPLIT / BOTH: need synthesis ───────────────────────────────
    with TimeoutSynth(wcfg, rcfg.get("chunk_timeout_s", 600)) as engine:

        # ── SENTINEL: re-synth all 8 with forced sentinel ─────────────────────
        print("\n=== SENTINEL: re-synth with sentinel forced ===")
        sentinel_clips: list[tuple[np.ndarray, int]] = []
        sentinel_wavs: dict[str, np.ndarray] = {}
        for row in ordered:
            seed = seed_for_chunk(row["hash"])
            wav = _synth(engine, row["text"], seed, config, table, sentinel, force_sent=True)
            if wav is None:
                raise SystemExit(f"timeout on {row['id']}")
            sentinel_clips.append((wav, row["pause_after_ms"]))
            sentinel_wavs[row["id"]] = wav
            dur = len(wav) / _SR
            cur_dur = len(current_clips[CHUNK_IDS.index(row["id"])][0]) / _SR
            print(f"  {row['id']}  {dur:.2f}s  (was {cur_dur:.2f}s)")

        sentinel_wav = _assemble(sentinel_clips, fade_samples)
        sentinel_mp3 = _master_variant("sentinel", sentinel_wav, config, out_root)
        print(f"sentinel.mp3 → {sentinel_mp3}  ({len(sentinel_wav)/_SR:.1f}s)")

        # ── SPLIT: split at boundaries, synth sub-fragments ───────────────────
        print("\n=== SPLIT: synthesising sub-fragments ===")
        split_clips: list[tuple[np.ndarray, int]] = []
        for row in ordered:
            parts = _split_at_boundaries(row["text"])
            base_seed = seed_for_chunk(row["hash"])
            print(f"  {row['id']}  {len(parts)} parts  {row['text'][:40]!r}")
            for pi, part in enumerate(parts):
                seed = base_seed + pi  # distinct seed per sub-fragment
                wav = _synth(engine, part, seed, config, table, sentinel, force_sent=False)
                if wav is None:
                    raise SystemExit(f"timeout on {row['id']} part {pi}")
                # pause after: PAUSE_SENT between parts, original pause after last
                is_last_part = pi == len(parts) - 1
                pause_ms = row["pause_after_ms"] if is_last_part else PAUSE_SENT
                split_clips.append((wav, pause_ms))
                print(f"    part {pi+1}: {len(part):3d}ch  {len(wav)/_SR:.2f}s  {part!r}")

        split_wav = _assemble(split_clips, fade_samples)
        split_mp3 = _master_variant("split", split_wav, config, out_root)
        print(f"split.mp3 → {split_mp3}  ({len(split_wav)/_SR:.1f}s)")

        # ── BOTH: split + forced sentinel ────────────────────────────────────
        print("\n=== BOTH: split sub-fragments + forced sentinel ===")
        both_clips: list[tuple[np.ndarray, int]] = []
        for row in ordered:
            parts = _split_at_boundaries(row["text"])
            base_seed = seed_for_chunk(row["hash"])
            for pi, part in enumerate(parts):
                seed = base_seed + pi
                wav = _synth(engine, part, seed, config, table, sentinel, force_sent=True)
                if wav is None:
                    raise SystemExit(f"timeout on {row['id']} part {pi}")
                is_last_part = pi == len(parts) - 1
                pause_ms = row["pause_after_ms"] if is_last_part else PAUSE_SENT
                both_clips.append((wav, pause_ms))

        both_wav = _assemble(both_clips, fade_samples)
        both_mp3 = _master_variant("both", both_wav, config, out_root)
        print(f"both.mp3 → {both_mp3}  ({len(both_wav)/_SR:.1f}s)")

    # ── PER-WORD DURATION REPORT (Experiment 1 sentinel effect) ──────────────
    print("\n=== PER-WORD DURATIONS: Experiment 1 — final word in terminal-punct chunks ===")
    print(f"(chunks ending in '.', flagged if final word < 45ms/char = !TRUNC)")
    for row in ordered:
        last = row["text"].rstrip()
        if not last or last[-1] not in _TERMINAL:
            continue
        idx = CHUNK_IDS.index(row["id"])
        cur_wav = current_clips[idx][0]
        sen_wav = sentinel_wavs[row["id"]]
        cur_ts = leadin._word_ts(cur_wav)
        sen_ts = leadin._word_ts(sen_wav)

        def fmt_ts(ts):
            if not ts:
                return "(no timestamps)"
            words_fmt = []
            for w, s, e in ts:
                dur = round((e - s) * 1000)
                nch = len(w)
                flag = "!TRUNC" if nch and dur / nch < 45 else ""
                words_fmt.append(f"{w}={dur}ms{flag}")
            return "  ".join(words_fmt)

        print(f"\n  {row['id']}  {row['text']!r}")
        print(f"    current:  {fmt_ts(cur_ts)}")
        print(f"    sentinel: {fmt_ts(sen_ts)}")

    print("\n=== DONE ===")
    print(f"Output: {out_root}/{{current,sentinel,split,both}}.mp3")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    run_experiment()
