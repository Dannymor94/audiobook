from __future__ import annotations

import time

from . import paths
from .device import configure_cpu_threads, pick_device

SAMPLES = [
    "Ты не поломан. Ты просто давно не слышал себя.",
    "Каждая маска когда-то была защитой. Потом она стала привычкой.",
    "Мы редко замечаем момент, когда устаём быть сильными.",
    "Тело помнит то, что ум предпочёл забыть.",
    "Иногда самое честное, что можно сделать, — остановиться.",
]


def run(config: dict) -> int:
    device = pick_device()
    configure_cpu_threads(workers=1)
    print(f"device={device}")
    from TTS.api import TTS
    t0 = time.perf_counter()
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    print(f"load: {time.perf_counter() - t0:.1f}s")

    ref = str(paths.ROOT / config["reference"]["path"])
    gen_s = audio_s = 0.0
    for text in SAMPLES:
        t = time.perf_counter()
        wav = tts.tts(text=text, speaker_wav=ref, language="ru")
        gen_s += time.perf_counter() - t
        audio_s += len(wav) / 24000
    rtf = gen_s / audio_s
    hours = rtf * 7 * 1.2
    print(f"RTF={rtf:.2f}  ->  7-часовая книга ~{hours:.0f} ч с запасом на переозвучку")
    print("вердикт:", "локально ок" if rtf < 4 else "на грани" if rtf < 8 else "арендовать GPU")
    return 0
