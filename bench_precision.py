"""Precision/quantization bench for the memory-bandwidth wall (Ryzen CPU).

The 0.6B talker runs fp32: ~2.5 GB of weights streamed per generation step,
so a dual-channel Ryzen is bandwidth-bound (1 worker RTF ~5, 4 workers only
+37%). This measures whether a smaller weight footprint breaks the wall.

Variants:  fp32 (baseline) | bf16 | fp16 | int8  (dynamic quant on Linears)

Modes:
    --probe                       load each variant, synth 1 chunk, report ok/fail+time
    --variant V --layout NxT      full throughput bench, save WAVs for CER
    --cer V                       whisper-transcribe variant's saved WAVs, report CER
    --variant V --layout 4x4 --interop N   set interop threads (inter- vs intra-op test)

WAVs land in out/bench_precision/<variant>/ ; CER compares whisper transcript to
the chunk text (same normalize_for_cer + threshold as production QC).
"""
from __future__ import annotations

import argparse
import multiprocessing
import time
from pathlib import Path

VARIANTS = ["fp32", "bf16", "fp16", "int8"]
LAYOUTS = ["1x8", "2x8", "4x4", "8x2"]
_SR = 24_000


def _load_chunks(n: int = 10) -> list[str]:
    root = Path(__file__).parent
    norm_files = sorted((root / "text").glob("20_glava_13*.norm.txt"))
    if not norm_files:
        raise FileNotFoundError("text/20_glava_13*.norm.txt not found — run from repo root")
    lines = [ln.strip() for ln in norm_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[:n]


def _wav_dir(variant: str) -> Path:
    from audiobook import paths
    d = paths.OUT / "bench_precision" / variant
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── model loading per variant ──────────────────────────────────────────────────

def _load_model_variant(variant: str, device: str):
    """Load Qwen3-TTS with the given precision/quantization. Raises on failure so
    the caller can report a variant as non-viable rather than silently degrade."""
    import torch
    from audiobook.synth import _local_snapshot
    from qwen_tts import Qwen3TTSModel

    snapshot = _local_snapshot()
    if variant == "fp32":
        model = Qwen3TTSModel.from_pretrained(str(snapshot), dtype=torch.float32)
        model.model.to(device)
    elif variant == "bf16":
        model = Qwen3TTSModel.from_pretrained(str(snapshot), dtype=torch.bfloat16)
        model.model.to(device)
    elif variant == "fp16":
        model = Qwen3TTSModel.from_pretrained(str(snapshot), dtype=torch.float16)
        model.model.to(device)
    elif variant == "int8":
        model = Qwen3TTSModel.from_pretrained(str(snapshot), dtype=torch.float32)
        model.model.to(device)
        # Dynamic quant: int8 weights, fp32 activations dequantized per-op. Only
        # Linear layers — the codec/conv path stays fp32. fbgemm backend on x86.
        # inplace=True skips quantize_dynamic's copy.deepcopy, which chokes on a
        # dict_keys the Qwen model holds ("cannot pickle 'dict_keys' object").
        torch.ao.quantization.quantize_dynamic(
            model.model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True
        )
    else:
        raise ValueError(f"unknown variant: {variant}")
    return model


# ── per-process worker ──────────────────────────────────────────────────────────

def _run_worker(variant, texts, seeds, wcfg, save_dir, num_workers, interop, q,
                retries=0) -> None:
    import os as _os
    _n = str(max(1, (_os.cpu_count() or 16) // num_workers))
    for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        _os.environ[_var] = _n

    import resource
    import numpy as np
    import soundfile as sf
    import torch
    from audiobook.synth import (
        CapExceeded, load_latents, max_tokens_for_text, synthesize,
    )
    from audiobook.pronounce import load_table, respell
    from audiobook.synth import apply_sentinel

    torch.set_num_threads(max(1, (_os.cpu_count() or 16) // num_workers))
    if interop:
        try:
            torch.set_num_interop_threads(interop)
        except RuntimeError:
            pass  # already set once this process; ignore

    try:
        model = _load_model_variant(variant, wcfg["device"])
    except Exception as e:  # variant not viable in a worker
        q.put({"error": repr(e)})
        return

    latents = load_latents(wcfg["latents_path"])
    cap = wcfg["cap"]
    table = load_table()
    sentinel = wcfg["sentinel"]

    audio_s = 0.0
    done = capped = attempts = 0
    t0 = time.perf_counter()
    for text, seed, idx in zip(texts, seeds, range(len(texts))):
        synth_text = apply_sentinel(respell(text, table), sentinel)
        mnt = max_tokens_for_text(synth_text, **cap) if cap else None
        # Production retry: a capped (runaway) generation retries with the next
        # deterministic seed, up to `retries` extra attempts. retries=0 → measure
        # raw generation only (capped chunks skipped, counted).
        wav = None
        for att in range(retries + 1):
            attempts += 1
            try:
                wav = synthesize(model, synth_text, latents, seed + att,
                                 wcfg["temperature"], wcfg["language"], max_new_tokens=mnt)
                break
            except CapExceeded:
                capped += 1
                wav = None
        if wav is None:
            continue
        done += 1
        audio_s += len(wav) / _SR
        if save_dir:
            gid = seeds[0] * 1000 + idx  # unique per (worker, chunk)
            sf.write(str(Path(save_dir) / f"{gid:07d}.wav"),
                     np.asarray(wav, dtype=np.float32), _SR, subtype="PCM_16", format="WAV")
    wall = time.perf_counter() - t0
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # Linux: KB
    q.put({"audio_s": audio_s, "wall": wall, "peak_mb": peak_kb / 1024,
           "done": done, "capped": capped, "attempts": attempts})


def _wcfg() -> dict:
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
        "sentinel": config["model"].get("sentinel", ""),
        "cap": cap_params(config),
    }


def run_layout(variant, layout, chunks, save_wav, interop, retries=0):
    n_workers, threads_lbl = (int(x) for x in layout.split("x"))
    wcfg = _wcfg()
    save_dir = str(_wav_dir(variant)) if save_wav else None
    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()

    groups: list[list[int]] = [[] for _ in range(n_workers)]
    for i in range(len(chunks)):
        groups[i % n_workers].append(i)

    t_wall = time.perf_counter()
    procs = []
    for w in range(n_workers):
        idxs = groups[w]
        texts = [chunks[i] for i in idxs]
        seeds = [42 + w * 100 + k for k in range(len(idxs))]
        p = ctx.Process(target=_run_worker,
                        args=(variant, texts, seeds, wcfg, save_dir, n_workers, interop, q, retries))
        procs.append(p)
        p.start()
    results = [q.get() for _ in procs]
    for p in procs:
        p.join()
    wall = time.perf_counter() - t_wall

    errs = [r["error"] for r in results if "error" in r]
    if errs:
        print(f"variant={variant} layout={layout}  FAILED: {errs[0]}")
        return None
    audio_total = sum(r["audio_s"] for r in results)
    peak_mb = max(r["peak_mb"] for r in results)
    done = sum(r["done"] for r in results)
    capped = sum(r["capped"] for r in results)
    attempts = sum(r["attempts"] for r in results)
    thr = audio_total / wall if wall else 0.0
    tag = f" interop={interop}" if interop else ""
    rtag = f" retries={retries}" if retries else ""
    print(f"variant={variant} layout={layout}{tag}{rtag}  workers={n_workers}  "
          f"done={done} capped={capped} attempts={attempts}  "
          f"audio={audio_total:.1f}s  wall={wall:.1f}s  "
          f"throughput={thr:.3f} audio-s/wall-s  peak_RAM/worker={peak_mb:.0f}MB")
    return thr


def probe(chunks, variants=None):
    """Load each variant, synth 1 chunk in-process, report viability + wall."""
    from audiobook.synth import (
        load_latents, max_tokens_for_text, synthesize, apply_sentinel,
    )
    from audiobook.pronounce import load_table, respell
    wcfg = _wcfg()
    latents = load_latents(wcfg["latents_path"])
    table = load_table()
    text = apply_sentinel(respell(chunks[1], table), wcfg["sentinel"])  # a real sentence
    mnt = max_tokens_for_text(text, **wcfg["cap"]) if wcfg["cap"] else None
    for v in (variants or VARIANTS):
        try:
            t0 = time.perf_counter()
            model = _load_model_variant(v, wcfg["device"])
            load_s = time.perf_counter() - t0
            t1 = time.perf_counter()
            wav = synthesize(model, text, latents, 42, wcfg["temperature"],
                             wcfg["language"], max_new_tokens=mnt)
            gen_s = time.perf_counter() - t1
            audio_s = len(wav) / _SR
            print(f"probe {v:5s}: OK   load={load_s:.1f}s  gen={gen_s:.1f}s  "
                  f"audio={audio_s:.1f}s  RTF={gen_s/audio_s:.1f}x")
            del model
            import gc; gc.collect()
        except Exception as e:
            print(f"probe {v:5s}: FAIL — {type(e).__name__}: {e}")


def run_cer(variant, chunks):
    """Whisper-transcribe the variant's saved WAVs, CER vs chunk text."""
    from audiobook.qc import load_whisper, transcribe, cer
    wav_dir = _wav_dir(variant)
    wavs = sorted(wav_dir.glob("*.wav"))
    if not wavs:
        print(f"cer {variant}: no WAVs in {wav_dir} — run the bench with --save-wav first")
        return
    # Map WAV back to chunk index: gid = seeds[0]*1000 + idx, but seeds differ per
    # layout. Simpler: WAVs saved from a single-worker run are in chunk order.
    # We rely on the caller saving from a 1x8 run (one worker, seeds 42..).
    wm = load_whisper()
    try:
        cers = []
        for wav in wavs:
            # recover chunk idx from filename: gid = 42*1000 + idx  (1-worker run)
            gid = int(wav.stem)
            idx = gid - 42_000
            if not (0 <= idx < len(chunks)):
                continue
            txt = transcribe(wm, wav)
            c = cer(chunks[idx], txt)
            cers.append(c)
            print(f"  chunk[{idx}] CER={c:.4f}")
    finally:
        del wm
        import gc; gc.collect()
    if cers:
        import statistics
        print(f"cer {variant}: mean={statistics.mean(cers):.4f}  "
              f"median={statistics.median(cers):.4f}  max={max(cers):.4f}  "
              f"n={len(cers)}  (threshold 0.05)")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--variants", help="comma list to restrict probe, e.g. int8")
    ap.add_argument("--variant", choices=VARIANTS)
    ap.add_argument("--layout", choices=LAYOUTS)
    ap.add_argument("--all-layouts", action="store_true", help="run 1x8 and 4x4")
    ap.add_argument("--save-wav", action="store_true")
    ap.add_argument("--interop", type=int, default=0)
    ap.add_argument("--retries", type=int, default=0,
                    help="production-style retry of capped chunks with next seed")
    ap.add_argument("--cer", choices=VARIANTS)
    args = ap.parse_args()

    chunks = _load_chunks(10)
    print(f"bench_precision: {len(chunks)} chunks from ch13")

    if args.probe:
        vs = args.variants.split(",") if args.variants else None
        probe(chunks, vs)
    elif args.cer:
        run_cer(args.cer, chunks)
    elif args.variant:
        layouts = ["1x8", "4x4"] if args.all_layouts else [args.layout or "4x4"]
        for lay in layouts:
            run_layout(args.variant, lay, chunks, args.save_wav, args.interop, args.retries)
    else:
        ap.error("need one of --probe / --variant / --cer")
