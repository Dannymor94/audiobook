"""stress-clips: extract word clips from rendered sections for stress review.

For each occurrence of risk/failed/watch words found in QC word timestamps,
extracts audio [word_start−0.6 s, word_end+0.6 s], joins clips with 0.4 s of
silence, and writes one mp3 + index.tsv per section.

Usage:
    ./run.sh stress-clips --section S [--words risk|failed|watch]
    (default: failed+watch)

Sources:
    risk    out/stress/risk.tsv   (col 0 = wordform, produced by stress-inventory)
    failed  out/stress/failed.tsv (col 0 = wordform, produced by stress-sheet apply)
    watch   text/stress_watch.yaml homographs list

─── QC word-timestamp contract (pending architect sign-off) ─────────────────
To search all words (not only flagged ones) QC must write a ``word_times``
field to each manifest row during the transcribe phase:

    "word_times": [[word_str, start_s, end_s, prob], ...]   ← every whisper word

Minimal change to qc._measure — add one line to the return dict:

    "word_times": [[w["w"], w["s"], w["e"], w.get("p")] for w in words]

Invariant: tied to current audio via chunk hash — if the chunk is re-rendered
the hash changes, QC re-runs, and word_times is replaced atomically with the
rest of the row. No separate file needed.

Until that change lands, stress_clips falls back to flag_words (watch-list and
low-confidence words). Risk/failed words absent from flag_words will be missed
and the affected chunks appear in the "нет таймкодов" report.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

import numpy as np

from audiobook import paths

_SR = 24000
_PAD_S = 0.6   # silence added before word_start and after word_end
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
    """Return [{id, word, start_s, end_s, prob}] for all matches, deduplicated.

    Prefers word_times (full Whisper timestamps, every word) when present;
    falls back to flag_words (only watch/conf words).  end_s is None when only
    flag_words is available (clip uses center-based fallback in slice_wav).
    Dedup key: (chunk_id, norm_word, start_s rounded to 3 dp).
    """
    hits: list[dict] = []
    seen: set[tuple] = set()
    for r in rows:
        word_times = r.get("word_times")
        if word_times is not None:
            # [[w, s, e, p], ...]  — full whisper output
            source = [(e[0], float(e[1]), float(e[2]), e[3]) for e in word_times]
        else:
            # [[w, s, p, reason], ...]  — flagged words only, no end time
            source = [(e[0], float(e[1]), None, e[2]) for e in (r.get("flag_words") or [])]

        for w, s, e, p in source:
            if _norm(w) not in word_set:
                continue
            key = (r["id"], _norm(w), round(s, 3))
            if key in seen:
                continue
            seen.add(key)
            hits.append({"id": r["id"], "word": w,
                         "start_s": s, "end_s": e, "prob": p})
    return hits


def chunks_without_timestamps(rows: list[dict]) -> list[str]:
    """IDs of rendered chunks with no word timing data (neither word_times nor flag_words)."""
    rendered = {"done", "qc_fail", "manual", "reused"}
    return [r["id"] for r in rows
            if r.get("status") in rendered
            and r.get("word_times") is None
            and "flag_words" not in r]


def _mmss(total_s: float) -> str:
    s = max(0, int(round(total_s)))
    return f"{s // 60}:{s % 60:02d}"


def slice_wav(data: np.ndarray, sr: int, start_s: float,
              end_s: float | None, pad_s: float) -> np.ndarray:
    """Extract data[start_s−pad_s : end_s+pad_s], clamped to file boundaries.

    When end_s is None (flag_words fallback): start_s is treated as the word
    centre and the window is [start_s−pad_s, start_s+pad_s].
    """
    n = len(data)
    a = max(0, int((start_s - pad_s) * sr))
    if end_s is None:
        b = min(n, int((start_s + pad_s) * sr))
    else:
        b = min(n, int((end_s + pad_s) * sr))
    return data[a:b].copy()


def build_clips(hits: list[dict], chunks_dir: Path, sr: int,
                pad_s: float, gap_s: float) -> tuple[np.ndarray, list[dict]]:
    """Concatenate clips; return (audio, records).

    records: [{hit, clip_start_s}] — only for hits that produced a clip.
    Missing wav files are skipped silently.
    Raises SystemExit for chunks at a sample rate other than sr.
    """
    import soundfile as sf
    gap = np.zeros(int(gap_s * sr), dtype=np.float32)
    parts: list[np.ndarray] = []
    records: list[dict] = []
    t = 0.0
    for hit in hits:
        wav_path = chunks_dir / f"{hit['id']}.wav"
        if not wav_path.exists():
            continue
        data, file_sr = sf.read(str(wav_path), dtype="float32")
        if file_sr != sr:
            raise SystemExit(
                f"неподдерживаемая частота {file_sr} Гц в {wav_path.name} "
                f"(ожидалось {sr} Гц)"
            )
        if data.ndim > 1:
            data = data.mean(axis=1)
        clip = slice_wav(data, sr, hit["start_s"], hit.get("end_s"), pad_s)
        if len(clip) == 0:
            continue
        records.append({"hit": hit, "clip_start_s": t})
        parts.append(clip)
        t += len(clip) / sr + gap_s
        parts.append(gap)
    if not parts:
        return np.zeros(0, dtype=np.float32), []
    return np.concatenate(parts[:-1]), records


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
    from audiobook.suspects import (read_index, read_index_identity,
                                    check_identity)
    from audiobook.assemble import preview_name
    import soundfile as sf

    sec_dir = paths.OUT / "sections" / section
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"нет манифеста для секции {section}: {sec_dir}")

    rows = _read_manifest(manifest_path)
    chunks_dir = sec_dir / "chunks"

    # ── report chunks with no timing data at all ─────────────────────────────
    no_ts = chunks_without_timestamps(rows)
    if no_ts:
        print(f"нет таймкодов слов в {len(no_ts)} чанках (word_times и flag_words отсутствуют):")
        for cid in no_ts:
            print(f"  {cid}")

    has_any_ts = any(
        r.get("word_times") is not None or "flag_words" in r for r in rows
    )
    if not has_any_ts:
        raise SystemExit(
            f"{section}: ни один чанк не имеет таймкодов слов — сначала выполните qc"
        )

    word_set = _word_set(words_arg)
    if not word_set:
        raise SystemExit("нет слов для поиска: файлы источников пусты или не существуют")

    # Sort hits by manifest order then by time within chunk
    hits = collect_hits(rows, word_set)
    if not hits:
        print(f"{section}: вхождений слов не найдено в таймкодах")
        return 0

    id_order = {r["id"]: i for i, r in enumerate(rows)}
    hits.sort(key=lambda h: (id_order.get(h["id"], 9999), h["start_s"]))

    # ── section timestamps from assembler index ───────────────────────────────
    stem = preview_name(None)
    idx_path = sec_dir / f"{stem}.index.tsv"
    index: dict[str, tuple[int, int]] = {}
    if idx_path.exists():
        try:
            ident = read_index_identity(idx_path)
            if ident is not None:
                err = check_identity(ident, rows, None)
                if err:
                    print(f"предупреждение: index.tsv устаревший ({err}); "
                          "section_time будет «?»")
                else:
                    index = read_index(idx_path)
            else:
                # old 3-column index — cannot verify identity; skip it
                print("предупреждение: index.tsv без колонки hash16; "
                      "проверка невозможна, section_time будет «?»")
        except Exception as exc:
            print(f"предупреждение: не удалось прочитать index.tsv ({exc}); "
                  "section_time будет «?»")

    head_ms = int((config.get("master") or {}).get("head_ms") or 0)

    # ── build clips ───────────────────────────────────────────────────────────
    audio, records = build_clips(hits, chunks_dir, _SR, _PAD_S, _GAP_S)
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

    # ── index.tsv built from successfully created clips ───────────────────────
    tsv_out = out_dir / f"{section}.index.tsv"
    with open(tsv_out, "w", encoding="utf-8") as f:
        f.write("clip_time\tsection\tchunk\tsection_time\tword\n")
        for rec in records:
            hit = rec["hit"]
            clip_t = rec["clip_start_s"]
            if index and hit["id"] in index:
                start_ms, lead_ms = index[hit["id"]]
                sec_ms = start_ms - lead_ms + hit["start_s"] * 1000 + head_ms
                sec_time = _mmss(sec_ms / 1000)
            else:
                sec_time = "?"
            f.write(f"{_mmss(clip_t)}\t{section}\t{hit['id']}\t"
                    f"{sec_time}\t{hit['word']}\n")

    print(f"{section}: {len(records)} клипов → {mp3_out}  индекс: {tsv_out}")
    return 0
