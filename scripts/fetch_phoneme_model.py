"""One-off, explicit download of the phoneme recognizer used by
`./run.sh phoneme-check` (facebook/wav2vec2-xlsr-53-espeak-cv-ft, Apache-2.0,
~1.3 GB) into models/hf/hub — inside the project, so it travels with the folder.

The pipeline runtime stays offline (HF_HUB_OFFLINE=1); this script lifts that
for itself only. Run from the project root:

    uv run python scripts/fetch_phoneme_model.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["HF_HUB_OFFLINE"] = "0"          # this process only
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["HF_HOME"] = str(ROOT / "models" / "hf")

from huggingface_hub import snapshot_download  # noqa: E402  (after env)

from audiobook.phoneme_check import HUB_DIR, MODEL_ID  # noqa: E402

if __name__ == "__main__":
    path = snapshot_download(
        MODEL_ID,
        cache_dir=str(HUB_DIR.parent),
        allow_patterns=["*.json", "*.txt", "*.bin", "*.safetensors"],
    )
    print(f"OK: {path}")
