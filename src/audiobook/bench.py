"""RTF bench: N parallel workers × T torch threads, the same way a section
render loads the machine. Used to pick ``render.cpu_threads``.

    ./run.sh bench                       # 1 worker, default threads
    ./run.sh bench --workers 2 --threads 6

Effective RTF = slowest worker's synthesis time / total audio of all workers —
the number that sets the book's wall time. Model loading is excluded.
"""
from __future__ import annotations

import time

from . import voicecfg
from .device import pick_device, threads_per_worker

# Placeholder phrases (not quotes from the book).
SAMPLES = [
    "Ты не поломан. Ты просто давно не слышал себя.",
    "Каждая маска когда-то была защитой. Потом она стала привычкой.",
    "Мы редко замечаем момент, когда устаём быть сильными.",
    "Тело помнит то, что ум предпочёл забыть.",
    "Иногда самое честное, что можно сделать, — остановиться.",
]


def effective_rtf(results: list[tuple[float, float]]) -> float:
    """[(synth_seconds, audio_seconds)] per worker → slowest synth / total audio."""
    audio = sum(a for _g, a in results)
    return max(g for g, _a in results) / audio if audio else float("inf")


def _bench_proc(config: dict, workers: int, threads: int, out_q) -> None:
    """Spawn child: pin BLAS threads before torch loads, then synth SAMPLES."""
    import os
    for var in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[var] = str(threads)
    from .device import configure_cpu_threads
    from .synth import load_latents, load_model, synthesize
    configure_cpu_threads(workers, override=threads)
    model = load_model(pick_device(), voicecfg.variant(config), voicecfg.quantize(config))
    latents = load_latents(voicecfg.latents_path(config))
    m = config["model"]
    out_q.put("ready")
    gen_s = audio_s = 0.0
    for text in SAMPLES:
        t = time.perf_counter()
        wav = synthesize(model, text, latents, m["seed"], m["temperature"], m["language"])
        gen_s += time.perf_counter() - t
        audio_s += len(wav) / 24000
    out_q.put((gen_s, audio_s))


def run(config: dict, workers: int = 1, threads: int | None = None) -> int:
    import multiprocessing as mp
    lat_path = voicecfg.latents_path(config)
    if not lat_path.exists():
        raise SystemExit(f"нет латентов {lat_path} — посчитать один раз (README)")
    t = threads_per_worker(workers, threads)
    print(f"device={pick_device()}  workers={workers}  threads/worker={t}")
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    procs = [ctx.Process(target=_bench_proc, args=(config, workers, t, q)) for _ in range(workers)]
    t0 = time.perf_counter()
    for p in procs:
        p.start()
    results: list[tuple[float, float]] = []
    ready = 0
    while len(results) < workers:
        msg = q.get(timeout=3600)
        if msg == "ready":
            ready += 1
            if ready == workers:
                print(f"load: {time.perf_counter() - t0:.1f}s")
        else:
            results.append(msg)
    for p in procs:
        p.join()
    rtf = effective_rtf(results)
    print(f"RTF={rtf:.2f}  (workers={workers}, threads/worker={t})  "
          f"→ 12 ч звука ≈ {rtf * 12 / 24:.1f} сут")
    return 0
