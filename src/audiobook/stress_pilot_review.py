"""Build a local blind ALG-02 review from verified pilot receipts. No TTS."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
from pathlib import Path

from audiobook import review


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(source: Path, out: Path, key_path: Path, expected_pairs: int = 8,
          *, policy: str = "uppercase-occurrence-pilot-v1") -> Path:
    """A new private folder, exact source inventory, separate private blind key."""
    source = source.resolve(strict=True)
    out = out.resolve()
    key_path = key_path.resolve()
    if (out.exists() or key_path.exists() or out.is_relative_to(source)
            or key_path.is_relative_to(out) or key_path.is_relative_to(source)):
        raise ValueError("NEW_REVIEW_AND_SEPARATE_KEY_REQUIRED")
    plan_bytes = (source / "plan_PRIVATE.json").read_bytes()
    plan = json.loads(plan_bytes)
    if policy not in {"uppercase-occurrence-pilot-v1", "single-stream-comma-semicolon-v1", "pocket-ipa-control-v1", "silero-openvoice-control-v1"} or plan.get("policy") != policy:
        raise ValueError("WRONG_PILOT")
    rhythm = policy == "single-stream-comma-semicolon-v1"
    pocket = policy == "pocket-ipa-control-v1"
    transfer = policy == "silero-openvoice-control-v1"
    if rhythm or pocket or transfer:
        ready = json.loads((source / "READY_PRIVATE.json").read_bytes())
        if (expected_pairs != 4 or ready["pairs"] != 4
                or ready["plan_sha256"] != sha(plan_bytes)
                or ready["receipts_sha256"] != sha((source / "receipts_PRIVATE.jsonl").read_bytes())):
            raise ValueError("RHYTHM_READY_MISMATCH")
    prefix = "ALG04B" if transfer else ("ALG04" if pocket else ("ALG03" if rhythm else "ALG02"))
    trials = [r for r in plan["trials"] if r["status"] == "planned"]
    ids = [r["chunk_id"] for r in trials]
    if len(ids) != expected_pairs or len(set(ids)) != len(ids):
        raise ValueError("WRONG_PAIR_INVENTORY")
    records = [json.loads(line) for line in
               (source / "receipts_PRIVATE.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    by_key = {(r["chunk_id"], r["arm"]): r for r in records}
    if len(records) != len(by_key) or set(by_key) != {
            (c, a) for c in ids for a in ("baseline", "candidate")}:
        raise ValueError("RECEIPT_INVENTORY_MISMATCH")
    import soundfile as sf

    verified = {}
    for t in trials:
        cid = t["chunk_id"]
        for arm in ("baseline", "candidate"):
            r = by_key[cid, arm]
            name = f"{cid}_{arm}.wav"
            if (not cid.isascii() or not cid.isdigit() or r["status"] != "generated"
                    or r["plan_sha256"] != sha(plan_bytes) or r["wav"] != name
                    or r["input_sha256"] != t[arm + "_sha256"]
                    or r["seed"] != t["seed"] or r["carrier"] != t["carrier"]):
                raise ValueError("RECEIPT_IDENTITY_MISMATCH")
            wav = source / name
            data = wav.read_bytes()
            if wav.is_symlink() or sha(data) != r["wav_sha256"]:
                raise ValueError("WAV_DIGEST_MISMATCH")
            info = sf.info(wav)
            if info.samplerate != 24000 or info.channels != 1 or info.frames <= 0:
                raise ValueError("INVALID_WAV")
            if info.frames != r["samples"]:
                raise ValueError("WAV_LENGTH_MISMATCH")
            verified[cid, arm] = (wav, r)
        if transfer:
            raw = source / f"{cid}_silero_raw.wav"
            if raw.is_symlink() or not raw.is_file() or any(
                    by_key[cid, arm]["source_wav_sha256"] != sha(raw.read_bytes())
                    for arm in ("baseline", "candidate")):
                raise ValueError("TRANSFER_SOURCE_MISMATCH")
        if by_key[cid, "baseline"]["generation"] != by_key[cid, "candidate"]["generation"]:
            raise ValueError("PAIR_GENERATION_MISMATCH")

    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    groups, keys = [], []
    for n, t in enumerate(trials, 1):
        cid = t["chunk_id"]
        arms = ["baseline", "candidate"]
        if secrets.randbelow(2):
            arms.reverse()
        group = []
        for side, arm in zip(("A", "B"), arms):
            wav, r = verified[cid, arm]
            name = f"{prefix}-{n:02d}_{side}.wav"
            dest = out / name
            shutil.copyfile(wav, dest)
            if sha(dest.read_bytes()) != r["wav_sha256"]:
                raise ValueError("COPY_DIGEST_MISMATCH")
            group.append({"file": name, "name": f"Пара {n} · {side}",
                          "meta": {"chunk": cid, "pair": str(n), "side": side,
                                   "hash": t["chunk_hash"], "wav_sha256": r["wav_sha256"]}})
            if transfer:
                group[-1]["meta"].update(control_ratings=True, target_word=t["target"]["word"],
                                         text=t["text"].replace("+", ""))
            keys.append({"file": name, "chunk_id": cid, "arm": arm,
                         "wav_sha256": r["wav_sha256"], "target": t["target"]})
        groups.append(group)
    # Bind browser state to actual shuffled audio identities, not title alone.
    pid = sha(json.dumps(keys, sort_keys=True).encode("utf-8"))[:16]
    key_path.parent.mkdir(parents=True, exist_ok=True)
    with key_path.open("x", encoding="utf-8") as f:
        json.dump({"page_id": pid, "plan_sha256": sha(plan_bytes), "items": keys},
                  f, ensure_ascii=False, indent=2)
    page = out / "review.html"
    title = ("ALG-04 — проверка фонемных ударений" if pocket else
             ("ALG-03 — проверка ритма" if rhythm else "ALG-02 — проверка ударений"))
    if transfer:
        title = "ALG-04B — произношение и голос"
    page.write_text(review.render(title, "golden", groups, pid),
                    encoding="utf-8")
    return page


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--private-key", type=Path, required=True)
    p.add_argument("--expected-pairs", type=int, default=8)
    p.add_argument("--policy", choices=["uppercase-occurrence-pilot-v1",
                   "single-stream-comma-semicolon-v1", "pocket-ipa-control-v1", "silero-openvoice-control-v1"], default="uppercase-occurrence-pilot-v1")
    a = p.parse_args()
    print(build(a.source, a.out, a.private_key, a.expected_pairs, policy=a.policy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
