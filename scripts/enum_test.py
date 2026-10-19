"""
Enumeration-pause test: render ch13 0015-0022 three ways.

  current  — cached wavs, no enum split
  150      — enum commas split to sub-fragments, 150ms pause
  250      — enum commas split to sub-fragments, 250ms pause

Enum rule: a depth-0 comma is an enumeration boundary if both adjacent
segments are ≤ 20 chars and neither starts with / contains a subordinating
marker. Em-dash resets the left-segment window.

out/enum_test/{current,150,250}.mp3
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audiobook import leadin, paths
from audiobook.assemble import _fade, _trim_silence
from audiobook.chunker import _depths, _split_sentences
from audiobook.master import master_section
from audiobook.pronounce import load_table, respell
from audiobook.synth import (
    _SAMPLE_RATE, _item_to_dict, apply_sentinel, cap_params, load_latents,
    load_model, max_tokens_for_text, seed_for_chunk, synthesize,
)

_SR = _SAMPLE_RATE
SEC = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
CHUNK_IDS = [f"{n:04d}" for n in range(15, 23)]

PAUSE_SENT = 350   # ms between sentences within a chunk
PAUSE_ENUM = None  # set per variant (150 or 250)

# ── Enumeration rule ──────────────────────────────────────────────────────────

_SUBORD_STARTS = {
    "который", "которая", "которое", "которые", "которого", "которому",
    "которым", "которых", "которую", "которой",
    "когда", "если", "хотя", "пока", "потому", "поскольку", "чтобы",
    "откуда", "зачем", "почему", "несмотря", "кто", "куда", "где", "что",
}
_SUBORD_ANYWHERE = {
    "который", "которая", "которое", "которые", "которого", "которому",
    "которым", "которых", "которую", "которой", "где",
}
_MAX_ITEM = 20
# Age words that signal a byline (Имя, N лет, Город) — not an enumeration
_AGE_WORDS = {"лет", "год", "года"}


def _cw(w: str) -> str:
    return w.strip(".,;:—–!?…»«()[]\"'").lower()


def _has_subord(seg: str) -> bool:
    words = seg.split()
    if not words:
        return False
    if _cw(words[0]) in _SUBORD_STARTS:
        return True
    return bool({_cw(w) for w in words} & _SUBORD_ANYWHERE)


def _enum_splits(sentence: str) -> list[str]:
    """Split a sentence at enumeration commas. Returns [sentence] if none found."""
    depths = _depths(sentence)
    n = len(sentence)
    seg_start = 0
    splits: list[int] = []
    i = 0
    while i < n:
        if sentence[i] in "—–" and depths[i] == 0:
            seg_start = i + 1
            while seg_start < n and sentence[seg_start] == " ":
                seg_start += 1
        elif sentence[i] == "," and depths[i] == 0:
            left = sentence[seg_start:i].strip()
            j = i + 1
            while j < n and sentence[j] == " ":
                j += 1
            k = j
            while k < n and (depths[k] != 0 or sentence[k] not in ",—–.!?…"):
                k += 1
            right = sentence[j:k].strip()
            if (
                len(left) <= _MAX_ITEM and len(right) <= _MAX_ITEM
                and not _has_subord(left) and not _has_subord(right)
                and left and right
            ):
                splits.append(i)
            # always advance segment window past this comma
            seg_start = i + 1
            while seg_start < n and sentence[seg_start] == " ":
                seg_start += 1
        i += 1

    if not splits:
        return [sentence]

    parts: list[str] = []
    prev = 0
    for pos in splits:
        p = sentence[prev:pos].strip()
        if p:
            parts.append(p)
        prev = pos + 1
        while prev < n and sentence[prev] == " ":
            prev += 1
    tail = sentence[prev:].strip()
    if tail:
        parts.append(tail)
    parts = [p for p in parts if p]

    # Byline guard: "Имя, N лет, Город" — any age-word segment → not an enumeration
    def _last_word(p: str) -> str:
        words = p.lower().split()
        return words[-1].strip(".,!?") if words else ""

    if any(_last_word(p) in _AGE_WORDS for p in parts):
        return [sentence]

    return parts


def _chunk_to_fragments(text: str, enum_pause_ms: int) -> list[tuple[str, int, bool]]:
    """Return (fragment_text, pause_after_ms, is_enum_part) triples for a chunk.

    Each sentence is split at enum commas; enum-pause separates enum items,
    PAUSE_SENT separates sentences. is_enum_part=True flags sub-sentence fragments
    from an enum split (used to strip terminal '?' before synthesis).
    """
    sents = _split_sentences(text)
    frags: list[tuple[str, int, bool]] = []
    for si, sent in enumerate(sents):
        parts = _enum_splits(sent)
        is_enum = len(parts) > 1
        last_sent = si == len(sents) - 1
        for pi, part in enumerate(parts):
            last_part = pi == len(parts) - 1
            if last_part and last_sent:
                pause = 0  # caller inserts chunk pause
            elif last_part:
                pause = PAUSE_SENT
            else:
                pause = enum_pause_ms
            frags.append((part, pause, is_enum))
    return frags


# ── Assembly ──────────────────────────────────────────────────────────────────

def _assemble(clips_with_pauses: list[tuple[np.ndarray, int]]) -> np.ndarray:
    parts: list[np.ndarray] = []
    for i, (wav, pause_ms) in enumerate(clips_with_pauses):
        trimmed = _trim_silence(wav)
        parts.append(trimmed)
        if pause_ms > 0:
            parts.append(np.zeros(int(_SR * pause_ms / 1000), dtype=np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def _master_variant(name: str, wav: np.ndarray, config: dict, out_root: Path) -> Path:
    var_dir = out_root / name
    var_dir.mkdir(parents=True, exist_ok=True)
    sf.write(str(var_dir / "section.wav"), wav, _SR, subtype="PCM_16")
    mp3, _ = master_section(var_dir, config)
    dst = out_root / f"{name}.mp3"
    shutil.copy2(mp3, dst)
    return dst


# ── Main ──────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    import yaml  # type: ignore[import]
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _book_wide_count() -> int:
    """Count chunks book-wide that have at least one enum split."""
    touched = 0
    for mf in sorted(paths.OUT.glob("sections/*/manifest.jsonl")):
        for line in mf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if any(len(_enum_splits(s)) > 1 for s in _split_sentences(row["text"])):
                touched += 1
    return touched


def run() -> None:
    config = _load_config()
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    sec_dir = paths.OUT / "sections" / SEC
    manifest = _read_manifest(sec_dir / "manifest.jsonl")
    rows = {r["id"]: r for r in manifest}
    chunks_dir = sec_dir / "chunks"

    out_root = paths.OUT / "enum_test"
    out_root.mkdir(parents=True, exist_ok=True)

    ordered = [rows[cid] for cid in CHUNK_IDS]

    # ── CURRENT: cached wavs, no enum split ───────────────────────────────────
    print("\n=== CURRENT ===")
    current_clips: list[tuple[np.ndarray, int]] = []
    for row in ordered:
        wav_path = chunks_dir / f"{row['id']}.wav"
        if not wav_path.exists():
            raise SystemExit(f"missing cached wav: {wav_path}")
        wav, _ = sf.read(str(wav_path), dtype="float32")
        current_clips.append((wav, row["pause_after_ms"]))
        sents = _split_sentences(row["text"])
        enum_sents = [s for s in sents if len(_enum_splits(s)) > 1]
        tag = f"  [ENUM: {len(enum_sents)} sent]" if enum_sents else ""
        print(f"  {row['id']}  {len(wav)/_SR:.2f}s{tag}  {row['text'][:60]!r}")

    current_wav = _assemble(current_clips)
    current_mp3 = _master_variant("current", current_wav, config, out_root)
    print(f"current.mp3 → {current_mp3}  ({len(current_wav)/_SR:.1f}s)")

    # ── SYNTHESIS: re-render chunks that have enum hits (in-process) ─────────
    needs_synth = {
        row["id"]
        for row in ordered
        if any(len(_enum_splits(s)) > 1 for s in _split_sentences(row["text"]))
    }
    print(f"\n=== SYNTH: {len(needs_synth)} chunks have enum hits: {sorted(needs_synth)} ===")

    from audiobook.device import configure_cpu_threads
    configure_cpu_threads(workers=1)
    model = load_model("cpu")
    lat_path = paths.ROOT / config["reference"]["path"]
    lat_path = lat_path.with_suffix(".latents.pt")
    fixed_latents = load_latents(lat_path)
    cap = cap_params(config)

    # synth_cache: chunk_id → {enum_pause_ms → list[(wav, pause_ms)]}
    synth_cache: dict[str, dict[int, list[tuple[np.ndarray, int]]]] = {}

    for row in ordered:
        if row["id"] not in needs_synth:
            continue
        base_seed = seed_for_chunk(row["hash"])
        synth_cache[row["id"]] = {}

        for enum_pause_ms in (150, 250):
            frags = _chunk_to_fragments(row["text"], enum_pause_ms)
            rendered: list[tuple[np.ndarray, int]] = []
            print(f"\n  {row['id']}  enum_pause={enum_pause_ms}ms  {len(frags)} frags")
            for fi, (frag_text, pause_ms, is_enum) in enumerate(frags):
                # strip terminal '?' from enum sub-fragments: standalone question
                # causes model to generate interrogative continuations and loop
                synth_frag = frag_text.rstrip("?") if is_enum and frag_text.endswith("?") else frag_text
                phrase = leadin.fires(synth_frag, config)
                base = leadin.pad(synth_frag, phrase) if phrase else synth_frag
                synth_text = apply_sentinel(respell(base, table), sentinel)
                seed = base_seed + fi
                mnt = max_tokens_for_text(synth_text, **cap) if cap else None
                torch.manual_seed(seed)
                t0 = time.perf_counter()
                wav = synthesize(model, synth_text, fixed_latents, seed,
                                 config["model"]["temperature"],
                                 config["model"]["language"],
                                 max_new_tokens=mnt)
                dt = (time.perf_counter() - t0) * 1000
                if phrase:
                    try:
                        wav = leadin.trim_carrier(wav, synth_text, phrase)
                    except leadin.TrimFailed as e:
                        print(f"    WARNING: lead-in trim failed: {e}")
                rendered.append((wav, pause_ms))
                dur = len(wav) / _SR
                print(f"    [{fi}] pause={pause_ms}ms  {dur:.2f}s  {dt:.0f}ms  {frag_text!r}")
            synth_cache[row["id"]][enum_pause_ms] = rendered

    # ── ASSEMBLE 150 and 250 variants ─────────────────────────────────────────
    for enum_pause_ms in (150, 250):
        name = str(enum_pause_ms)
        clips: list[tuple[np.ndarray, int]] = []
        for row in ordered:
            if row["id"] in needs_synth:
                # rendered sub-fragments + chunk pause appended at end
                frags = synth_cache[row["id"]][enum_pause_ms]
                # all but last already have pauses; append chunk pause after last
                for i, (wav, pause_ms) in enumerate(frags):
                    if i == len(frags) - 1:
                        clips.append((wav, row["pause_after_ms"]))
                    else:
                        clips.append((wav, pause_ms))
            else:
                wav_path = chunks_dir / f"{row['id']}.wav"
                wav, _ = sf.read(str(wav_path), dtype="float32")
                clips.append((wav, row["pause_after_ms"]))

        variant_wav = _assemble(clips)
        mp3 = _master_variant(name, variant_wav, config, out_root)
        print(f"\n{name}.mp3 → {mp3}  ({len(variant_wav)/_SR:.1f}s)")

    # ── BOOK-WIDE COUNT ───────────────────────────────────────────────────────
    print("\n=== BOOK-WIDE COUNT ===")
    touched = _book_wide_count()
    print(f"  {touched}/5127 chunks have at least one enum split")

    print("\n=== DONE ===")
    print(f"Output: {out_root}/{{current,150,250}}.mp3")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    run()
