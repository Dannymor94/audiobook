"""Probe the whole book for stress/reading traps BEFORE rendering it.

Scans every section's chunks (built in memory with the current config — same
text, hash and seed the real render would use; nothing is written to the
manifests or the chunk cache), tags risky chunks, greedily picks a small set
that covers every tag, renders just those, and writes one listening file:

  out/probe/probe.mp3   — the picks back to back, 1 s apart
  out/probe/index.tsv   — start mm:ss, section, chunk id, tags, text

The listener notes "mm:ss — what's wrong"; index.tsv maps it to the chunk and
the word. Fixes go to text/pronounce.yaml (confirmed with pron-test) or, for a
one-off bad take, to redo/accept once that section is rendered.

Tags:
  homograph:<w>   word from text/stress_watch.yaml (whole word, any case)
  one_word_run    ≥2 consecutive one-word sentences ("Заесть. Запить. Заснуть.")
  abbrev:<W>      all-caps Cyrillic of 2-5 letters (ПТСР) — may be spelled or read
  caps_word       all-caps word of 6+ letters (shouted emphasis in the text)
  latin:<w>       Latin-script token (URLs, PDF, Roman numerals)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from audiobook import paths

WATCH_PATH = paths.TEXT / "stress_watch.yaml"
GAP_S = 1.0
# How many chunks may represent each tag kind (homograph/abbrev/latin are per
# distinct word; these two are global).
CAP = {"one_word_run": 8, "caps_word": 6}

_WORD = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
_ONE_WORD_SENT = re.compile(r"[«(]?[А-Яа-яЁё\-]+[.!?…»)]+")
_LATIN = re.compile(r"[A-Za-z][A-Za-z.\-]*[A-Za-z]|[A-Za-z]")


def load_watch(path: Path = WATCH_PATH) -> set[str]:
    if not path.exists():
        return set()
    import yaml
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(w).lower() for w in data.get("homographs") or []}


def tags_for(text: str, watch: set[str], vocab: set[str] | None = None) -> set[str]:
    """``vocab``: lowercase words the book also uses in normal case. An all-caps
    word found there is emphasis (ТЕЛО), not an abbreviation (ПТСР)."""
    tags: set[str] = set()
    for w in _WORD.findall(text):
        lw = w.lower()
        if lw in watch:
            tags.add(f"homograph:{lw}")
        if w.isupper() and len(w) >= 2:
            known = vocab is not None and lw in vocab
            tags.add("caps_word" if known or len(w) > 5 else f"abbrev:{w}")
    run = 0
    for s in re.split(r"(?<=[.!?…])\s+", text):
        if _ONE_WORD_SENT.fullmatch(s.strip()):
            run += 1
            if run >= 2:
                tags.add("one_word_run")
        else:
            run = 0
    for t in _LATIN.findall(text):
        tags.add(f"latin:{t}")
    return tags


def _kind(tag: str) -> str:
    return tag.split(":", 1)[0] if tag in CAP or ":" not in tag else tag


def select(cands: list[tuple[dict, set[str]]], max_chunks: int) -> list[tuple[dict, set[str]]]:
    """Greedy cover: repeatedly take the chunk adding the most still-needed tags
    (shorter chunk wins ties — less listening). A per-word tag is needed once;
    a CAP kind is needed up to CAP[kind] times."""
    need: dict[str, int] = {}
    for _row, tags in cands:
        for t in tags:
            k = _kind(t)
            need[k] = CAP.get(k, 1)
    chosen: list[tuple[dict, set[str]]] = []
    pool = list(cands)
    while pool and len(chosen) < max_chunks:
        def gain(item):
            return sum(1 for k in {_kind(t) for t in item[1]} if need.get(k, 0) > 0)
        best = max(pool, key=lambda it: (gain(it), -len(it[0]["text"])))
        if gain(best) == 0:
            break
        pool.remove(best)
        chosen.append(best)
        for k in {_kind(t) for t in best[1]}:
            if need.get(k, 0) > 0:
                need[k] -= 1
    return chosen


def mmss(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def book_vocab() -> set[str]:
    """Lowercased words that occur in the book NOT written all-caps."""
    vocab: set[str] = set()
    for f in paths.TEXT.glob("*.norm.txt"):
        for w in _WORD.findall(f.read_text(encoding="utf-8")):
            if not w.isupper():
                vocab.add(w.lower())
    return vocab


def scan(config: dict, watch: set[str]) -> list[tuple[dict, set[str]]]:
    """[(row + 'section', tags)] for every tagged chunk of the book."""
    from audiobook.chunker import build_manifest, load_units
    vocab = book_vocab()
    out = []
    for jf in sorted((paths.TEXT / "blocks").glob("*.blocks.json")):
        d = json.loads(jf.read_text(encoding="utf-8"))
        nn, slug = d["nn"], d["slug"]
        normf = paths.TEXT / f"{nn}_{slug}.norm.txt"
        if not normf.exists() or normf.stat().st_size < 50:
            continue
        for row in build_manifest(load_units(nn, slug), config):
            tags = tags_for(row["text"], watch, vocab)
            if tags:
                out.append((dict(row, section=f"{nn}_{slug}"), tags))
    return out


def run(config: dict, max_chunks: int = 60, dry_run: bool = False) -> int:
    import soundfile as sf
    from audiobook.pronounce import load_table
    from audiobook.synth import _SAMPLE_RATE, _synth_one_chunk, worker_config

    watch = load_watch()
    cands = scan(config, watch)
    chosen = select(cands, max_chunks)
    all_tags = {t for _r, ts in cands for t in ts}
    covered = {t for _r, ts in chosen for t in ts}
    chars = sum(len(r["text"]) for r, _t in chosen)
    print(f"чанков с ловушками: {len(cands)}, меток: {len(all_tags)}; "
          f"выбрано {len(chosen)} чанков, покрыто меток {len(covered)}, "
          f"~{chars / 13 / 60:.1f} мин звука")
    out_dir = paths.OUT / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    if dry_run:
        for r, ts in chosen:
            print(f"  {r['section'][:24]:24} {r['id']}  {', '.join(sorted(ts))}")
        return 0

    from audiobook.master import master_wav
    from audiobook.worker import TimeoutSynth
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    retries = config.get("render", {}).get("timeout_retries", 2)
    timeout_s = config.get("render", {}).get("chunk_timeout_s", 600)
    wav_dir = out_dir / "chunks"
    wav_dir.mkdir(exist_ok=True)
    with TimeoutSynth(worker_config(config, 1), timeout_s) as engine:
        for r, _ts in chosen:
            p = wav_dir / f"{r['hash'][:16]}.wav"  # by hash: config change → re-render
            if p.exists():
                continue  # resumable
            wav, _seed = _synth_one_chunk(r, config, table, sentinel, engine, retries)
            if wav is None:
                print(f"  НЕ СИНТЕЗИРОВАЛСЯ: {r['section']} {r['id']}")
                continue
            tmp = p.with_name(p.name + ".part")
            sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
            tmp.replace(p)

    gap = np.zeros(int(GAP_S * _SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []
    t = 0.0
    with open(out_dir / "index.tsv", "w", encoding="utf-8") as f:
        f.write("start\tsection\tchunk\ttags\ttext\n")
        for r, ts in chosen:
            p = wav_dir / f"{r['hash'][:16]}.wav"
            if not p.exists():
                continue
            wav, _sr = sf.read(str(p), dtype="float32")
            f.write(f"{mmss(t)}\t{r['section']}\t{r['id']}\t{', '.join(sorted(ts))}\t{r['text']}\n")
            parts += [wav, gap]
            t += len(wav) / _SAMPLE_RATE + GAP_S
    raw = out_dir / "probe.wav"
    sf.write(str(raw), np.concatenate(parts), _SAMPLE_RATE, subtype="PCM_16")
    master_wav(raw, out_dir / "probe.mp3", config)
    raw.unlink()  # intermediate; chunk wavs kept for resume
    print(f"прослушка: {out_dir / 'probe.mp3'} ({mmss(t)})  оглавление: {out_dir / 'index.tsv'}")
    return 0
