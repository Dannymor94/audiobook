"""Golden set: a fixed list of hard chunks, rendered under a tag and compared
between tags, so every settings change (reference, pauses, temperature, int8)
is checked by ear on the same material with one command.

  text/golden_set.yaml   [{section, match, why}] — ``match`` is a substring of the
                         chunk text (chunk ids change on re-chunking, text does not)
  golden init            build the list: one chunk per probe tag + fixed entries
  golden render --tag T  out/golden/T/<hash16>.wav (resume), index.tsv, golden.mp3,
                         settings.json (snapshot of the settings that shape the sound)
  golden compare A B     out/golden/compare_A_B/NN_A.wav, NN_B.wav, compare.mp3, index.tsv

Chunks are built in memory with the current config (like probe): nothing is
written to the manifests or the chunk cache. Only chosen chunks are synthesised.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np

from audiobook import paths
from audiobook.master import master_wav
from audiobook.probe import mmss

GAP_S = 1.0            # between items in golden.mp3
COMPARE_A_B_S = 0.6    # pause between A and B of one item
COMPARE_ITEM_S = 1.5   # pause between items in compare.mp3
_SAMPLE_RATE = 24000   # = synth._SAMPLE_RATE (kept local: no heavy import for init/compare)
_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_MATCH_LEN = 48        # chars of chunk text used as the match for probe picks

# Fixed entries: the hard places of chapter 13 found by ear.
_FIXED_SECTION = "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu"
FIXED = [
    {"section": _FIXED_SECTION, "match": "Глава тринадцатая.", "why": "заголовок главы"},
    {"section": _FIXED_SECTION, "match": "Я тебя чувствую", "why": "короткая цитата-вставка"},
    {"section": _FIXED_SECTION, "match": "Заесть", "why": "ряд однословных предложений"},
    {"section": _FIXED_SECTION, "match": "Шаг первый.", "why": "метка шага"},
    {"section": _FIXED_SECTION, "match": "Дыши", "why": "короткая императивная фраза"},
]


def golden_path() -> Path:
    return paths.TEXT / "golden_set.yaml"


def golden_dir() -> Path:
    return paths.OUT / "golden"


# ── the list ────────────────────────────────────────────────────────────────

def _match_for(text: str) -> str:
    """Leading slice of the chunk text, cut at a word boundary."""
    t = text.strip()
    if len(t) <= _MATCH_LEN:
        return t
    cut = t[:_MATCH_LEN]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > _MATCH_LEN // 2 else cut).strip()


def build_entries(config: dict, max_chunks: int = 40) -> list[dict]:
    """Fixed entries first, then one probe pick per tag (greedy cover)."""
    from audiobook import probe
    watch = probe.load_watch(paths.TEXT / "stress_watch.yaml")
    cands = probe.scan(config, watch)
    chosen = probe.select(cands, max_chunks)
    entries = [dict(e) for e in FIXED]
    for row, tags in chosen:
        if any(e["section"] == row["section"] and e["match"] in row["text"] for e in FIXED):
            continue  # already covered by a fixed entry
        entries.append({"section": row["section"], "match": _match_for(row["text"]),
                        "why": ", ".join(sorted(tags))})
    return entries


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_entries(entries: list[dict], path: Path | None = None) -> None:
    import yaml
    body = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=1000)
    header = ("# Golden set: {section, match, why}. match — подстрока текста чанка.\n"
              "# Создаётся командой `golden init`; править руками можно.\n")
    _write_atomic(path or golden_path(), header + body)


def load_entries(path: Path | None = None) -> list[dict]:
    import yaml
    p = path or golden_path()
    if not p.exists():
        raise SystemExit(f"нет {p}: сначала `golden init`")
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    out = []
    for e in data:
        if not isinstance(e, dict) or not e.get("section") or not e.get("match"):
            raise SystemExit(f"golden_set.yaml: запись без section/match: {e!r}")
        out.append({"section": str(e["section"]), "match": str(e["match"]),
                    "why": str(e.get("why", ""))})
    return out


def run_init(config: dict, force: bool = False, max_chunks: int = 40) -> int:
    path = golden_path()
    if path.exists() and not force:
        print(f"{path} уже есть; не перезаписываю (--force чтобы пересоздать)")
        return 1
    entries = build_entries(config, max_chunks)
    save_entries(entries, path)
    print(f"golden_set: {len(entries)} записей ({len(FIXED)} фиксированных) → {path}")
    return 0


# ── resolving entries to chunks ─────────────────────────────────────────────

def resolve(entries: list[dict], config: dict) -> list[tuple[dict, dict]]:
    """[(entry, chunk row + 'section')] — first chunk containing ``match``,
    built in memory with the current config. Unresolvable entries are skipped
    with a warning."""
    from audiobook.chunker import build_manifest, load_units
    manifests: dict[str, list[dict] | None] = {}
    out = []
    for e in entries:
        sec = e["section"]
        if sec not in manifests:
            nn, _, slug = sec.partition("_")
            try:
                manifests[sec] = build_manifest(load_units(nn, slug), config)
            except (FileNotFoundError, KeyError, ValueError):
                manifests[sec] = None
        rows = manifests[sec]
        if rows is None:
            print(f"  ПРОПУСК: нет секции {sec} ({e['match']!r})")
            continue
        row = next((r for r in rows if e["match"] in r["text"]), None)
        if row is None:
            print(f"  ПРОПУСК: в {sec} нет чанка с {e['match']!r}")
            continue
        out.append((e, dict(row, section=sec)))
    return out


# ── render ──────────────────────────────────────────────────────────────────

def check_tag(tag: str) -> str:
    if not _TAG_RE.fullmatch(tag or ""):
        raise SystemExit(f"недопустимое имя --tag: {tag!r} (латиница, цифры, . _ -)")
    return tag


def settings_snapshot(config: dict) -> dict:
    """Settings that shape the sound (model incl. variant/quantize, reference,
    temperature, chunking, text_prep, pauses, lead-in)."""
    model = dict(config.get("model") or {})
    snap = {
        "model": model,
        "reference": dict(config.get("reference") or {}),
        "temperature": model.get("temperature"),
        "chunking": dict(config.get("chunking") or {}),
        "text_prep": dict(config.get("text_prep") or {}),
        "pauses_ms": dict(config.get("pauses_ms") or {}),
        "leadin": dict((config.get("render") or {}).get("leadin") or {}),
    }
    return json.loads(json.dumps(snap, default=str))


def render_items(resolved: list[tuple[dict, dict]], config: dict, out_dir: Path,
                 engine, table: dict | None = None) -> list[dict]:
    """Synthesise the missing chunks into ``out_dir/<hash16>.wav`` (float WAV,
    atomic, resume by existence) with the injected ``engine``; write index.tsv,
    settings.json and golden.mp3. Returns the items that have audio:
    [{n, section, chunk, hash16, why, match, text, start, wav}]."""
    import soundfile as sf
    from audiobook.pronounce import load_table
    from audiobook.synth import _synth_one_chunk

    table = load_table() if table is None else table
    sentinel = config["model"].get("sentinel", "")
    retries = config.get("render", {}).get("timeout_retries", 2)
    out_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    for e, row in resolved:
        h16 = row["hash"][:16]
        p = out_dir / f"{h16}.wav"
        if not p.exists():
            wav, _seed = _synth_one_chunk(row, config, table, sentinel, engine, retries)
            if wav is None:
                print(f"  НЕ СИНТЕЗИРОВАЛСЯ: {row['section']} {row['id']}")
                continue  # stays uncached → rendered on the next run
            tmp = p.with_name(p.name + ".part")
            sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="FLOAT", format="WAV")
            tmp.replace(p)
        items.append({"n": len(items) + 1, "section": row["section"], "chunk": row["id"],
                      "hash16": h16, "why": e["why"], "match": e["match"],
                      "text": row["text"], "wav": p})

    gap = np.zeros(int(GAP_S * _SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []
    t = 0.0
    lines = ["n\tsection\tchunk\thash16\twhy\tstart\ttext\n"]
    for it in items:
        wav, _sr = sf.read(str(it["wav"]), dtype="float32")
        it["start"] = mmss(t)
        lines.append("\t".join([str(it["n"]), it["section"], it["chunk"], it["hash16"],
                                it["why"], it["start"], it["text"]]) + "\n")
        parts += [wav, gap]
        t += len(wav) / _SAMPLE_RATE + GAP_S
    _write_atomic(out_dir / "index.tsv", "".join(lines))

    snap = settings_snapshot(config)
    snap["entries"] = [{k: it[k] for k in ("n", "section", "match", "why", "hash16")}
                       for it in items]
    _write_atomic(out_dir / "settings.json",
                  json.dumps(snap, ensure_ascii=False, indent=2) + "\n")

    if parts:
        raw = out_dir / "golden.wav"
        sf.write(str(raw), np.concatenate(parts), _SAMPLE_RATE, subtype="PCM_16")
        try:
            master_wav(raw, out_dir / "golden.mp3", config)
        finally:
            raw.unlink(missing_ok=True)  # intermediate; chunk wavs kept for resume
    return items


def run_render(config: dict, tag: str, workers: int = 1, engine=None) -> int:
    check_tag(tag)
    entries = load_entries()
    resolved = resolve(entries, config)
    out_dir = golden_dir() / tag
    todo = sum(1 for _e, r in resolved if not (out_dir / f"{r['hash'][:16]}.wav").exists())
    print(f"golden {tag}: записей {len(entries)}, найдено чанков {len(resolved)}, "
          f"к синтезу {todo}")
    if engine is None:
        if todo:
            from audiobook.synth import worker_config
            from audiobook.worker import TimeoutSynth
            timeout_s = config.get("render", {}).get("chunk_timeout_s", 600)
            with TimeoutSynth(worker_config(config, workers), timeout_s) as eng:
                items = render_items(resolved, config, out_dir, eng)
        else:
            items = render_items(resolved, config, out_dir, None)
    else:
        items = render_items(resolved, config, out_dir, engine)
    print(f"прослушка: {out_dir / 'golden.mp3'}  оглавление: {out_dir / 'index.tsv'}  "
          f"({len(items)} из {len(resolved)})")
    return 0 if len(items) == len(resolved) else 1


# ── compare ─────────────────────────────────────────────────────────────────

def _load_tag(tag: str) -> list[dict]:
    d = golden_dir() / check_tag(tag)
    sj = d / "settings.json"
    if not sj.exists():
        raise SystemExit(f"нет {sj}: сначала `golden render --tag {tag}`")
    return json.loads(sj.read_text(encoding="utf-8")).get("entries", [])


def run_compare(config: dict, a: str, b: str) -> int:
    import soundfile as sf
    ea, eb = _load_tag(a), _load_tag(b)
    by_b = {(e["section"], e["match"]): e for e in eb}
    out_dir = golden_dir() / f"compare_{a}_{b}"
    out_dir.mkdir(parents=True, exist_ok=True)

    parts: list[np.ndarray] = []
    lines = ["n\tsection\twhy\tstart\twav_a\twav_b\n"]
    t = 0.0
    n = 0
    for e in ea:
        key = (e["section"], e["match"])
        pa = golden_dir() / a / f"{e['hash16']}.wav"
        if key not in by_b:
            print(f"  ПРОПУСК: нет в {b}: {e['section']} {e['match']!r}")
            continue
        pb = golden_dir() / b / f"{by_b[key]['hash16']}.wav"
        missing = [x for x, p in ((a, pa), (b, pb)) if not p.exists()]
        if missing:
            print(f"  ПРОПУСК: нет wav в {', '.join(missing)}: {e['section']} {e['match']!r}")
            continue
        n += 1
        na, nb = out_dir / f"{n:02d}_{a}.wav", out_dir / f"{n:02d}_{b}.wav"
        shutil.copyfile(pa, na)
        shutil.copyfile(pb, nb)
        wa, _ = sf.read(str(pa), dtype="float32")
        wb, _ = sf.read(str(pb), dtype="float32")
        lines.append(f"{n}\t{e['section']}\t{e['why']}\t{mmss(t)}\t{na.name}\t{nb.name}\n")
        parts += [wa, np.zeros(int(COMPARE_A_B_S * _SAMPLE_RATE), dtype=np.float32),
                  wb, np.zeros(int(COMPARE_ITEM_S * _SAMPLE_RATE), dtype=np.float32)]
        t += (len(wa) + len(wb)) / _SAMPLE_RATE + COMPARE_A_B_S + COMPARE_ITEM_S
    _write_atomic(out_dir / "index.tsv", "".join(lines))
    if not parts:
        print("общих записей с аудио нет")
        return 1
    raw = out_dir / "compare.wav"
    sf.write(str(raw), np.concatenate(parts), _SAMPLE_RATE, subtype="PCM_16")
    try:
        master_wav(raw, out_dir / "compare.mp3", config)
    finally:
        raw.unlink(missing_ok=True)
    print(f"сравнение {a} / {b}: {n} пар → {out_dir / 'compare.mp3'}  ({out_dir / 'index.tsv'})")
    return 0
