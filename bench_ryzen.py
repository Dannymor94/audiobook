"""Throughput bench for worker layouts on multi-core CPU (Ryzen target).

Usage:
    uv run python bench_ryzen.py --layout 2x4
    uv run python bench_ryzen.py --all      # 1x8, 2x4, 3x2, 4x2 in sequence

Reports: audio-seconds rendered per wall-second, for 10 real ch13 chunks.
Run on the Ryzen; send the output back for scheduling decisions.
"""
from __future__ import annotations

import argparse
import multiprocessing
import time
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

def _load_chunks(n: int = 10) -> list[str]:
    root = Path(__file__).parent
    norm_files = sorted((root / "text").glob("20_glava_13*.norm.txt"))
    if not norm_files:
        raise FileNotFoundError("text/20_glava_13*.norm.txt not found — run from repo root")
    lines = [
        ln.strip()
        for ln in norm_files[0].read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    return lines[:n]


def _load_wcfg(num_workers: int) -> dict:
    import yaml
    from audiobook import paths
    from audiobook.synth import cap_params
    from audiobook.device import pick_device

    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    ref = paths.ROOT / config["reference"]["path"]
    return {
        "device": pick_device(),
        "latents_path": str(ref.with_suffix(".latents.pt")),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
        "num_workers": num_workers,
    }


# ── per-process worker ────────────────────────────────────────────────────────

def _run_worker(wcfg: dict, texts: list[str], base_seed: int, timeout_s: float, q) -> None:
    import time as _time
    from audiobook.worker import TimeoutSynth

    audio_s = 0.0
    t0 = _time.perf_counter()
    with TimeoutSynth(wcfg, timeout_s) as engine:
        for i, text in enumerate(texts):
            wav = engine.synth(text, base_seed + i)
            if wav is not None:
                audio_s += len(wav) / 24_000
    q.put((audio_s, _time.perf_counter() - t0))


# ── layout runner ─────────────────────────────────────────────────────────────

def run_layout(layout: str, chunks: list[str], timeout_s: float) -> None:
    n_str, t_str = layout.split("x")
    n_workers, threads_each = int(n_str), int(t_str)

    wcfg = _load_wcfg(n_workers)
    ctx = multiprocessing.get_context("spawn")
    q: multiprocessing.Queue = ctx.Queue()

    # distribute chunks round-robin
    groups: list[list[str]] = [[] for _ in range(n_workers)]
    for i, chunk in enumerate(chunks):
        groups[i % n_workers].append(chunk)

    t_wall = time.perf_counter()
    procs = [
        ctx.Process(target=_run_worker, args=(wcfg, groups[i], 42 + i * 100, timeout_s, q))
        for i in range(n_workers)
    ]
    for p in procs:
        p.start()
    results = [q.get() for _ in procs]
    for p in procs:
        p.join()
    wall = time.perf_counter() - t_wall

    audio_total = sum(r[0] for r in results)
    throughput = audio_total / wall if wall else 0.0
    rtf_each = wall / (audio_total / n_workers) if audio_total else float("nan")

    print(
        f"layout={layout}  workers={n_workers}  threads_each={threads_each}"
        f"  chunks={len(chunks)}  audio={audio_total:.1f}s"
        f"  wall={wall:.1f}s  throughput={throughput:.3f} audio-s/wall-s"
        f"  RTF_per_worker≈{rtf_each:.1f}x"
    )


# ── main ──────────────────────────────────────────────────────────────────────

LAYOUTS = ["1x8", "2x8", "4x4", "8x2"]

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)

    import yaml
    from audiobook import paths

    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    _timeout_s = _config.get("render", {}).get("chunk_timeout_s", 600)

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--layout", choices=LAYOUTS, help="e.g. 2x8")
    group.add_argument("--all", action="store_true", help="run all layouts in sequence")
    args = parser.parse_args()

    chunks = _load_chunks(10)
    print(f"bench_ryzen: {len(chunks)} chunks from ch13, timeout={_timeout_s}s each")

    layouts = LAYOUTS if args.all else [args.layout]
    for layout in layouts:
        run_layout(layout, chunks, _timeout_s)
