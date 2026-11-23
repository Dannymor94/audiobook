#!/usr/bin/env python3
"""Offline read-only coverage audit of the EXISTING RUAccent lexicon.

Reads the local models/dictionary/*.json.gz and text/*.norm.txt; no model load,
network, TTS, corpus changes or automatic pronunciation corrections.
Private word-level TSV and numeric summary stay in gitignored out/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
WORD = re.compile(r"[А-Яа-яЁё]+")
VOWELS = set("аеёиоуыэюя")


def read_gz_map(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing local dictionary file: {path.name}")
    with gzip.open(path, "rt", encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected format in {path.name}: expected a JSON object")
    return data


def words_in(text: str) -> list[str]:
    return [unicodedata.normalize("NFC", w).lower() for w in WORD.findall(text.replace("\u0301", ""))]


def category(word: str, accents: dict, homographs: dict, yo_words: dict) -> str:
    # RUAccent resolves homographs contextually; dictionary presence is not a verdict.
    if word in homographs:
        return "homograph"
    if word in accents:
        return "dictionary_exact"
    if word in yo_words or (("ё" in word) and word.replace("ё", "е") in accents):
        return "yo_needs_context"
    return "not_in_dictionary"


def audit(counts: Counter, accents: dict, homographs: dict, yo_words: dict) -> tuple[dict, list[dict]]:
    rows = []
    token_counts: Counter = Counter()
    type_counts: Counter = Counter()
    multi_token_counts: Counter = Counter()
    multi_type_counts: Counter = Counter()
    for word, n in sorted(counts.items(), key=lambda p: (-p[1], p[0])):
        kind = category(word, accents, homographs, yo_words)
        multi = sum(c in VOWELS for c in word) >= 2
        token_counts[kind] += n
        type_counts[kind] += 1
        if multi:
            multi_token_counts[kind] += n
            multi_type_counts[kind] += 1
        rows.append({"wordform": word, "tokens": n, "vowels_2plus": int(multi), "category": kind})
    data = {
        "total_word_tokens": sum(counts.values()),
        "unique_wordforms": len(counts),
        "tokens_by_category": dict(sorted(token_counts.items())),
        "wordforms_by_category": dict(sorted(type_counts.items())),
        "multisyllabic_tokens": sum(multi_token_counts.values()),
        "multisyllabic_wordforms": sum(multi_type_counts.values()),
        "multisyllabic_tokens_by_category": dict(sorted(multi_token_counts.items())),
        "multisyllabic_wordforms_by_category": dict(sorted(multi_type_counts.items())),
        "dictionary_entries": len(accents),
        "homograph_entries": len(homographs),
        "yo_entries": len(yo_words),
        "interpretation": "Lexical coverage only; NOT pronunciation accuracy or verified stress.",
    }
    return data, rows


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dictionary", type=Path, default=ROOT / "models" / "dictionary")
    p.add_argument("--text-dir", type=Path, default=ROOT / "text")
    p.add_argument("--section", help="Exact NN_slug prefix; default: all .norm.txt sections")
    p.add_argument("--out", type=Path, default=ROOT / "out" / "stress_dictionary_audit")
    args = p.parse_args()

    # Fail before writing when the dictionary is missing or incomplete.
    names = ("accents.json.gz", "omographs.json.gz", "yo_words.json.gz")
    paths = [args.dictionary / name for name in names]
    for path in paths:
        if not path.is_file():
            p.error(f"Local RUAccent dictionary missing: {path}. Do not auto-download.")
    inputs = sorted(args.text_dir.glob("[0-9][0-9]_*.norm.txt"))
    if args.section:
        inputs = [x for x in inputs if x.name == args.section + ".norm.txt"]
    inputs = [x for x in inputs if x.stat().st_size >= 50]
    if not inputs:
        p.error("No matching local normalized text files. No audit performed.")

    accents, homographs, yo_words = [read_gz_map(path) for path in paths]
    words = Counter()
    for path in inputs:
        words.update(words_in(path.read_text(encoding="utf-8")))
    if not words:
        p.error("No Cyrillic words in inputs.")

    summary, rows = audit(words, accents, homographs, yo_words)
    summary["sections_scanned"] = len(inputs)
    summary["dictionary_sha256"] = {x.name: sha256(x) for x in paths}
    args.out.mkdir(parents=True, exist_ok=True)
    private_csv = args.out / "wordforms_PRIVATE.tsv"
    with private_csv.open("w", encoding="utf-8", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=("wordform", "tokens", "vowels_2plus", "category"), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    (args.out / "counts.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print("Private word-level report saved under ignored out/; DO NOT upload that TSV.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
