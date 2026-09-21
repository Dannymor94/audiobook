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
    from .synth import (compute_latents, load_latents, load_model,
                        save_latents, synthesize)
    device = pick_device()
    configure_cpu_threads(workers=1)
    print(f"device={device}")
    t0 = time.perf_counter()
    model = load_model(device)
    print(f"load: {time.perf_counter() - t0:.1f}s")

    ref = paths.ROOT / config["reference"]["path"]
    lat_path = ref.with_suffix(".latents.pt")
    if lat_path.exists():
        latents = load_latents(lat_path)
    else:
        latents = compute_latents(model, ref)
        save_latents(latents, lat_path)
    seed = config["model"]["seed"]
    temperature = config["model"]["temperature"]
    language = config["model"]["language"]

    gen_s = audio_s = 0.0
    for text in SAMPLES:
        t = time.perf_counter()
        wav = synthesize(model, text, latents, seed, temperature, language)
        gen_s += time.perf_counter() - t
        audio_s += len(wav) / 24000
    rtf = gen_s / audio_s
    hours = rtf * 7 * 1.2
    print(f"RTF={rtf:.2f}  ->  7-часовая книга ~{hours:.0f} ч с запасом на переозвучку")
    print("вердикт:", "локально ок" if rtf < 4 else "на грани" if rtf < 8 else "арендовать GPU")
    return 0
