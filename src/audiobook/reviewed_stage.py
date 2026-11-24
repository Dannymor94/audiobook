"""Stage owner-reviewed WAVs against exact candidate inputs, without touching live output.

Receipts are private operator attestations reconstructed from actual trial evidence,
not generated from the desired candidate. No TTS, no production promotion.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from audiobook import chunker, paths, voice_plan


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def generation_identity(config: dict) -> dict:
    """Compare the recorded local model/voice and generation settings, not paths."""
    from audiobook import synth, voicecfg

    worker = synth.worker_config(config, 1)
    worker.pop("latents_path")
    worker["device"] = "cpu"
    return {
        "worker": worker,
        "model_id": voicecfg.model_id(config),
        "snapshot": synth._local_snapshot(voicecfg.variant(config)).name,
        "latents_sha256": file_digest(voicecfg.latents_path(config)),
        "reference_sha256": file_digest(paths.ROOT / config["reference"]["path"]),
    }


def input_identity(row: dict, config: dict, table: dict) -> dict:
    from audiobook import synth

    text, phrase = synth.prepare_synth_text(
        row["text"], config, table, config["model"].get("sentinel", ""),
        synth.row_leadin(row), row["open_end"])
    return {"input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "leadin": phrase}


def _verified_trial(receipt: dict, row: dict, config: dict, table: dict,
                    generation: dict) -> tuple[Path, int, int]:
    import numpy as np
    import soundfile as sf

    seed = receipt.get("seed")
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("INVALID_TRIAL_SEED")
    if (receipt.get("generation") != generation
            or receipt.get("input") != input_identity(row, config, table)):
        raise ValueError("TRIAL_INPUT_OR_GENERATION_MISMATCH")
    wav = Path(receipt["wav"])
    if file_digest(wav) != receipt.get("wav_sha256"):
        raise ValueError("TRIAL_WAV_DIGEST_MISMATCH")
    data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    if sr != 24000 or data.shape[1] != 1 or not len(data) or not np.isfinite(data).all():
        raise ValueError("INVALID_TRIAL_WAV")
    return wav, seed, round(len(data) * 1000 / sr)


def stage_section(section: str, tag: str, config: dict, table: dict,
                  rules: dict, receipts: dict, *, chapter_title_carrier: bool = True) -> Path:
    """Copy a current section into a NEW private stage, adopting reviewed changes.

    Every changed hash must have an explicitly supplied accepted receipt.
    Retain actual seeds and lock reviewed WAVs. No live writes, no orphan moves.
    READY.json is written last; a partial stage must never be promoted.
    Caller must ensure an idle local renderer and trusted trial evidence.
    """
    if (not re.fullmatch(r"[0-9]{2}_[A-Za-z0-9_-]+", section)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", tag)):
        raise ValueError("INVALID_STAGE_NAME")
    nn, slug = section.split("_", 1)
    config = chunker.section_config(config, section)
    live = paths.OUT / "sections" / section
    units = chunker.load_units(nn, slug)
    old = chunker._read_manifest(live / "manifest.jsonl")
    plan = voice_plan.plan_section(units, old, config, table, rules=rules,
                                  chapter_title_carrier=chapter_title_carrier)
    if plan["blocked"]:
        raise ValueError("BLOCKED_HASH_GAP")
    changed = {r["id"] for r in plan["rows"] if r["hash_changed"]}
    if not changed or changed != set(receipts) or plan["locked_hash_changes"]:
        raise ValueError("UNAPPROVED_OR_LOCKED_CHANGE")
    candidate_config = voice_plan.pause_config(config)
    if chapter_title_carrier:
        candidate_config.setdefault("render", {}).setdefault("leadin", {})[
            "chapter_title_carrier"] = True
    candidate_table = {**table, **voice_plan.validate_rules(rules)}
    fresh = chunker.build_manifest(units, candidate_config, pronounce_table=candidate_table)
    generation = generation_identity(candidate_config)
    outputs = []
    copies = []
    for prior, row in zip(old, fresh):
        cid = row["id"]
        if cid in changed:
            receipt = receipts[cid]
            source, seed, duration = _verified_trial(
                receipt, row, candidate_config, candidate_table, generation)
            row.update(status="done", locked=True, seed=seed, seed_override=seed,
                       duration_ms=duration)
            copies.append((source, cid, receipt["wav_sha256"]))
            outputs.append(row)
        else:
            source = live / "chunks" / f"{cid}.wav"
            if source.is_file():
                copies.append((source, cid, file_digest(source)))
            elif prior.get("locked") or prior.get("status") in ("done", "manual"):
                raise ValueError("MISSING_LIVE_WAV")
            outputs.append(prior)
    # Exclusive destination, independent physical copies; never use hard links.
    stage = paths.OUT / "reviewed_stage" / tag / section
    stage.mkdir(parents=True, exist_ok=False, mode=0o700)
    chunks = stage / "chunks"
    chunks.mkdir()
    for src, cid, digest in copies:
        dst = chunks / f"{cid}.wav"
        with src.open("rb") as inp, dst.open("xb") as out:
            shutil.copyfileobj(inp, out)
        if file_digest(dst) != digest:
            raise ValueError("STAGED_WAV_DIGEST_MISMATCH")
    chunker._write_manifest(stage / "manifest.jsonl", outputs)
    # Verify the source manifest did not change during staging (idle renderer).
    if voice_plan.digest(chunker._read_manifest(live / "manifest.jsonl")) != plan[
            "baseline_manifest_sha256"]:
        raise ValueError("LIVE_MANIFEST_CHANGED")
    ready = {
        "section": section,
        "source_manifest_sha256": plan["baseline_manifest_sha256"],
        "candidate_config_sha256": plan["candidate_config_sha256"],
        "candidate_dictionary_sha256": plan["candidate_dictionary_sha256"],
        "stage_manifest_sha256": file_digest(stage / "manifest.jsonl"),
        "adopted_ids": sorted(changed),
        "wav_sha256": {cid: digest for _, cid, digest in copies},
    }
    with (stage / "READY.json").open("x", encoding="utf-8") as stream:
        json.dump(ready, stream, indent=2, sort_keys=True)
    return stage
