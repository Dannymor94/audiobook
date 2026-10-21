"""A/B a stress respelling by ear: render ONE chunk several times, identical in
everything except how one word is spelled for the model.

    ./run.sh pron-test --section S --word Запить --try ЗапИть Запиить Запи́ть

Each variant is the current pronounce table with ``word`` → that spelling
("-" = no entry, the plain word). The chunk is found by whole-word match
(or given with --chunk). Same seed for every variant, so the spelling is the
only difference. Writes out/pron_test/<section>_<id>_<word>/<n>.wav and all.mp3
(variants in --try order, each in --seeds takes, 1.2 s apart). Never touches text/pronounce.yaml, the
manifest or the chunk cache — the chosen spelling is then added to
pronounce.yaml by hand (it enters only the affected chunks' hashes).

House rule from 0.6B (single capital stressed vowel) is not assumed to hold for
1.7B; this tool exists to re-confirm it by ear.
"""
from __future__ import annotations

import re

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
    from audiobook.synth import prepare_synth_text, seed_for_chunk
    sentinel = config["model"].get("sentinel", "")
    base = row.get("seed_override") or seed_for_chunk(row["hash"])
    out = []
    for v, t in tables:
        synth_text, phrase = prepare_synth_text(row["text"], config, t, sentinel)
        kw = {"leadin": phrase} if phrase else {}
        for k in range(seeds):
            wav = None
            for attempt in range(retries + 1):
                wav = engine.synth(synth_text, base + k * SEED_STEP + attempt, **kw)
                if wav is not None:
                    break
            out.append((v, k + 1, synth_text, wav))
    return out


def run(config: dict, section: str, word: str, variants: list[str],
        chunk_id: str | None = None, seeds: int = 2) -> int:
    from audiobook.master import master_wav
    from audiobook.pronounce import load_table
    from audiobook.synth import _SAMPLE_RATE, _read_manifest, worker_config
    from audiobook.worker import TimeoutSynth

    manifest = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest.exists():
        raise SystemExit(f"нет манифеста {manifest} — сначала chunk --section {section}")
    rows = _read_manifest(manifest)
    row = (next((r for r in rows if r["id"] == chunk_id), None) if chunk_id
           else find_chunk(rows, word))
    if row is None:
        raise SystemExit(f"чанк не найден: {chunk_id or word!r} в {section}")
    if not re.search(rf"\b{re.escape(word)}\b", row["text"]):
        raise SystemExit(f"в чанке {row['id']} нет слова {word!r} (регистр важен)")

    tables = variant_tables(load_table(), word, variants)
    out_dir = paths.OUT / "pron_test" / f"{section}_{row['id']}_{word}"
    out_dir.mkdir(parents=True, exist_ok=True)
    timeout_s = config.get("render", {}).get("chunk_timeout_s", 600)
    with TimeoutSynth(worker_config(config, 1), timeout_s) as engine:
        results = render_variants(engine, row, config, tables, seeds)

    gap = np.zeros(int(1.2 * _SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []
    print(f"чанк {row['id']}: {row['text']}")
    for n, (v, take, synth_text, wav) in enumerate(results, start=1):
        if wav is None:
            print(f"  {n}. {v!r} дубль {take}: НЕ СИНТЕЗИРОВАЛСЯ (cap/timeout)")
            continue
        sf.write(str(out_dir / f"{n}.wav"), wav, _SAMPLE_RATE, subtype="PCM_16")
        parts += [wav, gap]
        print(f"  {n}. {v!r} дубль {take}  ({len(wav) / _SAMPLE_RATE:.1f} с)  "
              f"→ модели: {synth_text}")
    if not parts:
        raise SystemExit("ни один вариант не синтезировался")
    raw = out_dir / "all.wav"
    sf.write(str(raw), np.concatenate(parts), _SAMPLE_RATE, subtype="PCM_16")
    master_wav(raw, out_dir / "all.mp3", config)
    raw.unlink()  # intermediate; per-variant wavs are kept
    print(f"прослушка: {out_dir / 'all.mp3'}")
    return 0
