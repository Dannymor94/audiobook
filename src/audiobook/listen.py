"""Listening plan: the few minutes of the rendered book a human should hear,
instead of all of it.

    ./run.sh listen-plan [--section S ...] [--intro-s 30] [--random 20]

Picks whole chunks from assembled sections (current index only):
  * every chunk with a suspect word (qc flag_words),
  * the chunks covering the first ``intro_s`` seconds of each section,
  * ``random`` more chunks from the whole set (fixed seed → same picks on rerun).
Cuts each one from the FINAL section.mp3 (what the listener will hear) and writes

  out/listen/plan.mp3      all picks back to back, 0.8 s apart
  out/listen/index.tsv     start, section, chunk, tags, text, hash (probe format)
  out/listen/chunks/<hash16>.wav

so `./run.sh review --dir out/listen` builds a marking page and `./run.sh fix plan`
maps the marks back to chunks by hash. Nothing in out/sections is changed.
"""
from __future__ import annotations

import random
import re
import subprocess
from pathlib import Path

import numpy as np

from audiobook import paths

GAP_S = 0.8
MIN_RANDOM_CHARS = 40
SEED = 20261030


def pick(rows: list[dict], index: dict[str, dict], intro_ms: int) -> list[tuple[dict, list[str]]]:
    """[(row, tags)] in reading order: suspects and the section intro."""
    out = []
    for r in rows:
        ix = index.get(str(r["id"]))
        if ix is None:
            continue
        tags = []
        if ix["start_ms"] < intro_ms:
            tags.append("начало")
        words = [f[0] for f in r.get("flag_words") or []]
        if words:
            tags.append("подозр: " + ", ".join(words[:4]))
        if tags:
            out.append((r, tags))
    return out


def add_random(picked: list[tuple[str, dict, list[str]]],
               pool: list[tuple[str, dict]], n: int, seed: int = SEED) -> list[tuple[str, dict, list[str]]]:
    """Add ``n`` random chunks (by hash, not already picked, long enough)."""
    have = {r["hash"] for _s, r, _t in picked}
    cand = [(s, r) for s, r in pool
            if r["hash"] not in have and len(r.get("text", "")) >= MIN_RANDOM_CHARS]
    rng = random.Random(seed)
    extra = rng.sample(cand, min(n, len(cand)))
    return picked + [(s, r, ["выборка"]) for s, r in extra]


def mmss(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def _decode(mp3: Path, sr: int) -> np.ndarray:
    ff = paths.ffmpeg()
    if ff is None:
        raise SystemExit("ffmpeg не найден (bin/ или PATH)")
    p = subprocess.run([str(ff), "-v", "error", "-i", str(mp3), "-f", "f32le", "-ac", "1",
                        "-ar", str(sr), "-"], capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32)


def _section_index(config: dict, section: str) -> tuple[list[dict], dict[str, dict]] | None:
    """(rows, index with mp3 times) or None if the section has no current assembly."""
    from audiobook.suspects import check_identity, read_index_identity
    from audiobook.sync import read_index_full
    from audiobook.synth import _read_manifest
    sec = paths.OUT / "sections" / section
    idx, mp3 = sec / "section.index.tsv", sec / "section.mp3"
    if not (idx.exists() and mp3.exists()):
        return None
    rows = _read_manifest(sec / "manifest.jsonl")
    ident = read_index_identity(idx)
    if ident is None or check_identity(ident, rows, None):
        print(f"  {section}: сборка не от текущего манифеста — пропущено (нужен assemble+master)")
        return None
    head = int((config.get("master") or {}).get("head_ms") or 0)
    index = {cid: {**v, "start_ms": v["start_ms"] + head}
             for cid, v in read_index_full(idx).items()}
    return rows, index


def run(config: dict, sections: list[str] | None = None, intro_s: float = 30,
        n_random: int = 20, tag: str | None = None, notify: bool = False) -> int:
    """``tag`` → out/listen/<tag>/ (one plan per chapter); ``notify`` → send the
    plan mp3 to Telegram (opt-in; no-op without credentials)."""
    import soundfile as sf
    from audiobook.master import encode_args

    secs = sections or sorted(p.parent.name for p in
                              (paths.OUT / "sections").glob("*/section.mp3"))
    picked: list[tuple[str, dict, list[str]]] = []
    pool: list[tuple[str, dict]] = []
    indexes: dict[str, dict[str, dict]] = {}
    for s in secs:
        got = _section_index(config, s)
        if got is None:
            continue
        rows, index = got
        indexes[s] = index
        picked += [(s, r, t) for r, t in pick(rows, index, int(intro_s * 1000))]
        pool += [(s, r) for r in rows if str(r["id"]) in index]
    if not indexes:
        raise SystemExit("нет собранных секций с актуальным index.tsv (assemble+master)")
    picked = add_random(picked, pool, n_random)
    # dedupe by hash (identical repeated text, e.g. "Шаг один.") keeping first
    seen, uniq = set(), []
    for s, r, t in picked:
        if r["hash"] not in seen:
            seen.add(r["hash"])
            uniq.append((s, r, t))
    uniq.sort(key=lambda x: (secs.index(x[0]), x[1].get("n", 0), str(x[1]["id"])))

    sr = int((config.get("master") or {}).get("sample_rate", 44100))
    if tag and not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", tag):
        raise SystemExit(f"listen-plan: недопустимый --tag {tag!r}")
    out = paths.OUT / "listen" / tag if tag else paths.OUT / "listen"
    wav_dir = out / "chunks"
    wav_dir.mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(GAP_S * sr), dtype=np.float32)
    parts, t, lines = [], 0.0, []
    audio_cache: dict[str, np.ndarray] = {}
    for s, r, tags in uniq:
        if s not in audio_cache:
            audio_cache = {s: _decode(paths.OUT / "sections" / s / "section.mp3", sr)}
        a = audio_cache[s]
        ix = indexes[s][str(r["id"])]
        seg = a[int(ix["start_ms"] * sr / 1000): int((ix["start_ms"] + ix["dur_ms"]) * sr / 1000)]
        h16 = r["hash"][:16]
        p = wav_dir / f"{h16}.wav"
        tmp = p.with_name(p.name + ".part")
        sf.write(str(tmp), seg, sr, subtype="FLOAT", format="WAV")
        tmp.replace(p)
        flat = " ".join(str(r.get("text", "")).split())
        lines.append(f"{mmss(t)}\t{s}\t{r['id']}\t{'; '.join(tags)}\t{flat}\t{h16}")
        parts += [seg, gap]
        t += len(seg) / sr + GAP_S

    idx = out / "index.tsv"
    tmp = idx.with_name(idx.name + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("start\tsection\tchunk\ttags\ttext\thash\n" + "\n".join(lines) + "\n")
    tmp.replace(idx)
    raw = out / "plan.wav.part"
    sf.write(str(raw), np.concatenate(parts), sr, subtype="FLOAT", format="WAV")
    mp3 = out / "plan.mp3"
    subprocess.run(encode_args(str(paths.ffmpeg()), raw, mp3.with_name("plan.mp3.part"),
                               "anull", sr), capture_output=True, check=True)
    mp3.with_name("plan.mp3.part").replace(mp3)
    raw.unlink()   # intermediate render of the plan itself; chunk wavs are kept
    kinds = {"начало": 0, "подозр": 0, "выборка": 0}
    for _s, _r, tags in uniq:
        for k in kinds:
            kinds[k] += any(x.startswith(k) for x in tags)
    print(f"план прослушки: {len(uniq)} фрагментов, {mmss(t)} "
          f"(начало глав {kinds['начало']}, подозрения {kinds['подозр']}, выборка {kinds['выборка']})")
    rel = out.relative_to(paths.OUT).as_posix()
    print(f"→ {mp3}\n  оглавление: {idx}\n  разметка: ./run.sh review --dir out/{rel}  "
          "→ ./run.sh fix plan <labels.json>")
    if notify:
        from audiobook import notify as tg
        what = ", ".join(secs) if len(secs) <= 2 else f"{len(secs)} секций"
        caption = (f"Послушать: {what} — {len(uniq)} фрагм., {mmss(t)}\n"
                   f"начало {kinds['начало']} · подозрения {kinds['подозр']} · выборка {kinds['выборка']}\n"
                   f"разметка: ./run.sh review --dir out/{rel}")
        sent, why = tg.deliver_audio(mp3, caption, title=f"план: {what}"[:60])
        print(f"telegram: {'отправлено' if sent else 'не отправлено — ' + why}")
    return 0
