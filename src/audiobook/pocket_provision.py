"""Provision public Pocket assets only, pinning the resolved revision before download."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from audiobook.pocket_preflight import FILES, sha, verify_assets

REPO = "gabrione/pocket-tts-phonemes-multilang"
PUBLIC_FILES = ("README.md", "manifest.json", "model.yaml", "tokenizer.json",
                "model.safetensors")


def expected_files(info) -> dict:
    revision = info.sha
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("FULL_MODEL_REVISION_REQUIRED")
    card = info.card_data
    if card is None or card.get("license") != "cc-by-4.0":
        raise ValueError("EXPECTED_WEIGHT_LICENSE_NOT_DECLARED")
    by_name = {s.rfilename: s for s in info.siblings or []}
    result = {}
    for name in PUBLIC_FILES:
        s = by_name.get(name)
        if s is None or type(s.size) is not int or s.size <= 0:
            raise ValueError("MISSING_FILE_METADATA:" + name)
        lfs = s.lfs
        lfs_hash = getattr(lfs, "sha256", None) if lfs is not None else None
        if lfs_hash:
            if not re.fullmatch(r"[a-f0-9]{64}", lfs_hash):
                raise ValueError("INVALID_LFS_DIGEST:" + name)
            algorithm, digest = "sha256", lfs_hash
        else:
            if name == "model.safetensors":
                raise ValueError("WEIGHT_LFS_SHA256_REQUIRED")
            if not isinstance(s.blob_id, str) or not re.fullmatch(r"[a-f0-9]{40}", s.blob_id):
                raise ValueError("GIT_BLOB_DIGEST_REQUIRED:" + name)
            algorithm, digest = "git-sha1", s.blob_id
        result[name] = dict(size=s.size, algorithm=algorithm, digest=digest)
    return result


def verify_download(path: Path, expected: dict) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected["size"]:
        raise ValueError("FILE_SIZE_OR_TYPE_MISMATCH:" + path.name)
    digest = sha(path)
    if expected["algorithm"] == "sha256":
        actual = digest
    elif expected["algorithm"] == "git-sha1":
        h = hashlib.sha1(f"blob {expected['size']}\0".encode("ascii"),
                         usedforsecurity=False)
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        actual = h.hexdigest()
    else:
        raise ValueError("UNSUPPORTED_METADATA_DIGEST")
    if actual != expected["digest"]:
        raise ValueError("PUBLISHER_DIGEST_MISMATCH:" + path.name)
    return digest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--revision", help="Previously recorded full commit; omit only on first resolution")
    a = p.parse_args()
    if a.revision and not re.fullmatch(r"[a-f0-9]{40}", a.revision):
        raise ValueError("FULL_MODEL_REVISION_REQUIRED")
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi(endpoint="https://huggingface.co", token=False)
    info = api.model_info(REPO, revision=a.revision, files_metadata=True, token=False)
    expected = expected_files(info)
    revision = info.sha
    if a.revision and revision != a.revision:
        raise ValueError("REVISION_MISMATCH")
    pinned = api.model_info(REPO, revision=revision, files_metadata=True, token=False)
    if pinned.sha != revision or expected_files(pinned) != expected:
        raise ValueError("PINNED_METADATA_MISMATCH")
    if a.out.exists() or not a.out.parent.is_dir():
        raise ValueError("NEW_OUTPUT_REQUIRED")
    if shutil.disk_usage(a.out.parent).free < 2*sum(x["size"] for x in expected.values()) + 1024**3:
        raise ValueError("INSUFFICIENT_DISK")
    a.out.mkdir(mode=0o700)
    (a.out / "publisher.json").write_text(json.dumps({
        "repo_id": REPO, "revision": revision, "license": "cc-by-4.0",
        "files": expected}, indent=2), encoding="utf-8")
    print("PINNED_REVISION=" + revision, flush=True)
    model = a.out / "model"
    model.mkdir(mode=0o700)
    actual = {}
    for name in PUBLIC_FILES:
        cached = hf_hub_download(REPO, name, revision=revision, token=False,
                                 endpoint="https://huggingface.co")
        dest = model / name
        shutil.copyfile(cached, dest)
        actual[name] = verify_download(dest, expected[name])
        if name == "manifest.json":
            m = json.loads(dest.read_bytes())
            if "ru" not in m.get("languages", []) or m.get("keep_stress") is not True:
                raise ValueError("RUSSIAN_STRESS_TRAINING_NOT_DECLARED")
        if name == "tokenizer.json":
            from tokenizers import Tokenizer
            from audiobook.pocket_preflight import verify_token_channel
            verify_token_channel(Tokenizer.from_file(str(dest)))
    inventory = dict(repo_id=REPO, revision=revision, files={n: actual[n] for n in FILES})
    verify_assets(model, inventory)
    path = a.out / "inventory.json"
    path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print("INVENTORY_SHA256=" + sha(path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
