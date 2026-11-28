"""Explicit, download-only provisioning for QWEN-VOICE-CAST-01."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    from audiobook.gamebox import require_gamebox
    require_gamebox()
    if shutil.disk_usage(args.assets.parent).free < 20 * 1024**3:
        raise RuntimeError("GAMEBOX_REQUIRED: insufficient disk")
    from huggingface_hub import HfApi, snapshot_download
    api = HfApi()
    args.assets.mkdir(mode=0o700, exist_ok=True)
    for kind in ("CustomVoice", "VoiceDesign"):
        repo = "Qwen/Qwen3-TTS-12Hz-1.7B-" + kind
        manifest = args.assets / (kind + ".json")
        if manifest.exists():
            print("REUSE_PIN", manifest, flush=True)
            continue
        info = api.model_info(repo, files_metadata=True)
        if info.card_data.license != "apache-2.0":
            raise RuntimeError("UNEXPECTED_LICENSE")
        # Freeze the revision before downloading. No inference in this stage.
        pin = args.assets / (kind + ".pin.json")
        if pin.exists():
            revision = json.loads(pin.read_text(encoding="utf-8"))["revision"]
        else:
            revision = info.sha
            pin.write_text(json.dumps(dict(repo=repo, revision=revision)), encoding="utf-8")
        dest = args.assets / kind
        snapshot_download(repo, revision=revision, local_dir=dest,
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.tiktoken", "LICENSE", "README.md"],
                          max_workers=2)
        records = []
        for file in sorted(dest.rglob("*")):
            if not file.is_file() or ".cache" in file.parts:
                continue
            h = hashlib.sha256()
            with file.open("rb") as handle:
                for block in iter(lambda: handle.read(1024**2), b""):
                    h.update(block)
            records.append(dict(path=str(file.relative_to(dest)), size=file.stat().st_size,
                                sha256=h.hexdigest()))
        if not any(r["path"].endswith(".safetensors") for r in records):
            raise RuntimeError("SAFETENSORS_REQUIRED")
        data = json.dumps(dict(repo=repo, revision=revision, license="apache-2.0", files=records),
                          sort_keys=True, indent=2).encode()
        manifest.write_bytes(data)
        print("PROVISIONED", kind, revision, hashlib.sha256(data).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
