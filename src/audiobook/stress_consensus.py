"""Offline dual-accentor audit. Text annotations are NOT acoustic verdicts.

No source mutation, no TTS, no automatic pronunciation dictionary updates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

WORD = re.compile(r"[А-Яа-яЁё]+")
MARKED = re.compile(r"[А-Яа-яЁё+\u0301]+")
VOWELS = "аеёиоуыэюя"


def fold(word: str) -> str:
    return word.lower().replace("ё", "е")


def parse_marked(token: str) -> tuple[str, int | None]:
    chars: list[str] = []
    marked: list[int] = []
    plus = False
    for c in token:
        if c == "+":
            if plus:
                return token, None
            plus = True
        elif c == "\u0301":
            if plus or not chars or chars[-1].lower() not in VOWELS:
                return token, None
            marked.append(len(chars) - 1)
        else:
            if plus:
                if c.lower() not in VOWELS:
                    return token, None
                marked.append(len(chars))
                plus = False
            chars.append(c)
    if plus:
        return token, None
    word = "".join(chars)
    yo = [i for i, c in enumerate(word) if c.lower() == "ё"]
    if not marked:
        marked = yo
    if len(marked) != 1 or (yo and yo != marked):
        return word, None
    return word, marked[0]


def align(text: str, output: str) -> list[tuple[str, int | None]] | None:
    """Compare every occurrence and preserve intervening characters exactly.

    Case differences and е→ё are allowed only for annotation comparison.
    Reject reordered/deleted words, punctuation edits, broken marks, and
    structural mismatches. Never use altered output as source text.
    """
    source = list(WORD.finditer(text))
    marked = list(MARKED.finditer(output))
    if len(source) != len(marked):
        return None
    a = b = 0
    result = []
    for x, y in zip(source, marked):
        if text[a:x.start()] != output[b:y.start()]:
            return None
        token, stress = parse_marked(y.group())
        if fold(x.group()) != fold(token):
            return None
        if any(c.lower() == "ё" and token[i].lower() != "ё"
               for i, c in enumerate(x.group())):
            return None
        result.append((token, stress))
        a, b = x.end(), y.end()
    if text[a:] != output[b:]:
        return None
    return result


def compare(text: str, ruaccent: str, silero: str) -> list[dict]:
    a, b = align(text, ruaccent), align(text, silero)
    result = []
    for ordinal, m in enumerate(WORD.finditer(text), 1):
        word = m.group()
        if sum(c.lower() in VOWELS for c in word) < 2:
            continue
        x = a[ordinal - 1] if a is not None else None
        y = b[ordinal - 1] if b is not None else None
        sx = x[1] if x else None
        sy = y[1] if y else None
        if a is None or b is None:
            status = "alignment_error"
        elif sx is None and sy is None:
            status = "unresolved"
        elif sx is None or sy is None:
            status = "single_source"
        elif sx == sy and x and y and x[0].lower() == y[0].lower():
            status = "agree"
        else:
            status = "disagree"
        result.append({"ordinal": ordinal, "start": m.start(), "end": m.end(), "word": word,
                       "ruaccent_word": x[0] if x else None, "ruaccent_stress": sx,
                       "silero_word": y[0] if y else None, "silero_stress": sy,
                       "status": status})
    return result


def candidate_input(text: str, findings: list[dict]) -> str:
    """Private trial text only: mark exact agreed occurrences with U+0301.

    Retain punctuation, casing, all other letters and unresolved occurrences.
    This is NOT a production TTS adapter or a claim that consensus is correct.
    """
    expected = [(i, m) for i, m in enumerate(WORD.finditer(text), 1)
                if sum(c.lower() in VOWELS for c in m.group()) >= 2]
    if len(findings) != len(expected):
        raise ValueError("INCOMPLETE_OCCURRENCE_ACCOUNTING")
    parts = []
    prev = 0
    for (i, m), f in zip(expected, findings):
        word = m.group()
        if (f["ordinal"], f["start"], f["end"], f["word"]) != (i, m.start(), m.end(), word):
            raise ValueError("OCCURRENCE_MISMATCH")
        parts.append(text[prev:m.start()])
        if f["status"] == "agree":
            stress = f["ruaccent_stress"]
            annotated = f["ruaccent_word"]
            if (type(stress) is not int or not 0 <= stress < len(word)
                    or word[stress].lower() not in VOWELS
                    or not isinstance(annotated, str)
                    or fold(annotated) != fold(word)
                    or f["silero_stress"] != stress
                    or f["silero_word"].lower() != annotated.lower()):
                raise ValueError("INVALID_AGREEMENT")
            chars = list(word)
            for j, c in enumerate(annotated):
                if c.lower() == "ё" and chars[j].lower() == "е":
                    chars[j] = "Ё" if chars[j].isupper() else "ё"
            if any(c.lower() == "ё" and j != stress for j, c in enumerate(chars)):
                raise ValueError("CONFLICTING_YO_STRESS")
            # ё itself carries stress; do not add a second mark.
            if chars[stress].lower() != "ё":
                chars[stress] += "\u0301"
            word = "".join(chars)
        parts.append(word)
        prev = m.end()
    parts.append(text[prev:])
    return "".join(parts)


def audit(rows: list[dict], primary, secondary) -> tuple[list[dict], dict]:
    """Call both already-local predictors; retain EVERY multisyllabic occurrence."""
    records = []
    for row in rows:
        text = row["text"]
        findings = compare(text, primary(text), secondary(text))
        records.extend({"id": row["id"], "hash": row["hash"], **r} for r in findings)
    counts = Counter(r["status"] for r in records)
    total = len(records)
    return records, {"occurrences": total, "statuses": dict(sorted(counts.items())),
                     "agreement_fraction": counts["agree"] / total if total else None,
                     "not_agreed": total - counts["agree"], "acoustic_checked": 0}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    # Both packages/models must have been separately installed, vetted and pinned.
    # Operator runs in a network-disabled environment; never install at runtime.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from audiobook.accent import accent_lines
    from silero_stress import load_accentor
    from importlib.metadata import version

    data = a.manifest.read_bytes()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("INVALID_MANIFEST")
    secondary = load_accentor()
    records, summary = audit(rows, lambda t: accent_lines([t])[0], secondary)
    summary.update(manifest_sha256=hashlib.sha256(data).hexdigest(),
                   ruaccent_version=version("ruaccent"), silero_version=version("silero-stress"),
                   limitation="Agreement is not ground truth or acoustic correctness; chunk context only.")
    if a.manifest.read_bytes() != data:
        raise ValueError("MANIFEST_CHANGED")
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (a.out / "occurrences.jsonl").open("x", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
