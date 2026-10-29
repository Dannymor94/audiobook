from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from . import paths, voicecfg

# ELF magic bytes for Linux/Windows x86-64; Mach-O magic for macOS arm64/x86-64
_MAGIC: dict[bytes, str] = {
    b"\x7fELF": "ELF (Linux/Windows)",
    b"\xfe\xed\xfa\xce": "Mach-O 32-bit",
    b"\xfe\xed\xfa\xcf": "Mach-O 64-bit",
    b"\xce\xfa\xed\xfe": "Mach-O 32-bit (reversed)",
    b"\xcf\xfa\xed\xfe": "Mach-O 64-bit (reversed)",
    b"MZ": "PE (Windows)",
}


def _binary_fmt(path: Path) -> str:
    try:
        data = path.read_bytes()[:4]
        for magic, label in _MAGIC.items():
            if data[: len(magic)] == magic:
                return label
        return "unknown"
    except OSError:
        return "unreadable"


def _check_ffmpeg_platform(r: "Report", ff: Path) -> None:
    fmt = _binary_fmt(ff)
    r.info("ffmpeg формат", fmt)
    expected = "ELF" if sys.platform == "linux" else ("Mach-O" if sys.platform == "darwin" else "PE")
    ok = expected in fmt
    r.check("ffmpeg платформа совпадает", ok,
            f"бинарь {fmt!r} не запустится на {sys.platform}; убрать bin/ffmpeg или заменить нативным")


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
        r.info("ffmpeg путь", ff)
        _check_ffmpeg_platform(r, ff)

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

    r.info("quantize", voicecfg.quantize(config or {}))

    if not no_models:
        variant = voicecfg.variant(config or {})
        qwen_dir = voicecfg.hub_dir(variant)
        r.check(f"models/hf (Qwen3-TTS {variant})", any(qwen_dir.rglob("model.safetensors")),
                f"нет {qwen_dir} — скопировать models/ с флешки")
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

        # ref_text for full-clone mode: if config points to one it must exist,
        # else create_voice_clone_prompt(x_vector_only_mode=False) raises
        # ValueError on the render machine. Lives in ref/ (gitignored, flash drive).
        if config and config.get("reference", {}).get("path"):
            lat = voicecfg.latents_path(config)
            r.check(f"латенты под {variant}", lat.exists(),
                    f"нет {lat} — латенты зависят от модели, посчитать один раз (README)")

        rtp = (config or {}).get("reference", {}).get("ref_text_path")
        if rtp:
            rt = paths.ROOT / rtp
            r.check("ref_text (полный клон)", rt.exists(),
                    f"нет {rt} — полный клон упадёт с ValueError; ref/ на флешке")

    print("\n".join(r.lines))
    print("\nDOCTOR:", "GREEN" if r.ok else "RED")
    return r.ok
