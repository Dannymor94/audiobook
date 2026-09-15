from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
BIN = ROOT / "bin"
REF = ROOT / "ref"
TEXT = ROOT / "text"
CACHE = ROOT / "cache"
OUT = ROOT / "out"


def ffmpeg() -> Path | None:
    """Сначала ./bin, потом PATH. Так переносится вместе с папкой."""
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    local = BIN / exe
    if local.exists():
        return local
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def apply_env_defaults() -> None:
    """Кэши моделей — внутри проекта, не в домашнем кэше. Вызывать до импорта torch/TTS."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("TTS_HOME", str(MODELS / "tts"))
    os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
