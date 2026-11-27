"""Public-only provisioner for ALG-04B Silero + OpenVoice converter.

Silero's official URL is mutable: recorded SHA is a local pin, not a publisher
digest. No model deserialization or private data in this program.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import urllib.request

from audiobook.pocket_preflight import sha
from audiobook.pocket_provision import verify_download

SILERO_URL = "https://models.silero.ai/models/tts/ru/v5_cis_base.pt"
OV_REPO = "myshell-ai/OpenVoiceV2"
OV_REV = "fd981100305a0e4291f93a9ad169c6d9f7bed54a"
OV_SHA = "9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e"
OV_SOURCE = "74a1d147b17a8c3092dd5430504bd83ef6c7eb23"
SILERO_SOURCE = "e382298387332f2bf461fe6eadfde99104611b0c"
NAMES = ("silero.pt", "config.json", "checkpoint.pth")


def verify_inventory(root: Path, inv: dict) -> dict:
    if (inv.get("silero_url") != SILERO_URL or inv.get("openvoice_revision") != OV_REV
            or inv.get("openvoice_source") != OV_SOURCE
            or inv.get("silero_source") != SILERO_SOURCE):
        raise ValueError("WRONG_MODEL_PROVENANCE")
    files = inv["files"]
    if set(files) != set(NAMES) or files["checkpoint.pth"] != OV_SHA:
        raise ValueError("WRONG_ASSET_INVENTORY")
    for name in NAMES:
        p = root/name
        if p.is_symlink() or not p.is_file() or sha(p) != files[name]:
            raise ValueError("ASSET_DIGEST_MISMATCH:" + name)
    cfg = json.loads((root/"config.json").read_bytes())
    if (cfg.get("_version_") != "v2" or cfg["data"]["sampling_rate"] != 22050
            or cfg["data"]["n_speakers"] != 0 or cfg["model"]["zero_g"] is not True):
        raise ValueError("WRONG_CONVERTER_CONFIG")
    return inv


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    from huggingface_hub import HfApi, hf_hub_download

    if a.out.exists() or not a.out.parent.is_dir():
        raise ValueError("NEW_OUTPUT_REQUIRED")
    if shutil.disk_usage(a.out.parent).free < 3*1024**3:
        raise ValueError("INSUFFICIENT_DISK")
    info = HfApi(endpoint="https://huggingface.co", token=False).model_info(
        OV_REPO, revision=OV_REV, files_metadata=True, token=False)
    if info.sha != OV_REV or info.card_data is None or info.card_data.get("license") != "mit":
        raise ValueError("CONVERTER_REVISION_OR_LICENSE_MISMATCH")
    siblings = {s.rfilename: s for s in info.siblings or []}
    a.out.mkdir(mode=0o700)
    publisher = {}
    for name in ("config.json", "checkpoint.pth"):
        remote = f"converter/{name}"
        s = siblings[remote]
        if name == "checkpoint.pth":
            if getattr(s.lfs, "sha256", None) != OV_SHA:
                raise ValueError("PUBLISHER_WEIGHT_DIGEST_MISMATCH")
            expected = dict(size=s.size, algorithm="sha256", digest=OV_SHA)
        else:
            expected = dict(size=s.size, algorithm="git-sha1", digest=s.blob_id)
        cached = hf_hub_download(OV_REPO, remote, revision=OV_REV, token=False,
                                 endpoint="https://huggingface.co")
        shutil.copyfile(cached, a.out/name)
        verify_download(a.out/name, expected)
        publisher[name] = expected
    # Do not silently substitute another model or noncommercial variant.
    with urllib.request.urlopen(SILERO_URL, timeout=60) as response:
        if response.geturl() != SILERO_URL:
            raise ValueError("UNEXPECTED_SILERO_REDIRECT")
        length = int(response.headers.get("Content-Length", "0"))
        if not 0 < length < 1024**3:
            raise ValueError("UNEXPECTED_SILERO_SIZE")
        target = a.out / "silero.pt"
        target.touch(exist_ok=False)
        with target.open("wb") as f:
            remaining = length
            while remaining:
                block = response.read(min(1024*1024, remaining))
                if not block:
                    raise ValueError("TRUNCATED_SILERO_DOWNLOAD")
                f.write(block)
                remaining -= len(block)
            if response.read(1):
                raise ValueError("SILERO_LENGTH_MISMATCH")
    inv = dict(silero_url=SILERO_URL, openvoice_revision=OV_REV,
               openvoice_source=OV_SOURCE, silero_source=SILERO_SOURCE,
               files={name: sha(a.out/name) for name in NAMES})
    verify_inventory(a.out, inv)
    (a.out/"publisher.json").write_text(json.dumps(publisher, indent=2), encoding="utf-8")
    path = a.out/"inventory.json"
    path.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    print("INVENTORY_SHA256=" + sha(path))
    print("Silero SHA256 locally frozen; no publisher SHA available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
