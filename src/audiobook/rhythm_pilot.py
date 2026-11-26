"""Bounded ALG-03 actuator feasibility pilot; never writes production audio."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from time import perf_counter

from audiobook.rhythm_actuator import POLICY, plan

CH1 = "08_glava_1_zver_vnutri_nas_instinkty_eto_ne"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_trials(rows: list[dict], gold: dict, targets: list[dict],
                 config: dict, table: dict) -> list[dict]:
    by_id = {r["id"]: r for r in rows}
    annotations = {r["id"]: r for r in gold["rows"]}
    if len(by_id) != len(rows) or len(annotations) != len(gold["rows"]):
        raise ValueError("DUPLICATE_INVENTORY")
    if len(targets) != 4 or len({t["chunk_id"] for t in targets}) != 4:
        raise ValueError("EXACTLY_FOUR_DISTINCT_PAIRS_REQUIRED")
    trials = []
    for target in targets:
        cid = target["chunk_id"]
        if not isinstance(cid, str) or len(cid) != 4 or not cid.isascii() or not cid.isdigit():
            raise ValueError("INVALID_CHUNK_ID")
        if cid not in by_id or cid not in annotations:
            raise ValueError("UNKNOWN_TARGET")
        annotation = annotations[cid]
        if annotation.get("independently_reviewed") is not True:
            raise ValueError("INDEPENDENT_BOUNDARY_REVIEW_REQUIRED")
        r = plan(by_id[cid], annotation, target["offset"], config, table)
        if r["status"] != "planned":
            raise ValueError("UNUSABLE_TARGET:" + r["status"])
        trials.append(dict(r, target=target))
    if Counter(r["split"] for r in trials) != {"development": 2, "heldout": 2}:
        raise ValueError("TWO_DEV_TWO_HELDOUT_REQUIRED")
    return trials


def preflight(parent: Path) -> None:
    from audiobook.gamebox import require_gamebox

    require_gamebox()
    fields = Path("/proc/meminfo").read_text(encoding="ascii").splitlines()
    available = [int(l.split()[1]) for l in fields if l.startswith("MemAvailable:")]
    if len(available) != 1 or available[0] < 15*1024*1024:
        raise ValueError("INSUFFICIENT_AVAILABLE_RAM")
    fs = subprocess.check_output(["stat", "-f", "-c", "%T", str(parent)],
                                 text=True).strip()
    if fs not in {"ext2/ext3", "xfs", "btrfs", "zfs", "f2fs"}:
        raise ValueError("PERSISTENT_LOCAL_FILESYSTEM_REQUIRED")
    if shutil.disk_usage(parent).free < 2*1024**3:
        raise ValueError("INSUFFICIENT_DISK")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gold", type=Path, required=True)
    p.add_argument("--gold-sha256", required=True)
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument("--targets-sha256", required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--canonical-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--plan-sha256", help="Required for execution: digest of prior dry-run plan")
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    if a.execute:
        if not a.plan_sha256:
            raise ValueError("FROZEN_PLAN_DIGEST_REQUIRED")
        from audiobook.gamebox import require_gamebox
        require_gamebox()

    from audiobook import chunker, jobqueue, paths, synth
    from audiobook.__main__ import load_config
    from audiobook.pronounce import load_table
    from audiobook.reviewed_stage import file_digest, generation_identity
    from unittest.mock import patch

    paths.apply_env_defaults()
    canonical = a.canonical_out.resolve(strict=True)
    isolated = paths.OUT.resolve(strict=True)
    out = a.out.resolve()
    if (canonical == isolated or not (canonical / "queue").is_dir()
            or out.exists() or out.is_relative_to(canonical)
            or out.is_relative_to(isolated) or out.is_relative_to(paths.ROOT.resolve())
            or os.environ.get("AUDIOBOOK_CONFIG") or os.environ.get(jobqueue.LOCK_HELD_ENV)):
        raise ValueError("ISOLATED_WORKSPACE_NEW_PRIVATE_OUT_AND_CANONICAL_LOCK_REQUIRED")
    manifest = isolated / "sections" / CH1 / "manifest.jsonl"
    canonical_manifest = canonical / "sections" / CH1 / "manifest.jsonl"
    gold_bytes, target_bytes = a.gold.read_bytes(), a.targets.read_bytes()
    if digest(gold_bytes) != a.gold_sha256 or digest(target_bytes) != a.targets_sha256:
        raise ValueError("FROZEN_ANNOTATIONS_MISMATCH")
    gold, targets = json.loads(gold_bytes), json.loads(target_bytes)
    if gold["manifest_sha256"] != a.manifest_sha256:
        raise ValueError("GOLD_MANIFEST_MISMATCH")
    with patch.object(jobqueue, "queue_root", return_value=canonical / "queue"), jobqueue.heavy_command_lock("rhythm-actuator"):
        if any(j.get("status") in ("pending", "running", "unreadable") for j in jobqueue.list_jobs()):
            raise ValueError("CANONICAL_QUEUE_NOT_IDLE")
        data = manifest.read_bytes()
        if digest(data) != a.manifest_sha256 or canonical_manifest.read_bytes() != data:
            raise ValueError("MANIFEST_IDENTITY_MISMATCH")
        rows = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
        if len(rows) != 238:
            raise ValueError("CH1_INVENTORY_MISMATCH")
        config = chunker.section_config(load_config(), CH1)
        synth.ensure_manifest_current(config, CH1)
        trials = build_trials(rows, gold, targets, config, load_table())
        if a.execute:
            preflight(out.parent.resolve(strict=True))
        generation = generation_identity(config)
        wcfg = synth.worker_config(config, 1)
        wcfg["device"] = "cpu"
        payload = dict(policy=POLICY, manifest_sha256=a.manifest_sha256,
                       gold_sha256=a.gold_sha256, targets_sha256=a.targets_sha256,
                       generation=generation, trials=trials)
        plan_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if a.execute and digest(plan_bytes) != a.plan_sha256:
            raise ValueError("FROZEN_PLAN_MISMATCH")
        out.mkdir(mode=0o700, exist_ok=False)
        (out / "plan_PRIVATE.json").write_bytes(plan_bytes)
        if not a.execute:
            print("PLANNED_ONLY: 4 pairs; no TTS; plan_sha256=" + digest(plan_bytes))
            return 0

        import numpy as np
        import soundfile as sf
        from audiobook.worker import TimeoutSynth

        started = datetime.now(timezone.utc).isoformat()
        clock = perf_counter()
        timeout = config.get("render", {}).get("chunk_timeout_s", 600)
        with (out / "receipts_PRIVATE.jsonl").open("x", encoding="utf-8") as log:
            with TimeoutSynth(wcfg, timeout) as engine:
                for r in trials:
                    for arm in ("baseline", "candidate"):
                        t0 = perf_counter()
                        wav = engine.synth(r[arm], r["seed"], leadin=r["carrier"])
                        receipt = dict(chunk_id=r["chunk_id"], arm=arm, seed=r["seed"],
                                       carrier=r["carrier"], generation=generation,
                                       input_sha256=r[arm+"_sha256"],
                                       plan_sha256=digest(plan_bytes),
                                       elapsed_s=perf_counter()-t0, status="failed")
                        if wav is not None and wav.ndim == 1 and len(wav) and np.isfinite(wav).all():
                            path = out / f"{r['chunk_id']}_{arm}.wav"
                            sf.write(str(path), wav, 24000, subtype="FLOAT")
                            receipt.update(status="generated", wav=path.name,
                                           wav_sha256=file_digest(path), samples=len(wav))
                        log.write(json.dumps(receipt, ensure_ascii=False)+"\n")
                        log.flush()
                        os.fsync(log.fileno())
                        if receipt["status"] != "generated":
                            raise RuntimeError("PILOT_ARM_FAILED_NO_RETRY")
        if (manifest.read_bytes() != data or canonical_manifest.read_bytes() != data
                or generation_identity(config) != generation
                or a.gold.read_bytes() != gold_bytes or a.targets.read_bytes() != target_bytes):
            raise ValueError("PILOT_IDENTITY_CHANGED")
        (out / "READY_PRIVATE.json").write_text(json.dumps({
            "plan_sha256": digest(plan_bytes), "pairs": 4,
            "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": perf_counter()-clock,
            "receipts_sha256": file_digest(out / "receipts_PRIVATE.jsonl")}),
            encoding="utf-8")
        print("READY: 4 pairs / 8 WAV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
