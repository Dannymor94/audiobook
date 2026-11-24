"""Bounded offline paired U+0301 probe of the EXISTING local Qwen checkpoint.

Public synthetic sentences only; new private directory, no production pipeline
or model provisioning. Never interprets audio generation as stress accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
from pathlib import Path

from audiobook.stress_consensus import VOWELS, WORD

ACUTE = "\u0301"
# Synthetic, not manuscript excerpts. Each case marks exactly one target.
CASES = (
    ("fuel", "Для печи нужно то́пливо."),
    ("hungry", "После прогулки он го́лоден."),
    ("badgers", "В лесу живут барсуки́."),
    ("impudent", "Он заметил наха́ла у двери."),
    ("doing", "Мы де́лаем это вместе."),
    ("castle", "На холме стоял за́мок."),
    ("lock", "На двери висел замо́к."),
    ("milk", "На столе стояло молоко́."),
)


def trial_plan(seed: int) -> list[dict]:
    rows = []
    for i, (case, marked) in enumerate(CASES):
        if marked.count(ACUTE) != 1:
            raise ValueError("INVALID_FIXTURE")
        pos = marked.index(ACUTE)
        if marked[pos - 1].lower() not in VOWELS:
            raise ValueError("INVALID_FIXTURE")
        plain = marked.replace(ACUTE, "")
        target = next(m for m in WORD.finditer(plain) if m.start() <= pos - 1 < m.end())
        for condition, text in (("plain", plain), ("acute", marked)):
            rows.append(dict(case=case, condition=condition, text=text,
                             expected_word=target.group(), expected_index=pos - 1 - target.start(),
                             source_start=target.start(), source_end=target.end(),
                             seed=(seed + i) % (2**32)))
    random.Random(seed).shuffle(rows)
    for i, row in enumerate(rows, 1):
        row["id"] = f"{i:03d}"
    return rows


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def snapshot_hashes(path: Path) -> dict[str, str]:
    if not (path / "config.json").is_file() or not list(path.glob("*.safetensors")):
        raise ValueError("EXPECTED_EXISTING_LOCAL_SAFETENSORS_SNAPSHOT")
    return {p.relative_to(path).as_posix(): sha256(p)
            for p in sorted(path.rglob("*")) if p.is_file()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--ref-wav", type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ref-text-file", type=Path)
    mode.add_argument("--xvector-only", action="store_true")
    p.add_argument("--temperature", type=float, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--threads", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if not math.isfinite(a.temperature) or a.temperature <= 0 or not 0 <= a.seed < 2**32 or a.threads < 1:
        raise ValueError("INVALID_TRIAL_SETTINGS")
    if a.out.exists():
        raise ValueError("OUTPUT_EXISTS")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    snapshot = a.snapshot.resolve(strict=True)
    config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "qwen3_tts":
        raise ValueError("EXPECTED_QWEN3_TTS")
    model_hashes = snapshot_hashes(snapshot)
    ref_digest = sha256(a.ref_wav)
    ref_bytes = a.ref_text_file.read_bytes() if a.ref_text_file else None
    ref_text = ref_bytes.decode("utf-8") if ref_bytes is not None else None
    if ref_text is not None and not ref_text.strip():
        raise ValueError("EMPTY_REFERENCE_TEXT")
    import numpy as np
    import soundfile as sf
    import torch
    from importlib.metadata import version
    from time import monotonic
    from qwen_tts import Qwen3TTSModel

    torch.set_num_threads(a.threads)
    model = Qwen3TTSModel.from_pretrained(str(snapshot), dtype=torch.float32,
                                         local_files_only=True, trust_remote_code=False)
    model.model.to("cpu")
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(a.ref_wav), ref_text=ref_text,
        x_vector_only_mode=a.xvector_only,
    )
    if sha256(a.ref_wav) != ref_digest:
        raise ValueError("REFERENCE_CHANGED")
    plan = trial_plan(a.seed)
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (a.out / "plan_PRIVATE.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    provenance = dict(snapshot_sha256=model_hashes, reference_sha256=ref_digest,
                      reference_text_sha256=hashlib.sha256(ref_bytes).hexdigest() if ref_bytes is not None else None,
                      clone_mode="xvector" if a.xvector_only else "icl",
                      device="cpu", dtype="float32", threads=a.threads,
                      temperature=a.temperature, max_new_tokens=256,
                      torch=str(torch.__version__), qwen_tts=version("qwen-tts"),
                      transformers=version("transformers"),
                      limitation="Isolated direct mark probe; not production preprocessing parity.")
    (a.out / "provenance_PRIVATE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    outcomes = []
    with (a.out / "takes_PRIVATE.jsonl").open("x", encoding="utf-8") as stream:
        for row in plan:
            random.seed(row["seed"])
            np.random.seed(row["seed"])
            torch.manual_seed(row["seed"])
            rec = dict(id=row["id"], status="failed")
            try:
                t0 = monotonic()
                wavs, sr = model.generate_voice_clone(
                    text=row["text"], language="Russian", voice_clone_prompt=prompt,
                    temperature=a.temperature, max_new_tokens=256,
                )
                elapsed = monotonic() - t0
                wav = np.asarray(wavs[0], dtype=np.float32)
                if (type(sr) is not int or sr <= 0 or wav.ndim != 1 or not wav.size
                        or not np.isfinite(wav).all() or wav.size / sr >= 256 / 12 * .95):
                    raise ValueError("INVALID_OR_CAPPED_AUDIO")
                path = a.out / (row["id"] + ".wav")
                sf.write(str(path), wav, sr, subtype="FLOAT")
                rec.update(status="generated", sha256=sha256(path), seconds=wav.size / sr,
                           elapsed_seconds=elapsed, rtf=elapsed / (wav.size / sr))
            except Exception as exc:
                rec["error_type"] = type(exc).__name__
            outcomes.append(rec)
            stream.write(json.dumps(rec) + "\n")
            stream.flush()
    if snapshot_hashes(snapshot) != model_hashes or sha256(a.ref_wav) != ref_digest:
        raise ValueError("MODEL_OR_REFERENCE_CHANGED")
    if a.ref_text_file and a.ref_text_file.read_bytes() != ref_bytes:
        raise ValueError("REFERENCE_TEXT_CHANGED")
    summary = dict(planned=len(plan), generated=sum(r["status"] == "generated" for r in outcomes),
                   failed=sum(r["status"] != "generated" for r in outcomes),
                   stress_rated=0, release_ready=False)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
