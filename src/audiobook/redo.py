"""Per-chunk seed override: redo (render candidates) + accept (install + lock)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from audiobook import paths


def _sec_dir(section: str) -> Path:
    return paths.OUT / "sections" / section


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_manifest(path: Path, rows: list[dict]) -> None:
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def run_redo(config: dict, section: str, chunk_id: str, n_candidates: int) -> int:
    sec_dir = _sec_dir(section)
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"no manifest for section {section}")

    rows = _read_manifest(manifest_path)
    row = next((r for r in rows if r["id"] == chunk_id), None)
    if row is None:
        raise SystemExit(f"chunk {chunk_id!r} not found in {section}")

    out_dir = paths.OUT / "redo" / section / chunk_id
    out_dir.mkdir(parents=True, exist_ok=True)

    import soundfile as sf
    from audiobook.pronounce import load_table, respell
    from audiobook.synth import _SAMPLE_RATE, apply_sentinel, cap_params, seed_for_chunk
    from audiobook.worker import TimeoutSynth

    ref = paths.ROOT / config["reference"]["path"]
    rcfg = config.get("render", {})
    wcfg = {
        "device": "cpu",
        "latents_path": str(ref.with_suffix(".latents.pt")),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
    }
    sentinel = config["model"].get("sentinel", "")
    table = load_table()

    base_seed = seed_for_chunk(row["hash"])
    synth_text = apply_sentinel(respell(row["text"], table), sentinel)

    print(f"redo {section}/{chunk_id}: {row['text']!r}")
    print(f"base_seed={base_seed}, rendering {n_candidates} candidates")

    with TimeoutSynth(wcfg, rcfg.get("chunk_timeout_s", 600)) as engine:
        for i in range(1, n_candidates + 1):
            seed = base_seed + i * 100
            out_path = out_dir / f"variant_{i:02d}__seed+{i * 100}.wav"
            if out_path.exists():
                print(f"  variant {i:02d}  skip (exists)")
                continue
            wav = engine.synth(synth_text, seed)
            if wav is None:
                print(f"  variant {i:02d}  TIMEOUT")
                continue
            tmp = out_path.parent / (out_path.name + ".part")
            sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
            tmp.replace(out_path)
            dur = len(wav) / _SAMPLE_RATE
            print(f"  variant {i:02d}  seed+{i * 100}  {dur:.2f}s")

    print(f"\nListen: {out_dir}")
    print(f"Accept: audiobook accept {section} {chunk_id} <1..{n_candidates}>")
    return 0


def run_accept(config: dict, section: str, chunk_id: str, variant: int) -> int:
    sec_dir = _sec_dir(section)
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"no manifest for section {section}")

    redo_dir = paths.OUT / "redo" / section / chunk_id
    candidates = sorted(redo_dir.glob(f"variant_{variant:02d}__*.wav"))
    if not candidates:
        raise SystemExit(f"variant {variant:02d} not found in {redo_dir}")
    src_wav = candidates[0]

    m = re.search(r"seed\+(\d+)", src_wav.name)
    if not m:
        raise SystemExit(f"can't parse seed from {src_wav.name}")
    seed_offset = int(m.group(1))

    rows = _read_manifest(manifest_path)
    row = next((r for r in rows if r["id"] == chunk_id), None)
    if row is None:
        raise SystemExit(f"chunk {chunk_id!r} not found")

    import soundfile as sf
    from audiobook.synth import _SAMPLE_RATE, seed_for_chunk

    actual_seed = seed_for_chunk(row["hash"]) + seed_offset

    dst_wav = sec_dir / "chunks" / f"{chunk_id}.wav"
    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_wav.parent / (dst_wav.name + ".part")
    shutil.copy2(src_wav, tmp)
    tmp.replace(dst_wav)

    data, sr = sf.read(str(dst_wav))
    duration_ms = round(len(data) / sr * 1000)

    row["seed_override"] = actual_seed
    row["locked"] = True
    row["status"] = "done"
    row["duration_ms"] = duration_ms
    _write_manifest(manifest_path, rows)

    print(f"accepted {section}/{chunk_id}: variant {variant}, seed={actual_seed}, locked=True")
    return 0
