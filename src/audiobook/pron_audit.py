"""Audit text/pronounce.yaml against the whole book — no model, no audio.

For every entry: how many times it fires and in which sections, counted with
the very regex pronounce.respell() uses (pronounce.build_pattern: one pass,
longest key first, whole-word, case-sensitive) on the very string respell()
sees — the chunk text after voicecfg.prepare_text (strip_quotes, yo_restore…),
as chunker.build_manifest hashes it. An entry that fires there is the one that
changes a chunk hash; a count over the raw .norm.txt is shown next to it,
because the two can differ (yo_restore already wrote the ё, the chunker cut a
phrase entry in two, a quote mark stood between the words).

Flags:
  мёртвая запись              fires 0 times in the chunks
  в stress_watch              the key (lowercased) is also a probe homograph
  меняет буквы — проверить    the replacement differs from the key by more than
                              stress marking (vowel case, ё/е, doubled vowel);
                              a legitimate typo fix is still worth seeing
  меняет пунктуацию           same letters, different punctuation/spacing
  заглавная согласная         a consonant changed case (house rule marks stress
                              with a capital VOWEL)
  замена = ключ               the entry does nothing
  в тексте ≠ в чанках         raw-text and chunk counts differ

Output: a Russian table on stdout and out/pron_audit.tsv (atomic write).
"""
from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from pathlib import Path

from audiobook import paths

_VOWELS = "аеёиоуыэюя"
_DOUBLED = re.compile(r"([аеиоуыэюя])\1+")
_NON_LETTER = re.compile(r"[\W\d_]+")

FLAG_DEAD = "мёртвая запись"
FLAG_WATCH = "в stress_watch"
FLAG_LETTERS = "меняет буквы — проверить"
FLAG_PUNCT = "меняет пунктуацию"
FLAG_CONSONANT = "заглавная согласная"
FLAG_NOOP = "замена = ключ"
FLAG_TEXT_DIFF = "в тексте ≠ в чанках"


# ------------------------------------------------------------------ pure logic

def _fold(s: str) -> str:
    """Lowercase, ё→е, a run of one vowel → that vowel."""
    return _DOUBLED.sub(r"\1", s.lower().replace("ё", "е"))


def _consonants(s: str) -> str:
    return "".join(c for c in s if c.isalpha() and c.lower() not in _VOWELS)


def change_flags(key: str, value: str) -> list[str]:
    """How the replacement differs from the key, beyond stress marking."""
    if key == value:
        return [FLAG_NOOP]
    fk, fv = _fold(key), _fold(value)
    letters_k, letters_v = _NON_LETTER.sub("", fk), _NON_LETTER.sub("", fv)
    if letters_k != letters_v:
        return [FLAG_LETTERS]
    flags = []
    if re.sub(r"\w", "", fk) != re.sub(r"\w", "", fv):
        flags.append(FLAG_PUNCT)
    if _consonants(key) != _consonants(value):
        flags.append(FLAG_CONSONANT)
    return flags


def count_fires(texts: list[str], pattern: re.Pattern | None) -> Counter:
    """{key: matches} exactly as respell() would replace them in each text."""
    c: Counter = Counter()
    if pattern is None:
        return c
    for t in texts:
        for m in pattern.finditer(t):
            c[m.group(0)] += 1
    return c


def audit_rows(table: dict[str, str], watch: set[str],
               chunk_texts: dict[str, list[str]],
               norm_texts: dict[str, str]) -> list[dict]:
    """One row per table entry (table order). ``chunk_texts``: section → the
    prepared chunk strings respell() sees; ``norm_texts``: section → raw text."""
    from audiobook.pronounce import build_pattern
    pat = build_pattern(table)
    per_sec = {s: count_fires(ts, pat) for s, ts in chunk_texts.items()}
    raw = count_fires(list(norm_texts.values()), pat)
    rows = []
    for key, value in table.items():
        secs = [(s, c[key]) for s, c in sorted(per_sec.items()) if c[key]]
        fires = sum(n for _s, n in secs)
        flags = []
        if fires == 0:
            flags.append(FLAG_DEAD)
        if key.lower() in watch:
            flags.append(FLAG_WATCH)
        flags += change_flags(key, value)
        if raw[key] != fires:
            flags.append(FLAG_TEXT_DIFF)
        rows.append({"key": key, "value": value, "fires": fires,
                     "text_hits": raw[key], "sections": secs, "flags": flags})
    return rows


def _short_sections(secs: list[tuple[str, int]], limit: int = 6) -> str:
    parts = [f"{s.split('_', 1)[0]}×{n}" for s, n in secs]
    if len(parts) > limit:
        parts = parts[:limit] + [f"…+{len(secs) - limit}"]
    return ", ".join(parts) or "—"


def format_report(rows: list[dict]) -> str:
    lines = [f"{'запись':<26} {'замена':<26} {'чанки':>5} {'текст':>5}  секции / флаги"]
    for r in rows:
        tail = _short_sections(r["sections"])
        if r["flags"]:
            tail += "  [" + "; ".join(r["flags"]) + "]"
        lines.append(f"{r['key'][:26]:<26} {r['value'][:26]:<26} "
                     f"{r['fires']:>5} {r['text_hits']:>5}  {tail}")
    counts = Counter(f for r in rows for f in r["flags"])
    lines.append("")
    lines.append(f"записей: {len(rows)}, срабатываний в чанках: {sum(r['fires'] for r in rows)}")
    for flag in (FLAG_DEAD, FLAG_LETTERS, FLAG_WATCH, FLAG_PUNCT, FLAG_CONSONANT,
                 FLAG_NOOP, FLAG_TEXT_DIFF):
        if counts[flag]:
            keys = ", ".join(r["key"] for r in rows if flag in r["flags"])
            lines.append(f"  {flag}: {counts[flag]} — {keys}")
    return "\n".join(lines)


def _tsv_cell(s: str) -> str:
    return s.replace("\t", " ").replace("\n", " ")


def write_tsv(rows: list[dict], path: Path) -> None:
    """Atomic: temp file next to the target, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write("key\tvalue\tfires\ttext_hits\tsections\tflags\n")
        for r in rows:
            secs = ",".join(f"{s}:{n}" for s, n in r["sections"])
            f.write("\t".join(_tsv_cell(x) for x in (
                r["key"], r["value"], str(r["fires"]), str(r["text_hits"]),
                secs, "; ".join(r["flags"]))) + "\n")
    tmp.replace(path)


# ------------------------------------------------------------------ book scan

def book_texts(config: dict) -> tuple[dict[str, list[str]], dict[str, str], list[str]]:
    """(section → prepared chunk texts, section → raw .norm.txt, warnings).
    Sections come from text/blocks/*.blocks.json, as in probe.scan."""
    from audiobook import voicecfg
    from audiobook.chunker import build_chunks, load_units
    chunks: dict[str, list[str]] = {}
    norms: dict[str, str] = {}
    warnings: list[str] = []
    for jf in sorted((paths.TEXT / "blocks").glob("*.blocks.json")):
        d = json.loads(jf.read_text(encoding="utf-8"))
        nn, slug = d["nn"], d["slug"]
        sec = f"{nn}_{slug}"
        normf = paths.TEXT / f"{sec}.norm.txt"
        if not normf.exists():
            warnings.append(f"{sec}: нет {normf.name} — пропущена")
            continue
        norms[sec] = normf.read_text(encoding="utf-8")
        try:
            units = load_units(nn, slug)
        except SystemExit as e:
            warnings.append(f"{sec}: блоки не сходятся с текстом ({e}) — чанки не посчитаны")
            continue
        chunks[sec] = [voicecfg.prepare_text(c["text"], config)
                       for c in build_chunks(units, config)]
    return chunks, norms, warnings


def audit(config: dict, table_path: Path | None = None,
          watch_path: Path | None = None) -> list[dict]:
    from audiobook.probe import load_watch
    from audiobook.pronounce import load_table
    table = load_table(table_path if table_path is not None else paths.TEXT / "pronounce.yaml")
    watch = load_watch(watch_path if watch_path is not None else paths.TEXT / "stress_watch.yaml")
    chunk_texts, norm_texts, warnings = book_texts(config)
    for w in warnings:
        print(f"внимание: {w}")
    return audit_rows(table, watch, chunk_texts, norm_texts)


def run(config: dict, table_path: Path | None = None,
        watch_path: Path | None = None) -> int:
    rows = audit(config, table_path, watch_path)
    if not rows:
        print("pronounce.yaml пуст — проверять нечего")
        return 0
    print(format_report(rows))
    out = paths.OUT / "pron_audit.tsv"
    write_tsv(rows, out)
    print(f"таблица: {out}")
    return 0
