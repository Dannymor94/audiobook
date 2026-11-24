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


def _meta_path(out_dir: Path) -> Path:
    return out_dir / "meta.json"


def _retire_stale_candidates(out_dir: Path, row: dict) -> None:
    """Candidates belong to one chunk TEXT (hash), not to a chunk id: a re-chunk
    can give id 0042 another text. If the folder holds candidates for another
    hash (or legacy ones without meta.json), move them to _old_<hash12>/ —
    never delete — and record the current hash."""
    meta = _meta_path(out_dir)
    have = sorted(out_dir.glob("variant_*.wav"))
    old_hash = None
    if meta.exists():
        old_hash = json.loads(meta.read_text(encoding="utf-8")).get("hash")
    if have and old_hash != row["hash"]:
        dst = out_dir / f"_old_{(old_hash or 'legacy')[:12]}"
        n = 1
        while dst.exists():
            dst = out_dir / f"_old_{(old_hash or 'legacy')[:12]}_{n}"
            n += 1
        dst.mkdir()
        for f in have:
            f.replace(dst / f.name)
        if meta.exists():
            meta.replace(dst / meta.name)
        print(f"  старые кандидаты (другой текст чанка) перенесены в {dst.name}/")
    tmp = meta.parent / (meta.name + ".tmp")
    tmp.write_text(json.dumps({"hash": row["hash"], "text": row["text"]},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(meta)


def run_redo(config: dict, section: str, chunk_id: str, n_candidates: int) -> int:
    sec_dir = _sec_dir(section)
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"no manifest for section {section}")

    rows = _read_manifest(manifest_path)
    row = next((r for r in rows if r["id"] == chunk_id), None)
    if row is None:
        raise SystemExit(f"chunk {chunk_id!r} not found in {section}")

    from audiobook.synth import ensure_manifest_current
    ensure_manifest_current(config, section)
    out_dir = paths.OUT / "redo" / section / chunk_id
    out_dir.mkdir(parents=True, exist_ok=True)
    _retire_stale_candidates(out_dir, row)

    import soundfile as sf

    from audiobook.pronounce import load_table
    from audiobook.synth import _SAMPLE_RATE, prepare_synth_text, row_leadin, seed_for_chunk, worker_config
    from audiobook.worker import TimeoutSynth

    rcfg = config.get("render", {})
    wcfg = worker_config(config)  # variant + its latents, same as render
    wcfg["device"] = "cpu"
    sentinel = config["model"].get("sentinel", "")
    table = load_table()

    base_seed = seed_for_chunk(row["hash"])
    synth_text, phrase = prepare_synth_text(row["text"], config, table, sentinel,
                                            row_leadin(row), row.get("open_end", False))
    synth_kw = {"leadin": phrase} if phrase else {}

    print(f"redo {section}/{chunk_id}: {row['text']!r}")
    print(f"base_seed={base_seed}, rendering {n_candidates} candidates"
          + (f" (lead-in: {phrase!r})" if phrase else ""))

    with TimeoutSynth(wcfg, rcfg.get("chunk_timeout_s", 600)) as engine:
        for i in range(1, n_candidates + 1):
            seed = base_seed + i * 100
            out_path = out_dir / f"variant_{i:02d}__seed+{i * 100}.wav"
            if out_path.exists():
                print(f"  variant {i:02d}  skip (exists)")
                continue
            wav = engine.synth(synth_text, seed, **synth_kw)
            if wav is None:
                print(f"  variant {i:02d}  TIMEOUT")
                continue
            tmp = out_path.parent / (out_path.name + ".part")
            sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="FLOAT", format="WAV")  # float: no clipping at write
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
    meta = _meta_path(redo_dir)
    cand_hash = (json.loads(meta.read_text(encoding="utf-8")).get("hash")
                 if meta.exists() else None)
    if cand_hash != row["hash"]:
        raise SystemExit(
            f"accept: кандидаты в {redo_dir} сделаны для другого текста чанка {chunk_id} "
            f"(или до появления meta.json) — сначала ./run.sh redo {section} {chunk_id}")

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


def run_accept_original(config: dict, section: str, chunk_id: str,
                        expected_hash: str, wav_sha256: str, actual_seed: int) -> int:
    """Lock an owner-reviewed existing manual WAV without replacing its bytes.

    The caller supplies the verified generation seed from local provenance,
    not merely the last attempted QC seed. Run only in an isolated work copy
    under the CLI heavy lock.
    """
    import numpy as np
    import soundfile as sf

    from audiobook import chunker, pronounce, voice_plan
    from audiobook.reviewed_stage import file_digest

    if (not re.fullmatch(r"[0-9]{2}_[A-Za-z0-9_-]+", section)
            or not re.fullmatch(r"[0-9]{4,}", chunk_id)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_hash)
            or not re.fullmatch(r"[0-9a-f]{64}", wav_sha256)
            or type(actual_seed) is not int or not 0 <= actual_seed < 2**63):
        raise ValueError("INVALID_ACCEPT_ORIGINAL_ARGUMENTS")
    config = chunker.section_config(config, section)
    sec_dir = _sec_dir(section)
    manifest_path = sec_dir / "manifest.jsonl"
    rows = _read_manifest(manifest_path)
    nn, slug = section.split("_", 1)
    voice_plan.plan_section(chunker.load_units(nn, slug), rows, config, pronounce.load_table())
    matches = [r for r in rows if r["id"] == chunk_id]
    if len(matches) != 1 or matches[0]["hash"] != expected_hash:
        raise ValueError("ACCEPT_ORIGINAL_HASH_MISMATCH")
    row = matches[0]
    if row.get("status") != "manual" or row.get("locked"):
        raise ValueError("ACCEPT_ORIGINAL_NOT_MANUAL")
    wav = sec_dir / "chunks" / f"{chunk_id}.wav"
    if not wav.is_file() or file_digest(wav) != wav_sha256:
        raise ValueError("ACCEPT_ORIGINAL_WAV_MISMATCH")
    data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    if sr != 24000 or data.shape[1] != 1 or not len(data) or not np.isfinite(data).all():
        raise ValueError("ACCEPT_ORIGINAL_INVALID_WAV")
    row.update(status="done", locked=True, seed=actual_seed,
               seed_override=actual_seed, duration_ms=round(len(data) * 1000 / sr))
    _write_manifest(manifest_path, rows)
    print(f"accepted original {section}/{chunk_id}: locked=True")
    return 0
