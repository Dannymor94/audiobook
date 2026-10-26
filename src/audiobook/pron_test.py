"""pron-test: synthesise multiple text variants of a phrase, each with N dubs,
then concatenate into a single all.mp3 for A/B listening.

Output layout:
    out/pron_test/<section>_<YYYYMMDD>_<word>/
        v01/dub_01.wav  dub_02.wav  ...
        v02/...
        all.mp3
"""
from __future__ import annotations

import datetime
import hashlib
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from audiobook import paths
from audiobook.synth import _SAMPLE_RATE, cap_params
from audiobook.worker import TimeoutSynth

_SR = _SAMPLE_RATE


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(_SR * seconds), dtype=np.float32)


def run_pron_test(
    config: dict,
    section: str,
    word: str,
    tries: list[str],
    dubs: int = 3,
) -> int:
    variants = [word if t == "-" else t for t in tries]

    date = datetime.date.today().strftime("%Y%m%d")
    test_dir = paths.OUT / "pron_test" / f"{section}_{date}_{word}"
    test_dir.mkdir(parents=True, exist_ok=True)

    ref = paths.ROOT / config["reference"]["path"]
    rcfg = config.get("render", {})
    wcfg = {
        "device": "cpu",
        "latents_path": str(ref.with_suffix(".latents.pt")),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
    }

    base_seed = int(hashlib.sha1(word.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF

    sep_short = test_dir / "_sep_short.wav"
    sep_long = test_dir / "_sep_long.wav"
    sf.write(str(sep_short), _silence(0.3), _SR, subtype="PCM_16", format="WAV")
    sf.write(str(sep_long), _silence(1.0), _SR, subtype="PCM_16", format="WAV")

    wav_files: list[Path] = []
    report: list[str] = []

    with TimeoutSynth(wcfg, rcfg.get("chunk_timeout_s", 600)) as engine:
        for vi, variant in enumerate(variants, 1):
            var_dir = test_dir / f"v{vi:02d}"
            var_dir.mkdir(exist_ok=True)

            dub_info: list[str] = []
            for di in range(1, dubs + 1):
                seed = base_seed + vi * 1000 + di * 100
                out_path = var_dir / f"dub_{di:02d}.wav"

                if di > 1:
                    wav_files.append(sep_short)
                wav_files.append(out_path)

                if out_path.exists():
                    data, sr = sf.read(str(out_path))
                    dur = len(data) / sr
                    dub_info.append(f"дубль {di}: {dur:.2f}с (кеш)")
                    continue

                wav = engine.synth(variant, seed)
                if wav is None:
                    dub_info.append(f"дубль {di}: TIMEOUT/RUNAWAY")
                    sf.write(str(out_path), _silence(0.1), _SR, subtype="PCM_16", format="WAV")
                    continue

                tmp = out_path.parent / (out_path.name + ".part")
                sf.write(str(tmp), wav, _SR, subtype="PCM_16", format="WAV")
                tmp.replace(out_path)
                dur = len(wav) / _SR
                dub_info.append(f"дубль {di}: {dur:.2f}с")

            base_marker = " (base)" if variant == word else ""
            report.append(f"{vi}. {variant!r}{base_marker}  —  {', '.join(dub_info)}")

            if vi < len(variants):
                wav_files.append(sep_long)

    _concat_mp3(test_dir, wav_files)

    print(f"\npron-test: {len(variants)} вариантов × {dubs} дублей")
    for line in report:
        print(line)
    print(f"\nall.mp3: {test_dir / 'all.mp3'}")
    return 0


def _concat_mp3(test_dir: Path, wav_files: list[Path]) -> None:
    ff_path = paths.ffmpeg()
    if ff_path is None:
        print("ffmpeg не найден — all.mp3 не собран")
        return
    concat_list = test_dir / "_concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in wav_files:
            escaped = str(p.resolve()).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    all_mp3 = test_dir / "all.mp3"
    subprocess.run(
        [str(ff_path), "-hide_banner", "-y",
         "-f", "concat", "-safe", "0",
         "-i", str(concat_list),
         "-c:a", "libmp3lame", "-b:a", "128k",
         str(all_mp3)],
        check=True,
    )
