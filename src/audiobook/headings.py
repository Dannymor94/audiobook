"""Render all section headings to out/headings_check_v2/ for stress/accent review.

Each heading is synthesised with the frozen production config (model, reference,
temperature, cap, and retries identical to the main pipeline). Writes:
  NNN__<section>__<slug>.wav  — one per heading (resume: skips existing files)
  index.txt                   — filename TAB text, one line per heading
  all_headings.mp3            — concatenated, mastered (eq3 + loudnorm), 1.5 s gaps
  all_headings.txt            — timestamp index: mm:ss TAB section TAB text

Prints a stats report: cap hits, retries, timeouts, wall time.
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from audiobook import paths
from audiobook.chunker import chunk_hash
from audiobook.master import _loudnorm_measure, _ff
from audiobook.pronounce import load_table, respell
from audiobook.synth import (
    _SAMPLE_RATE, apply_sentinel, cap_params, load_latents, seed_for_chunk,
)
from audiobook.text_blocks import cyrillic_slug
from audiobook.worker import TimeoutSynth

log = logging.getLogger(__name__)

_GAP_S = 1.5
_OUT = paths.OUT / "headings_check_v2"


def _collect_headings(config: dict) -> list[tuple[str, str]]:
    """Return [(section_id, heading_text), …] in document order."""
    from audiobook.chunker import load_units

    headings: list[tuple[str, str]] = []
    for jf in sorted((paths.TEXT / "blocks").glob("*.blocks.json")):
        d = json.loads(jf.read_text(encoding="utf-8"))
        nn, slug = d["nn"], d["slug"]
        normf = paths.TEXT / f"{nn}_{slug}.norm.txt"
        if not normf.exists() or normf.stat().st_size < 50:
            continue
        for u in load_units(nn, slug):
            if u["type"] == "heading":
                headings.append((f"{nn}_{slug}", u["text"]))
    return headings


def _heading_hash(text: str, config: dict) -> str:
    from audiobook.chunker import latents_hash
    m = config["model"]
    lat = latents_hash(config)
    table = load_table()
    synth_text = respell(text, table)
    return chunk_hash(text, m["name"], m["seed"], m["temperature"],
                      m["language"], lat, synth_text if synth_text != text else None)


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _master_concat(raw: Path, out_mp3: Path, config: dict) -> None:
    """Two-pass loudnorm + eq3 chain → 192k CBR mp3."""
    m = config["master"]
    I, tp, lra = float(m["lufs"]), float(m["true_peak"]), 11.0
    sr = int(m["sample_rate"])
    eq = m.get("eq_filters", "")
    ff = _ff()

    meas = _loudnorm_measure(ff, raw, I, tp, lra, eq)
    mid = f",{eq}" if eq else ""
    af = (
        f"highpass=f={int(m['highpass_hz'])}{mid},"
        f"loudnorm=I={I}:TP={tp}:LRA={lra}:"
        f"measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
        f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
        f"offset={meas['target_offset']}:linear=true"
    )
    subprocess.run(
        [ff, "-hide_banner", "-y", "-i", str(raw), "-af", af, "-ar", str(sr),
         "-c:a", "libmp3lame", "-b:a", "192k", "-id3v2_version", "3", str(out_mp3)],
        capture_output=True, check=True,
    )


def run(config: dict) -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    headings = _collect_headings(config)
    print(f"headings={len(headings)}  -> {_OUT}")

    ref = paths.ROOT / config["reference"]["path"]
    lat_path = ref.with_suffix(".latents.pt")
    rcfg = config.get("render", {})
    wcfg = {
        "device": "cpu",  # portability: Ryzen render target is CPU
        "latents_path": str(lat_path),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
    }
    timeout_s = rcfg.get("chunk_timeout_s", 600)
    retries = rcfg.get("timeout_retries", 6)
    sentinel = config["model"].get("sentinel", "")
    table = load_table()

    # Stats
    n_synth = n_skip = n_cap = n_timeout = total_retries = 0
    timeout_chunks: list[str] = []

    wav_files: list[Path] = []  # in order, for concat
    wavnames: list[str] = []    # for index.txt
    texts: list[str] = []
    sections: list[str] = []

    t0 = time.perf_counter()
    with TimeoutSynth(wcfg, timeout_s) as engine:
        for i, (sec, text) in enumerate(headings, start=1):
            slug = cyrillic_slug(text)
            name = f"{i:03d}__{sec}__{slug}.wav"
            wav_path = _OUT / name

            if wav_path.exists():
                n_skip += 1
            else:
                synth_text = apply_sentinel(respell(text, table), sentinel)
                h = _heading_hash(text, config)
                base_seed = seed_for_chunk(h)

                wav = None
                for attempt in range(retries + 1):
                    seed = base_seed + attempt
                    wav = engine.synth(synth_text, seed)
                    if wav is not None:
                        if attempt > 0:
                            n_cap += 1
                            total_retries += attempt
                        break
                    total_retries += 1

                if wav is None:
                    n_timeout += 1
                    timeout_chunks.append(f"{i:03d} {text!r}")
                    log.warning("heading %03d timed out (all %d attempts): %r", i, retries + 1, text)
                    # write 0.5s silence placeholder so concat stays intact
                    wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)

                tmp = wav_path.parent / (wav_path.name + ".part")
                sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
                tmp.replace(wav_path)
                n_synth += 1

            wav_files.append(wav_path)
            wavnames.append(name)
            texts.append(text)
            sections.append(sec)

            if i % 50 == 0:
                elapsed = time.perf_counter() - t0
                print(f"  {i}/{len(headings)}  ({elapsed:.0f}s, "
                      f"cap_chunks={n_cap}, timeouts={n_timeout})")

    wall = time.perf_counter() - t0

    # Build index.txt
    index_path = _OUT / "index.txt"
    with open(index_path, "w", encoding="utf-8") as f:
        for name, text in zip(wavnames, texts):
            f.write(f"{name}\t{text}\n")

    # Concatenate with gaps
    gap = np.zeros(int(_SAMPLE_RATE * _GAP_S), dtype=np.float32)
    parts: list[np.ndarray] = []
    ts_entries: list[tuple[float, str, str]] = []
    cursor = 0.0
    for wav_path, sec, text in zip(wav_files, sections, texts):
        data, _ = sf.read(str(wav_path), dtype="float32")
        if data.ndim > 1:
            data = data[:, 0]
        ts_entries.append((cursor, sec, text))
        parts.append(data)
        parts.append(gap)
        cursor += len(data) / _SAMPLE_RATE + _GAP_S
    concat = np.concatenate(parts[:-1]) if parts else np.zeros(0, dtype=np.float32)

    raw_wav = _OUT / "all_headings_raw.wav"
    sf.write(str(raw_wav), concat, _SAMPLE_RATE, subtype="PCM_16")

    all_mp3 = _OUT / "all_headings.mp3"
    _master_concat(raw_wav, all_mp3, config)
    raw_wav.unlink()

    # Timestamp index
    ts_path = _OUT / "all_headings.txt"
    total_dur_s = len(concat) / _SAMPLE_RATE
    with open(ts_path, "w", encoding="utf-8") as f:
        total_min = int(total_dur_s) // 60
        total_sec = int(total_dur_s) % 60
        f.write(f"# {len(headings)} headings, {total_min:02d}:{total_sec:02d} total, "
                f"{_GAP_S:.1f}s gaps\n")
        f.write("# mm:ss\tsection\theading\n")
        for ts, sec, text in ts_entries:
            f.write(f"{_fmt_ts(ts)}\t{sec}\t{text}\n")

    # Report
    print(f"\n=== headings_check_v2 report ===")
    print(f"total={len(headings)}  synth={n_synth}  skip={n_skip}  "
          f"timeout={n_timeout}  wall={wall:.0f}s")
    print(f"chunks with cap-hit retries: {n_cap}  total extra attempts: {total_retries}")
    print(f"runaway rate: {n_cap}/{n_synth} = {n_cap/max(n_synth,1)*100:.0f}% of synthesised")
    if n_timeout:
        print(f"TIMEOUTS ({n_timeout}) — each cost 600s × 7 attempts ~ 1.2 h per heading:")
        for t in timeout_chunks:
            print(f"  {t}")
    print(f"all_headings.mp3  -> {all_mp3}  ({total_dur_s/60:.1f} min)")
    print(f"all_headings.txt  -> {ts_path}")
    return 0
