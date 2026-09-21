from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from . import paths


class Report:
    def __init__(self) -> None:
        self.ok = True
        self.lines: list[str] = []

    def check(self, name: str, cond: bool, hint: str = "") -> None:
        mark = "OK " if cond else "FAIL"
        self.lines.append(f"[{mark}] {name}" + ("" if cond else f"  -> {hint}"))
        self.ok &= cond

    def info(self, name: str, value: object) -> None:
        self.lines.append(f"[ .. ] {name}: {value}")


def run(no_models: bool = False, config: dict | None = None) -> bool:
    r = Report()
    r.info("platform", f"{platform.system()} {platform.machine()} py{sys.version_info.major}.{sys.version_info.minor}")
    r.check("python 3.11", sys.version_info[:2] == (3, 11), "qwen-tts пинит окружение под 3.11")
    r.check("PYTHONUTF8=1", os.environ.get("PYTHONUTF8") == "1", "выставить в .env / run.bat")
    r.check("TTS_HOME внутри проекта",
            Path(os.environ.get("TTS_HOME", "")).resolve() == (paths.MODELS / "tts").resolve(),
            "иначе веса уйдут в домашний кэш и не переедут")
    r.check("HF_HOME внутри проекта",
            Path(os.environ.get("HF_HOME", "")).resolve() == (paths.MODELS / "hf").resolve(), "см. .env")

    ff = paths.ffmpeg()
    r.check("ffmpeg", ff is not None, "положить в bin/ или поставить в PATH")
    if ff:
        r.info("ffmpeg", ff)

    try:
        import torch
        from .device import pick_device
        r.info("torch", torch.__version__)
        r.info("device", pick_device())
    except Exception as e:  # noqa: BLE001
        r.check("torch импортируется", False, str(e))

    try:
        import qwen_tts  # noqa: F401
        r.info("qwen-tts", "импортируется")
    except Exception as e:  # noqa: BLE001
        r.check("qwen-tts импортируется", False, str(e))

    if not no_models:
        qwen_dir = paths.MODELS / "hf" / "hub" / "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base"
        r.check("models/hf (Qwen3-TTS)", any(qwen_dir.rglob("model.safetensors")), "скопировать models/ с флешки")
        r.check(f"models/nn  ({paths.MODELS / 'nn'})", (paths.MODELS / "nn").exists(), "скопировать models/nn с флешки (451 MB)")
        r.check(f"models/dictionary  ({paths.MODELS / 'dictionary'})", (paths.MODELS / "dictionary").exists(), "скопировать models/dictionary с флешки (22 MB)")
        r.check("models/whisper", (paths.MODELS / "whisper").exists(), "скопировать models/")
        ref = paths.ROOT / (config or {}).get("reference", {}).get("path", "ref/isaev_ref.wav")
        r.check("референс голоса", ref.exists(), f"нет {ref}")
        if ref.exists():
            try:
                import soundfile as sf
                info = sf.info(str(ref))
                r.info("референс", f"{info.samplerate} Hz, {info.channels} ch, {info.duration:.1f} s")
                r.check("референс mono", info.channels == 1, "ffmpeg -ac 1")
                r.check("референс 6-30 с", 6 <= info.duration <= 30, "обрезать")
            except Exception as e:  # noqa: BLE001
                r.check("референс читается", False, str(e))

    print("\n".join(r.lines))
    print("\nDOCTOR:", "GREEN" if r.ok else "RED")
    return r.ok
