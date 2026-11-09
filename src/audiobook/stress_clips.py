"""stress-clips: extract word clips from rendered sections for stress review.

Looks up risk/failed/watch words in the per-chunk flag_words stored by QC
(whisper word timestamps), slices ±0.6 s around each hit, joins clips with
0.4 s of silence, and writes one mp3 + index.tsv per section.

Usage:
    ./run.sh stress-clips --section S [--words risk|failed|watch]
    (default: failed+watch)

Sources:
    risk    out/stress/risk.tsv   (col 0 = wordform, produced by stress-inventory)
    failed  out/stress/failed.tsv (col 0 = wordform, produced by stress-sheet apply)
    watch   text/stress_watch.yaml homographs list

flag_words layout in manifest rows:
    [[word_str, start_s, prob_or_None, reason_str], ...]
Only words flagged by QC are stored here. Watch-list words are always present
when whisper hears them; risk/failed words appear if whisper also flagged them
(low confidence or they happen to be in the watch list).
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np

from audiobook import paths

_SR = 24000
_PAD_S = 0.6   # half-window around word
_GAP_S = 0.4   # silence between clips

_STRESS_TABLE = {c: None for c in (0x0300, 0x0301, 0x0340, 0x0341)}
_NON_WORD = re.compile(r"[^\w]", re.UNICODE)


def _norm(w: str) -> str:
    t = unicodedata.normalize("NFC", w)
    t = t.translate(_STRESS_TABLE).replace("+", "")
    t = t.replace("ё", "е").replace("Ё", "Е")
    return _NON_WORD.sub("", t).lower()


def load_tsv_words(path: Path) -> set[str]:
    """Read col-0 wordforms from a tsv, return normalised set."""
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            out.add(_norm(line.split("\t")[0]))
    return out


def load_watch_words() -> set[str]:
    p = paths.TEXT / "stress_watch.yaml"
    if not p.exists():
        return set()
    import yaml
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {_norm(str(w)) for w in data.get("homographs") or []}


def _word_set(words_arg: list[str]) -> set[str]:
    out: set[str] = set()
    if "risk" in words_arg:
        out |= load_tsv_words(paths.OUT / "stress" / "risk.tsv")
    if "failed" in words_arg:
        out |= load_tsv_words(paths.OUT / "stress" / "failed.tsv")
    if "watch" in words_arg:
        out |= load_watch_words()
    return out


def collect_hits(rows: list[dict], word_set: set[str]) -> list[dict]:
    """Return [{id, start_s, word, prob}] for all flag_words matching word_set."""
    hits = []
    for r in rows:
        for entry in r.get("flag_words") or []:
            w, s, p = entry[0], entry[1], entry[2]
            if _norm(w) in word_set:
                hits.append({"id": r["id"], "start_s": float(s),
                             "word": w, "prob": p})
    return hits


def _mmss(total_s: float) -> str:
    s = max(0, int(round(total_s)))
    return f"{s // 60}:{s % 60:02d}"


def slice_wav(data: np.ndarray, sr: int, center_s: float,
              pad_s: float) -> np.ndarray:
    """Extract data[center±pad_s], zero-padded at boundaries."""
    n = len(data)
    start = max(0, int((center_s - pad_s) * sr))
    end = min(n, int((center_s + pad_s) * sr))
    return data[start:end].copy()


def build_clips(hits: list[dict], chunks_dir: Path, sr: int,
                pad_s: float, gap_s: float) -> tuple[np.ndarray, list[float]]:
    """Concatenate clips; return (audio, list_of_clip_start_times_s)."""
    import soundfile as sf
    gap = np.zeros(int(gap_s * sr), dtype=np.float32)
    parts: list[np.ndarray] = []
    starts: list[float] = []
    t = 0.0
    for hit in hits:
        wav_path = chunks_dir / f"{hit['id']}.wav"
        if not wav_path.exists():
            continue
        data, file_sr = sf.read(str(wav_path), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        clip = slice_wav(data, file_sr, hit["start_s"], pad_s)
        if len(clip) == 0:
            continue
        starts.append(t)
        parts.append(clip)
        t += len(clip) / file_sr + gap_s
        parts.append(gap)
    if not parts:
        return np.zeros(0, dtype=np.float32), []
    # drop trailing gap
    return np.concatenate(parts[:-1] if parts else parts), starts


def _encode_mp3(wav_path: Path, out_path: Path) -> None:
    ff = paths.ffmpeg()
    if not ff:
        raise SystemExit("ffmpeg не найден (bin/ или PATH)")
    tmp = out_path.with_suffix(".part.mp3")
    subprocess.run(
        [str(ff), "-hide_banner", "-y", "-i", str(wav_path),
         "-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", str(tmp)],
        check=True, capture_output=True,
    )
    tmp.replace(out_path)


def run(config: dict, section: str | None, words_arg: list[str]) -> int:
    if not section:
        raise SystemExit("stress-clips: --section обязателен")

    from audiobook.synth import _read_manifest
    from audiobook.suspects import read_index, read_index_identity, check_identity, manifest_identity
    from audiobook.assemble import preview_name
    import soundfile as sf

    sec_dir = paths.OUT / "sections" / section
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"нет манифеста для секции {section}: {sec_dir}")

    stem = preview_name(None)
    idx_path = sec_dir / f"{stem}.index.tsv"
    has_index = idx_path.exists()

    rows = _read_manifest(manifest_path)
    chunks_dir = sec_dir / "chunks"

    word_set = _word_set(words_arg)
    if not word_set:
        raise SystemExit("нет слов для поиска: файлы источников пусты или не существуют")

    hits = collect_hits(rows, word_set)
    if not hits:
        print(f"{section}: вхождений не найдено в flag_words")
        return 0

    # Warn about chunks without flag_words
    no_flags = [r["id"] for r in rows
                if r.get("status") in ("done", "qc_fail", "manual", "reused")
                and "flag_words" not in r]
    if no_flags:
        print(f"нет таймкодов слов в {len(no_flags)} чанках: "
              + ", ".join(str(i) for i in no_flags[:10])
              + (" …" if len(no_flags) > 10 else ""))

    # section timestamps (optional — only when index exists)
    index: dict[str, tuple[int, int]] = {}
    if has_index:
        try:
            ident = read_index_identity(idx_path)
            if ident is not None:
                err = check_identity(ident, rows, None)
            else:
                # ponytail: skip mtime check if no identity columns; times may be stale
                err = None
            if not err:
                index = read_index(idx_path)
        except Exception:
            pass  # section times become "?" in index.tsv

    head_ms = int((config.get("master") or {}).get("head_ms") or 0)

    # Sort hits by chunk order (preserve manifest order within chunk)
    id_order = {r["id"]: i for i, r in enumerate(rows)}
    hits.sort(key=lambda h: (id_order.get(h["id"], 9999), h["start_s"]))

    audio, clip_starts = build_clips(hits, chunks_dir, _SR, _PAD_S, _GAP_S)
    if audio.size == 0:
        print(f"{section}: wav-файлы чанков не найдены — рендер выполнен?")
        return 0

    out_dir = paths.OUT / "stress" / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_tmp = out_dir / f"{section}.wav"
    sf.write(str(wav_tmp), audio, _SR, subtype="PCM_16")
    mp3_out = out_dir / f"{section}.mp3"
    _encode_mp3(wav_tmp, mp3_out)
    wav_tmp.unlink()

    # index.tsv
    tsv_out = out_dir / f"{section}.index.tsv"
    with open(tsv_out, "w", encoding="utf-8") as f:
        f.write("clip_time\tsection\tchunk\tsection_time\tword\n")
        for hit, clip_t in zip(hits, clip_starts):
            if index and hit["id"] in index:
                start_ms, lead_ms = index[hit["id"]]
                sec_ms = start_ms - lead_ms + hit["start_s"] * 1000 + head_ms
                sec_time = _mmss(sec_ms / 1000)
            else:
                sec_time = "?"
            f.write(f"{_mmss(clip_t)}\t{section}\t{hit['id']}\t{sec_time}\t{hit['word']}\n")

    print(f"{section}: {len(hits)} клипов → {mp3_out}  индекс: {tsv_out}")
    return 0
