"""stress-clips: extract word clips from rendered sections for stress review.

For each occurrence of risk/failed/watch words found in QC word_times,
extracts audio [word_start−0.6 s, word_end+0.6 s], joins clips with 0.4 s of
silence, and writes one mp3 + index.tsv per section.

Usage:
    ./run.sh stress-clips --section S [--words risk|failed|watch]
    (default: failed+watch)

Sources:
    risk    out/stress/risk.tsv   (col 0 = wordform, produced by stress-inventory)
    failed  out/stress/failed.tsv (col 0 = wordform, produced by stress-sheet apply)
    watch   text/stress_watch.yaml homographs list

─── QC word_times contract ───────────────────────────────────────────────────
qc._measure stores every whisper word in the manifest row:

    "word_times": [[word_str, start_s, end_s, prob], ...]

This field is populated by run() (normal QC) and run_words_only() (re-
transcribe without re-synth, safe on done/manual chunks). It is atomically
replaced whenever the chunk is re-transcribed, so it always reflects the
current audio. No fallback to flag_words: flag_words is a filtered subset
(watch+conf), not a source of complete timestamps.
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
    """Return [{id, word, start_s, end_s, prob}] from word_times, deduplicated.

    Only uses word_times (complete whisper output); never falls back to
    flag_words. Rows without word_times are silently skipped here — the caller
    uses chunks_without_timestamps() to report them separately.
    Dedup key: (chunk_id, norm_word, start_s rounded to 3 dp).
    """
    hits: list[dict] = []
    seen: set[tuple] = set()
    for r in rows:
        word_times = r.get("word_times")
        if word_times is None:
            continue
        for entry in word_times:
            w, s, e, p = entry[0], float(entry[1]), float(entry[2]), entry[3]
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
    """IDs of rendered chunks with no word_times field."""
    rendered = {"done", "qc_fail", "manual", "reused"}
    return [r["id"] for r in rows
            if r.get("status") in rendered
            and r.get("word_times") is None]


def _mmss(total_s: float) -> str:
    s = max(0, int(round(total_s)))
    return f"{s // 60}:{s % 60:02d}"


def slice_wav(data: np.ndarray, sr: int, start_s: float,
              end_s: float | None, pad_s: float) -> np.ndarray:
    """Extract data[start_s−pad_s : end_s+pad_s], clamped to file boundaries.

    When end_s is None: start_s is treated as the word centre and the window
    is [start_s−pad_s, start_s+pad_s] (legacy fallback, not used in production).
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

    # ── verify word_times coverage ────────────────────────────────────────────
    no_ts = chunks_without_timestamps(rows)
    if no_ts:
        print(f"нет word_times в {len(no_ts)} чанках (нужен повторный QC):")
        for cid in no_ts:
            print(f"  {cid}")

    has_any_wt = any(r.get("word_times") is not None for r in rows)
    if not has_any_wt:
        raise SystemExit(
            f"{section}: word_times отсутствуют — выполните: "
            f"./run.sh qc-words --section {section}"
        )

    if no_ts:
        raise SystemExit(
            f"{section}: {len(no_ts)} чанков без word_times — результат будет неполным. "
            f"Запустите: ./run.sh qc-words --section {section}"
        )

    word_set = _word_set(words_arg)
    if not word_set:
        raise SystemExit("нет слов для поиска: файлы источников пусты или не существуют")

    hits = collect_hits(rows, word_set)
    if not hits:
        print(f"{section}: вхождений слов не найдено в word_times")
        return 0

    # Sort by manifest order then by time within chunk
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
