"""A/B a stress respelling by ear: render ONE chunk several times, identical in
everything except how one word is spelled for the model.

    ./run.sh pron-test --section S --word Запить --try ЗапИть Запиить Запи́ть

Each variant is the current pronounce table with ``word`` → that spelling
("-" = no entry, the plain word). The chunk is found by whole-word match
(or given with --chunk). Same seed for every variant, so the spelling is the
only difference. Writes out/pron_test/<section>_<id>_<word>/<n>.wav and all.mp3
(variants in --try order, each in --seeds takes, 1.2 s apart). Leftovers of a previous
run in the same folder (n.wav, meta.tsv, all.mp3, review.html) are moved to
_old_<timestamp>/ before rendering — never deleted, never mixed with the new
takes (a shorter --try list would otherwise leave stale n.wav). Never touches text/pronounce.yaml, the
manifest or the chunk cache — the chosen spelling is then added to
pronounce.yaml by hand (it enters only the affected chunks' hashes).

House rule from 0.6B (single capital stressed vowel) is not assumed to hold for
1.7B; this tool exists to re-confirm it by ear.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import soundfile as sf

from audiobook import paths

PLAIN = "-"


def find_chunk(rows: list[dict], word: str) -> dict | None:
    pat = re.compile(rf"\b{re.escape(word)}\b")
    return next((r for r in rows if pat.search(r["text"])), None)


def variant_tables(table: dict[str, str], word: str,
                   variants: list[str]) -> list[tuple[str, dict[str, str]]]:
    out = []
    for v in variants:
        t = dict(table)
        if v == PLAIN:
            t.pop(word, None)
        else:
            t[word] = v
        out.append((v, t))
    return out


SEED_STEP = 1009  # distinct take per --seeds index, far from retry offsets


def render_variants(engine, row: dict, config: dict,
                    tables: list[tuple[str, dict[str, str]]], seeds: int = 2,
                    retries: int = 3) -> list[tuple[str, int, str, np.ndarray | None]]:
    """[(variant, take, synth_text, wav|None)], variant-major. Take k uses the
    same seed for every variant, so within a take only the spelling differs;
    several takes show whether a stress is the spelling or just seed luck."""
    from audiobook.synth import prepare_synth_text, row_leadin, seed_for_chunk
    sentinel = config["model"].get("sentinel", "")
    base = row.get("seed_override") or seed_for_chunk(row["hash"])
    out = []
    for v, t in tables:
        synth_text, phrase = prepare_synth_text(row["text"], config, t, sentinel,
                                                row_leadin(row), row.get("open_end", False))
        kw = {"leadin": phrase} if phrase else {}
        for k in range(seeds):
            wav = None
            for attempt in range(retries + 1):
                wav = engine.synth(synth_text, base + k * SEED_STEP + attempt, **kw)
                if wav is not None:
                    break
            out.append((v, k + 1, synth_text, wav))
    return out


META_COLUMNS = ["n", "chunk", "variant", "take", "start", "synth_text"]
SAMPLE_RATE = 24000  # synth._SAMPLE_RATE; kept here so the writer needs no model imports
GAP_S = 1.2


def _mmss(t: float) -> str:
    m, sec = divmod(int(t), 60)
    return f"{m}:{sec:02d}"


_LEFTOVER_RE = re.compile(r"\d+\.wav")
LEFTOVER_FILES = ("meta.tsv", "meta.tsv.part", "all.mp3", "all.wav", "review.html")


def previous_run_files(out_dir: Path) -> list[Path]:
    """Files a previous pron-test run left in ``out_dir``."""
    if not out_dir.is_dir():
        return []
    nums = sorted(p for p in out_dir.iterdir() if p.is_file() and _LEFTOVER_RE.fullmatch(p.name))
    return nums + [out_dir / n for n in LEFTOVER_FILES if (out_dir / n).is_file()]


def archive_previous_run(out_dir: Path) -> Path | None:
    from audiobook.review import archive_stale
    return archive_stale(out_dir, previous_run_files(out_dir))


def write_results(out_dir: Path, results: list[tuple[dict, list]]) -> list[np.ndarray]:
    """Write <n>.wav per variant/take plus meta.tsv (n, chunk, variant, take,
    start, synth_text) next to them — the review page reads it for captions.
    ``n`` counts all variants in order, a failed one gets no wav and no meta row.
    Returns the audio parts (wav, gap, wav, gap, ...) for the all.mp3 listen."""
    gap = np.zeros(int(GAP_S * SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []
    t = 0.0
    n = 0
    meta_rows: list[list[str]] = []
    for row, res in results:
        print(f"чанк {row['id']}: {row['text']}")
        for v, take, synth_text, wav in res:
            n += 1
            if wav is None:
                print(f"  {n}. {v!r} дубль {take}: НЕ СИНТЕЗИРОВАЛСЯ (cap/timeout)")
                continue
            sf.write(str(out_dir / f"{n}.wav"), wav, SAMPLE_RATE, subtype="FLOAT")
            parts += [wav, gap]
            start = _mmss(t)
            print(f"  {n}. [{start}] {v!r} дубль {take}  ({len(wav) / SAMPLE_RATE:.1f} с)"
                  f"  → модели: {synth_text}")
            flat = " ".join(synth_text.split())  # one line per row: no tabs/newlines
            meta_rows.append([str(n), str(row["id"]), v, str(take), start, flat])
            t += len(wav) / SAMPLE_RATE + GAP_S
    tmp = out_dir / "meta.tsv.part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(META_COLUMNS) + "\n")
        for r in meta_rows:
            f.write("\t".join(r) + "\n")
    tmp.replace(out_dir / "meta.tsv")
    return parts


def run(config: dict, section: str, word: str, variants: list[str],
        chunk_id: str | None = None, seeds: int = 2, n_chunks: int = 1) -> int:
    from audiobook.master import master_wav
    from audiobook.pronounce import load_table
    from audiobook.synth import _read_manifest, worker_config
    from audiobook.worker import TimeoutSynth

    manifest = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest.exists():
        raise SystemExit(f"нет манифеста {manifest} — сначала chunk --section {section}")
    rows = _read_manifest(manifest)
    pat = re.compile(rf"\b{re.escape(word)}\b")
    if chunk_id:
        picked = [r for r in rows if r["id"] == chunk_id]
        if not picked:
            raise SystemExit(f"чанк не найден: {chunk_id} в {section}")
        if not pat.search(picked[0]["text"]):
            raise SystemExit(f"в чанке {chunk_id} нет слова {word!r} (регистр важен)")
    else:
        picked = [r for r in rows if pat.search(r["text"])][:max(1, n_chunks)]
        if not picked:
            raise SystemExit(f"слово {word!r} не найдено в {section} (регистр важен)")

    tables = variant_tables(load_table(), word, variants)
    tag = picked[0]["id"] if len(picked) == 1 else f"{len(picked)}chunks"
    out_dir = paths.OUT / "pron_test" / f"{section}_{tag}_{word}"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_previous_run(out_dir)
    timeout_s = config.get("render", {}).get("chunk_timeout_s", 600)
    with TimeoutSynth(worker_config(config, 1), timeout_s) as engine:
        results = [(row, render_variants(engine, row, config, tables, seeds))
                   for row in picked]

    parts = write_results(out_dir, results)
    if not parts:
        raise SystemExit("ни один вариант не синтезировался")
    raw = out_dir / "all.wav"
    sf.write(str(raw), np.concatenate(parts), SAMPLE_RATE, subtype="FLOAT")
    master_wav(raw, out_dir / "all.mp3", config)
    raw.unlink()  # intermediate; per-variant wavs are kept
    print(f"прослушка: {out_dir / 'all.mp3'}  (в [м:сс] — начало каждого дубля)")
    return 0
