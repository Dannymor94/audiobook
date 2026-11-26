"""ALG-04 bounded, synthetic IPA stress responsiveness trial, never production audio.

No manuscript input. The deliberately contrastive stress arms are diagnostic,
not normative Russian pronunciations. Acoustic execution requires explicit GO.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from audiobook.pocket_preflight import sha, verify_assets, verify_token_channel
from audiobook.rhythm_pilot import preflight

UPSTREAM = "a696db20e2877a080df503d9bad11f315a3429ff"
POLICY = "pocket-ipa-control-v1"
# Identical segmental strings with contrastive primary-stress marks. Vowel
# reduction is intentionally not varied: this isolates marker responsiveness.
CASES = (
    ("01", "development", "ˈmama", "maˈma"),
    ("02", "development", "ˈzamak", "zaˈmak"),
    ("03", "heldout", "ˈmuka", "muˈka"),
    ("04", "heldout", "ˈatlas", "atˈlas"),
)
SEED = 42
CPU_THREADS = 8
SETTINGS = dict(temp=0.3, cfg=2.0, eos_threshold=-1.0, eos_countdown=1,
                n_steps=1, max_frames=125, voice_sec=5.0, emit_frames=2,
                fade_in_ms=0.0)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_plan(tokenizer, identity: dict, reference_sha: str,
              upstream_sha: str, versions: dict) -> dict:
    tokens = verify_token_channel(tokenizer, [(a, b) for _, _, a, b in CASES])
    trials = []
    for (cid, split, a, b), t in zip(CASES, tokens):
        trials.append({"chunk_id": cid, "chunk_hash": digest((a+"\0"+b).encode()),
                       "split": split, "status": "planned", "seed": SEED,
                       "carrier": None, "baseline": a, "candidate": b,
                       "baseline_sha256": digest(a.encode()),
                       "candidate_sha256": digest(b.encode()),
                       "baseline_tokens": t["a_ids"], "candidate_tokens": t["b_ids"],
                       "target": {"split": split, "kind": "marker_responsiveness"}})
    return dict(policy=POLICY, identity=identity, reference_sha256=reference_sha,
                upstream=UPSTREAM, sampler_sha256=upstream_sha, versions=versions,
                settings=SETTINGS, cpu_threads=CPU_THREADS, trials=trials)


def collect_audio(engine, ipa, voice, seed, expected_ids, timeout=180):
    import numpy as np

    if engine.tokens(ipa).tolist() != expected_ids:
        raise ValueError("ACTUAL_CONDITIONER_TOKEN_MISMATCH")
    chunks, end = [], None
    clock = perf_counter()
    for event, row, value in engine.stream([(ipa, voice)], seed=seed,
                                            stop=lambda _: perf_counter()-clock > timeout):
        if row != 0 or end is not None:
            raise ValueError("UNEXPECTED_STREAM_EVENT")
        if event == "audio":
            if value.ndim != 1 or not len(value) or not np.isfinite(value).all():
                raise ValueError("INVALID_AUDIO_FRAME")
            chunks.append(value)
        elif event == "end":
            end = value
        else:
            raise ValueError("UNEXPECTED_STREAM_EVENT")
    if (not chunks or end is None or end.get("stopped") is not False
            or end.get("max_frames") or type(end.get("frames")) is not int
            or not 0 < end["frames"] < engine.max_frames
            or perf_counter()-clock > timeout):
        raise ValueError("INCOMPLETE_OR_CAPPED_AUDIO")
    wav = np.concatenate(chunks)
    if len(wav) != end["frames"] * engine.samples_per_frame:
        raise ValueError("FRAME_LENGTH_MISMATCH")
    if not np.any(wav):
        raise ValueError("SILENT_AUDIO")
    return wav


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--inventory-sha256", required=True)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--reference-sha256", required=True)
    p.add_argument("--upstream", type=Path, required=True)
    p.add_argument("--sampler-sha256", required=True)
    p.add_argument("--canonical-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--plan-sha256")
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    from audiobook.gamebox import require_gamebox
    require_gamebox()
    if a.execute and not a.plan_sha256:
        raise ValueError("FROZEN_PLAN_REQUIRED")
    # HF offline flags are not a network sandbox. Operator must enforce
    # network isolation for execution independently.
    if any(os.environ.get(k) != "1" for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise ValueError("OFFLINE_FLAGS_REQUIRED")
    from audiobook import jobqueue, paths
    from unittest.mock import patch
    canonical = a.canonical_out.resolve(strict=True)
    out = a.out.resolve()
    if (out.exists() or out.is_relative_to(canonical)
            or out.is_relative_to(paths.ROOT.resolve())
            or out.is_relative_to(a.model_dir.resolve())
            or out.is_relative_to(a.upstream.resolve())
            or not (canonical/"queue").is_dir() or os.environ.get(jobqueue.LOCK_HELD_ENV)):
        raise ValueError("PRIVATE_OUTPUT_AND_CANONICAL_LOCK_REQUIRED")
    preflight(out.parent.resolve(strict=True))
    upstream = a.upstream.resolve(strict=True)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(upstream), *args], text=True).strip()
    if git("rev-parse", "HEAD") != UPSTREAM or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("UPSTREAM_CHECKOUT_NOT_PINNED_CLEAN")
    sampler = upstream/"hybrid/tts/phonemes/batch.py"
    if sha(sampler) != a.sampler_sha256 or sha(a.reference) != a.reference_sha256:
        raise ValueError("SAMPLER_OR_REFERENCE_DIGEST_MISMATCH")
    if sha(a.inventory) != a.inventory_sha256:
        raise ValueError("INVENTORY_DIGEST_MISMATCH")
    inventory = json.loads(a.inventory.read_bytes())
    identity = verify_assets(a.model_dir, inventory)
    if sys.version_info[:2] != (3, 12):
        raise ValueError("PYTHON_312_REQUIRED")
    versions = {n: importlib.metadata.version(n) for n in
                ("pocket-tts", "torch", "tokenizers", "numpy", "soundfile", "pyyaml")}
    if (versions["pocket-tts"] != "4.0.1" or versions["torch"].split("+")[0] != "2.13.0"
            or versions["tokenizers"] != "0.22.2"):
        raise ValueError("PINNED_RUNTIME_REQUIRED")
    from tokenizers import Tokenizer
    plan = make_plan(Tokenizer.from_file(str(a.model_dir/"tokenizer.json")),
                     identity, a.reference_sha256, a.sampler_sha256, versions)
    data = json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()
    if a.execute and digest(data) != a.plan_sha256:
        raise ValueError("FROZEN_PLAN_MISMATCH")
    with patch.object(jobqueue, "queue_root", return_value=canonical/"queue"), jobqueue.heavy_command_lock("pocket-pilot"):
        if any(j.get("status") in ("pending", "running", "unreadable") for j in jobqueue.list_jobs()):
            raise ValueError("CANONICAL_QUEUE_NOT_IDLE")
        out.mkdir(mode=0o700, exist_ok=False)
        (out/"plan_PRIVATE.json").write_bytes(data)
        if not a.execute:
            print("PLANNED_ONLY: " + digest(data))
            return 0
        import torch
        import soundfile as sf
        torch.set_num_threads(CPU_THREADS)
        torch.manual_seed(SEED)
        sys.path.insert(0, str(upstream))
        from hybrid.tts.phonemes.batch import PhonemeBatchTTS
        started = datetime.now(timezone.utc).isoformat()
        clock = perf_counter()
        engine = PhonemeBatchTTS.load(a.model_dir, device="cpu",
                                      tokenizer=str(a.model_dir/"tokenizer.json"),
                                      n_bins=4000, **SETTINGS)
        if engine.device.type != "cpu" or engine.sr != 24000 or "ru" not in engine.info["languages"]:
            raise ValueError("MODEL_RUNTIME_IDENTITY_MISMATCH")
        if Path(sys.modules["hybrid.tts.phonemes.batch"].__file__).resolve() != sampler.resolve():
            raise ValueError("UNEXPECTED_SAMPLER_MODULE")
        voice = engine.voice_latents(str(a.reference))
        with (out/"receipts_PRIVATE.jsonl").open("x", encoding="utf-8") as log:
            for t in plan["trials"]:
                for arm in ("baseline", "candidate"):
                    t0 = perf_counter()
                    wav = collect_audio(engine, t[arm], voice, t["seed"], t[arm+"_tokens"])
                    path = out/f"{t['chunk_id']}_{arm}.wav"
                    sf.write(str(path), wav, 24000, subtype="FLOAT")
                    receipt = dict(chunk_id=t["chunk_id"], arm=arm, status="generated",
                                   plan_sha256=digest(data), seed=t["seed"], carrier=None,
                                   input_sha256=t[arm+"_sha256"], generation={k: plan[k] for k in ("identity", "reference_sha256", "upstream",
                                                                  "sampler_sha256", "versions", "settings", "cpu_threads")},
                                   wav=path.name, wav_sha256=sha(path), samples=len(wav),
                                   elapsed_s=perf_counter()-t0)
                    log.write(json.dumps(receipt)+"\n")
                    log.flush()
                    os.fsync(log.fileno())
        if (verify_assets(a.model_dir, inventory) != identity
                or sha(a.inventory) != a.inventory_sha256
                or sha(a.reference) != a.reference_sha256 or sha(sampler) != a.sampler_sha256
                or git("rev-parse", "HEAD") != UPSTREAM
                or git("status", "--porcelain", "--untracked-files=all")):
            raise ValueError("INPUT_IDENTITY_CHANGED")
        (out/"READY_PRIVATE.json").write_text(json.dumps({
            "plan_sha256": digest(data), "pairs": 4,
            "receipts_sha256": sha(out/"receipts_PRIVATE.jsonl"),
            "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": perf_counter()-clock}), encoding="utf-8")
    print("READY: 4 synthetic pairs; no production writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
