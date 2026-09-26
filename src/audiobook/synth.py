"""Qwen3-TTS-12Hz-0.6B-Base synthesis: load model, compute/cache the reusable
voice-clone prompt (speaker x-vector), synthesise.

The model is loaded from the LOCAL HF snapshot directory, not by repo-id: under
HF_HUB_OFFLINE=1 the tokenizer's is_base_mistral() probe hits the network for a
repo-id and aborts, but a local path sets _is_local=True and skips it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from audiobook import leadin, paths
from audiobook.device import pick_device

log = logging.getLogger(__name__)

_SAMPLE_RATE = 24000
# Qwen3-TTS-12Hz: the talker emits 12 codec tokens per second of audio, so a
# token budget converts directly to an audio-length cap.
_CODEC_HZ = 12


class CapExceeded(Exception):
    """Generation saturated its max_new_tokens budget — a runaway, not real
    speech. Raised so the caller can retry with the next seed cheaply instead of
    waiting out the wall-clock timeout."""


def max_tokens_for_text(text: str, base_ms: float, ms_per_char: float,
                        margin: float) -> int:
    """Codec-token budget for a chunk, from its char length. A runaway then ends
    in seconds (budget hit) instead of running to the 120s timeout.

    audio_ms = (base_ms + chars·ms_per_char)·margin, tokens = audio_ms·12/1000.
    base_ms covers per-chunk fixed overhead (leading/trailing silence + the
    sentinel) that dominates very short chunks; ms_per_char + margin keep the cap
    generously above real speech so a legit chunk is never truncated."""
    audio_ms = (base_ms + len(text) * ms_per_char) * margin
    return max(1, math.ceil(audio_ms / 1000 * _CODEC_HZ))


def cap_params(config: dict) -> dict | None:
    """Length-cap kwargs for max_tokens_for_text, from config.render. None
    disables the cap (worker generates open-ended, guarded only by the timeout)."""
    r = config.get("render", {})
    if "cap_ms_per_char" not in r:
        return None
    return {
        "base_ms": r.get("cap_base_ms", 3000),
        "ms_per_char": r["cap_ms_per_char"],
        "margin": r.get("cap_margin", 1.5),
    }

_QWEN_HUB_DIR = (
    paths.MODELS / "hf" / "hub" / "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base"
)

# Qwen wants a language *name*; config.yaml carries short codes. Extend as needed.
_LANG_NAMES = {
    "ru": "russian", "en": "english", "de": "german", "fr": "french",
    "es": "spanish", "it": "italian", "pt": "portuguese", "ja": "japanese",
    "ko": "korean", "zh": "chinese",
}

_model = None


def _local_snapshot() -> Path:
    """Resolve the local snapshot dir (loading by path avoids the offline probe)."""
    snaps = _QWEN_HUB_DIR / "snapshots"
    if not snaps.is_dir():
        raise FileNotFoundError(
            f"Qwen3-TTS weights missing: {_QWEN_HUB_DIR}\n"
            "Copy models/ from the project drive."
        )
    ref = _QWEN_HUB_DIR / "refs" / "main"
    if ref.is_file():
        commit = ref.read_text(encoding="utf-8").strip()
        cand = snaps / commit
        if cand.is_dir():
            return cand
    dirs = sorted(p for p in snaps.iterdir() if p.is_dir())
    if not dirs:
        raise FileNotFoundError(f"No snapshot under {snaps}")
    return dirs[-1]


def load_model(device: str | None = None):
    global _model
    if _model is not None:
        return _model
    dev = device or pick_device()
    # Qwen's custom generate() mixes CPU/MPS tensors — run on cuda or cpu only.
    # cpu is the Windows render target anyway.
    if dev == "mps":
        dev = "cpu"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    snapshot = _local_snapshot()  # raises with a clear message if weights absent
    from qwen_tts import Qwen3TTSModel  # heavy + noisy import: keep it lazy
    model = Qwen3TTSModel.from_pretrained(str(snapshot), dtype=torch.float32)
    model.model.to(dev)
    _model = model
    return model


# ── voice-clone prompt ("latents"): computed once, cached in ref/ ─────────────

def _item_to_dict(item) -> dict:
    return {
        "ref_code": item.ref_code,
        "ref_spk_embedding": item.ref_spk_embedding,
        "x_vector_only_mode": item.x_vector_only_mode,
        "icl_mode": item.icl_mode,
        "ref_text": item.ref_text,
    }


def _dict_to_items(latents: dict) -> list:
    from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem
    return [VoiceClonePromptItem(**d) for d in latents["items"]]


def compute_latents(model, ref_wav: Path, ref_text: str | None = None) -> dict:
    """Precompute the reusable voice-clone prompt once (project invariant:
    reference latents are computed once and live in ref/).
    Pass ref_text for full-clone (ICL) mode; omit for x-vector-only."""
    if ref_text is not None:
        items = model.create_voice_clone_prompt(
            ref_audio=str(ref_wav), ref_text=ref_text, x_vector_only_mode=False
        )
    else:
        items = model.create_voice_clone_prompt(
            ref_audio=str(ref_wav), x_vector_only_mode=True
        )
    return {"items": [_item_to_dict(i) for i in items]}


def save_latents(latents: dict, path: Path) -> None:
    torch.save(latents, str(path))


def load_latents(path: Path) -> dict:
    return torch.load(str(path), map_location="cpu", weights_only=True)


def _feed_hash(h, obj) -> None:
    if isinstance(obj, torch.Tensor):
        h.update(b"T")
        h.update(str(tuple(obj.shape)).encode("utf-8"))
        h.update(str(obj.dtype).encode("utf-8"))
        h.update(obj.detach().cpu().contiguous().numpy().tobytes())
    elif isinstance(obj, dict):
        h.update(b"D")
        for k in sorted(obj):
            h.update(repr(k).encode("utf-8"))
            _feed_hash(h, obj[k])
    elif isinstance(obj, (list, tuple)):
        h.update(b"L")
        for x in obj:
            _feed_hash(h, x)
    else:
        h.update(b"S")
        h.update(repr(obj).encode("utf-8"))


def latents_sha1(latents: dict) -> str:
    """Content hash of the latents, stable across save/load and process runs."""
    h = hashlib.sha1()
    _feed_hash(h, latents)
    return h.hexdigest()


# ── per-chunk seed ────────────────────────────────────────────────────────────

def seed_for_chunk(chunk_hash: str) -> int:
    """Deterministic torch seed for a chunk, derived from its hash. Same chunk →
    same seed on every machine and run, so a re-render reproduces byte-for-byte."""
    return int(chunk_hash[:8], 16)


# ── sentinel (kept: Qwen still clips chunk tails without it) ───────────────────

# Chunks ending in these characters already give the model a natural stop signal;
# appending a sentinel would add audible speech to their output.
_TERMINAL = frozenset(".!?…:;»\"")


def apply_sentinel(text: str, sentinel: str) -> str:
    """Append sentinel only when text has no terminal punctuation."""
    if not sentinel:
        return text
    last = text.rstrip()
    if last and last[-1] in _TERMINAL:
        return text
    return text + sentinel


def strip_sentinel(text: str, sentinel: str) -> str:
    """Inverse of apply_sentinel on the text seam (audio trim happens at assembly)."""
    if sentinel and text.endswith(sentinel):
        return text[: -len(sentinel)]
    return text


def prepare_synth_text(text: str, config: dict, table: dict,
                       sentinel: str) -> tuple[str, str | None]:
    """The exact string fed to the model for a chunk, plus the lead-in carrier if
    one fires. Order: pad (short chunks) → respell (stress dict) → sentinel — the
    chunk hash (chunker.chunk_hash) is built the same way. Returns
    ``(synth_text, phrase|None)``; pass ``phrase`` as ``engine.synth(..., leadin=)``
    so a padded chunk gets the carrier trimmed off. The single source of truth for
    synthesis input, shared by render, redo, and qc re-synth — so no path can
    quietly drop the padding and let the drift back in."""
    from audiobook.pronounce import respell
    phrase = leadin.fires(text, config)
    base = leadin.pad(text, phrase) if phrase else text
    return apply_sentinel(respell(base, table), sentinel), phrase


# ── synthesis ─────────────────────────────────────────────────────────────────

def synthesize(
    model,
    text: str,
    latents: dict,
    seed: int,
    temperature: float,
    language: str = "ru",
    speed: float = 1.0,
    max_new_tokens: int | None = None,
) -> np.ndarray:
    # Qwen3-TTS-0.6B has no speed control; tempo is governed by the reference
    # (validated: a longer reference yields slower speech). Fail loud rather than
    # silently ignore a speed the caller expects to take effect.
    if speed != 1.0:
        raise NotImplementedError(
            "Qwen3-TTS-0.6B has no speed control; tempo follows the reference"
        )
    torch.manual_seed(seed)
    lang = _LANG_NAMES.get(language.lower(), language)
    kw = {} if max_new_tokens is None else {"max_new_tokens": max_new_tokens}
    wavs, _sr = model.generate_voice_clone(
        text=text,
        language=lang,
        voice_clone_prompt=_dict_to_items(latents),
        temperature=temperature,
        **kw,
    )
    wav = np.asarray(wavs[0], dtype=np.float32)
    # Saturating the budget means the model never emitted a stop — a runaway, not
    # speech. Flag it so the caller retries the next seed instead of caching garbage.
    if max_new_tokens is not None:
        cap_s = max_new_tokens / _CODEC_HZ
        if len(wav) / _SAMPLE_RATE >= cap_s * 0.95:
            raise CapExceeded(f"generation hit {max_new_tokens}-token cap ({cap_s:.1f}s)")
    return wav


# ── synth stage: render a section's chunks, cached and resumable ───────────────

def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_manifest(path: Path, rows: list[dict]) -> None:
    """Atomic: write to a temp file then rename, so an interrupt never leaves a
    half-written manifest (cache is the source of resumability)."""
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def render_section(engine, sec_dir: Path, config: dict) -> tuple[int, int, int, float]:
    """Synthesise every not-yet-done chunk of one section via ``engine`` (a
    TimeoutSynth or any object with ``synth(text, seed) -> ndarray | None``).
    Returns (synthesised, skipped, timed_out, synth_audio_s). Skips a chunk whose
    status is 'done' AND whose wav is on disk; writes each wav atomically and
    persists the manifest after each one. A chunk that exceeds the engine timeout
    (engine returns None) is marked status 'timeout', logged, and the run
    continues — it stays not-done, so a later run retries it."""
    manifest_path = sec_dir / "manifest.jsonl"
    rows = _read_manifest(manifest_path)
    chunks_dir = sec_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    sentinel = config["model"].get("sentinel", "")
    retries = config.get("render", {}).get("timeout_retries", 2)
    from audiobook.pronounce import load_table
    table = load_table()

    synthesised = skipped = timed_out = 0
    synth_audio_s = 0.0
    for row in rows:
        wav_path = chunks_dir / f"{row['id']}.wav"
        if row.get("status") == "done" and wav_path.exists():
            skipped += 1
            continue
        seed_ov = row.get("seed_override")
        base_seed = seed_ov if seed_ov is not None else seed_for_chunk(row["hash"])
        # Short chunk → prepend the context lead-in (cut back off after synth).
        synth_text, phrase = prepare_synth_text(row["text"], config, table, sentinel)
        synth_kw = {"leadin": phrase} if phrase else {}
        # The per-chunk seed is deterministic, so a hang would recur every run.
        # Retry with derived alternate seeds (base+1, base+2, …) so a sampling-
        # triggered hang can escape; only a hang across all seeds is a "timeout".
        wav = None
        used_seed = base_seed
        for attempt in range(retries + 1):
            used_seed = base_seed + attempt
            wav = engine.synth(synth_text, used_seed, **synth_kw)
            if wav is not None:
                break
            log.warning("chunk %s timed out (seed %d, attempt %d/%d): %r",
                        row["id"], used_seed, attempt + 1, retries + 1, row["text"])
        if wav is None:  # exhausted retries — kept alive by engine, next chunk continues
            row["status"] = "timeout"
            row["seed"] = base_seed
            row["duration_ms"] = None
            _write_manifest(manifest_path, rows)
            timed_out += 1
            continue
        tmp = wav_path.parent / (wav_path.name + ".part")
        sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
        tmp.replace(wav_path)
        row["status"] = "done"
        row["seed"] = used_seed  # the seed that actually produced this wav
        row["duration_ms"] = round(len(wav) / _SAMPLE_RATE * 1000)
        _write_manifest(manifest_path, rows)  # persist progress per chunk
        synthesised += 1
        synth_audio_s += len(wav) / _SAMPLE_RATE
    return synthesised, skipped, timed_out, synth_audio_s


def _render_group_worker(wcfg, timeout_s, sentinel, retries, group,
                         chunks_dir_str, out_q, config) -> None:
    """Child (spawn): synth a disjoint subset of chunk rows via one TimeoutSynth,
    write each wav atomically, and report each result on out_q as it lands. The
    PARENT owns the manifest — workers never touch it, so parallel workers cannot
    race on it. wcfg["num_workers"] tells the TimeoutSynth child how to divide
    CPU threads. Ends with a ``None`` sentinel."""
    import soundfile as sf
    from audiobook.pronounce import load_table
    from audiobook.worker import TimeoutSynth

    table = load_table()
    chunks_dir = Path(chunks_dir_str)
    with TimeoutSynth(wcfg, timeout_s) as engine:
        for row in group:
            seed_ov = row.get("seed_override")
            base = seed_ov if seed_ov is not None else seed_for_chunk(row["hash"])
            synth_text, phrase = prepare_synth_text(row["text"], config, table, sentinel)
            synth_kw = {"leadin": phrase} if phrase else {}
            wav, used = None, base
            for attempt in range(retries + 1):
                used = base + attempt
                wav = engine.synth(synth_text, used, **synth_kw)
                if wav is not None:
                    break
            if wav is None:
                out_q.put({"id": row["id"], "status": "timeout", "seed": base})
                continue
            wav_path = chunks_dir / f"{row['id']}.wav"
            tmp = wav_path.parent / (wav_path.name + ".part")
            sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
            tmp.replace(wav_path)
            out_q.put({"id": row["id"], "status": "done", "seed": used,
                       "duration_ms": round(len(wav) / _SAMPLE_RATE * 1000),
                       "audio_s": len(wav) / _SAMPLE_RATE})
    out_q.put(None)


def _plan_parallel(rows: list[dict], chunks_dir: Path, num_workers: int
                   ) -> tuple[list[list[dict]], int]:
    """Split rows into `num_workers` round-robin groups of the not-yet-done chunks.
    A chunk is done (skipped) only if status=='done' AND its wav is on disk, so a
    manifest that claims done but lost its wav is re-synthesised. Round-robin (not
    contiguous) so no worker gets a run of unusually long chunks. Pure — the
    resume/partition correctness is unit-tested without models."""
    todo = [r for r in rows
            if not (r.get("status") == "done" and (chunks_dir / f"{r['id']}.wav").exists())]
    skipped = len(rows) - len(todo)
    groups: list[list[dict]] = [[] for _ in range(num_workers)]
    for i, row in enumerate(todo):
        groups[i % num_workers].append(row)
    return groups, skipped


def render_section_parallel(sec_dir: Path, config: dict, wcfg: dict, timeout_s: float,
                            num_workers: int) -> tuple[int, int, int, float]:
    """Parallel render: N worker processes synth disjoint chunk subsets; this
    parent drains results and persists the manifest after each one (resume stays
    intact — a crash loses at most the in-flight chunks, whose wavs weren't
    renamed). Same (respell → sentinel → retry) logic and per-chunk seeds as
    render_section, so output matches the single-worker path chunk-for-chunk."""
    import multiprocessing as mp

    manifest_path = sec_dir / "manifest.jsonl"
    rows = _read_manifest(manifest_path)
    chunks_dir = sec_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    by_id = {r["id"]: r for r in rows}

    groups, skipped = _plan_parallel(rows, chunks_dir, num_workers)
    if not any(groups):
        return 0, skipped, 0, 0.0

    sentinel = config["model"].get("sentinel", "")
    retries = config.get("render", {}).get("timeout_retries", 2)

    ctx = mp.get_context("spawn")
    out_q = ctx.Queue()
    procs = [
        ctx.Process(target=_render_group_worker,
                    args=(wcfg, timeout_s, sentinel, retries, groups[w],
                          str(chunks_dir), out_q, config))
        for w in range(num_workers) if groups[w]
    ]
    for p in procs:
        p.start()

    synthesised = timed_out = 0
    synth_audio_s = 0.0
    live = len(procs)
    while live:
        res = out_q.get()
        if res is None:
            live -= 1
            continue
        row = by_id[res["id"]]
        row["status"] = res["status"]
        row["seed"] = res["seed"]
        if res["status"] == "done":
            row["duration_ms"] = res["duration_ms"]
            synthesised += 1
            synth_audio_s += res["audio_s"]
        else:
            row["duration_ms"] = None
            timed_out += 1
        _write_manifest(manifest_path, rows)  # single writer, per-chunk persistence
    for p in procs:
        p.join()
    return synthesised, skipped, timed_out, synth_audio_s


def run(config: dict, section: str | None = None, num_workers: int = 1) -> int:
    if not section:
        raise SystemExit("synth: --section обязателен (иначе отрендерится вся книга)")
    sec_dir = paths.OUT / "sections" / section
    if not (sec_dir / "manifest.jsonl").exists():
        raise SystemExit(f"нет манифеста для секции {section}: {sec_dir}")

    ref = paths.ROOT / config["reference"]["path"]
    rcfg = config.get("render", {})
    timeout_s = rcfg.get("chunk_timeout_s", 120)
    wcfg = {
        "device": pick_device(),
        "latents_path": str(ref.with_suffix(".latents.pt")),
        "temperature": config["model"]["temperature"],
        "language": config["model"]["language"],
        "cap": cap_params(config),
        "num_workers": num_workers,  # TimeoutSynth child divides CPU threads by this
    }

    t0 = time.perf_counter()
    if num_workers > 1:
        synthesised, skipped, timed_out, synth_audio_s = render_section_parallel(
            sec_dir, config, wcfg, timeout_s, num_workers)
    else:
        from audiobook.worker import TimeoutSynth
        with TimeoutSynth(wcfg, timeout_s) as engine:
            synthesised, skipped, timed_out, synth_audio_s = render_section(engine, sec_dir, config)
    wall = time.perf_counter() - t0

    rows = _read_manifest(sec_dir / "manifest.jsonl")
    total_audio_s = sum((r.get("duration_ms") or 0) for r in rows) / 1000
    # RTF over audio produced THIS run, so a resume reports its own real cost.
    rtf = wall / synth_audio_s if synth_audio_s else float("nan")
    print(f"section={section}  chunks={len(rows)}  synthesised={synthesised}  "
          f"skipped={skipped}  timeout={timed_out}")
    print(f"wall={wall:.1f}s  audio(this run)={synth_audio_s:.1f}s  "
          f"audio(section)={total_audio_s:.1f}s  RTF={rtf:.2f}x")
    if timed_out:
        for r in rows:
            if r.get("status") == "timeout":
                print(f"  TIMEOUT {r['id']}: {r['text']!r}")
    return 0
