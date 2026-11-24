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


_HSPACE = " \t\u00a0\u202f"
_GAP_PUNCT = '.,!?;:«»„“”"()[]'


def _format_gap(a: str, b: str, *, edge: bool) -> bool:
    """Only horizontal spacing; retain punctuation and lexical boundaries.

    Never accept changed digits, Latin text, hyphens, signs or newlines.
    """
    if any(c not in _HSPACE + _GAP_PUNCT for c in a + b):
        return False
    stripped_a = "".join(c for c in a if c not in _HSPACE)
    stripped_b = "".join(c for c in b if c not in _HSPACE)
    if stripped_a != stripped_b:
        return False
    return bool(stripped_a) or edge or bool(a and b)


def align_detailed(text: str, output: str, *, strict: bool = False):
    """Return exact ordered annotation mapping and non-text reason category."""
    source = list(WORD.finditer(text))
    marked = list(MARKED.finditer(output))
    if len(source) != len(marked):
        return None, "word_count"
    a = b = 0
    result = []
    reformatted = False
    for i, (x, y) in enumerate(zip(source, marked)):
        left, right = text[a:x.start()], output[b:y.start()]
        if left != right:
            if strict or not _format_gap(left, right, edge=i == 0):
                return None, "separator_changed"
            reformatted = True
        token, stress = parse_marked(y.group())
        if fold(x.group()) != fold(token):
            return None, "word_changed"
        if any(c.lower() == "ё" and token[j].lower() != "ё"
               for j, c in enumerate(x.group())):
            return None, "source_yo_lost"
        result.append((token, stress))
        a, b = x.end(), y.end()
    if text[a:] != output[b:]:
        if strict or not _format_gap(text[a:], output[b:], edge=True):
            return None, "separator_changed"
        reformatted = True
    return result, "format_only" if reformatted else "exact"


def align(text: str, output: str) -> list[tuple[str, int | None]] | None:
    """Allow only proven harmless horizontal spacing differences.

    Reject word reorder/deletion, punctuation or lexical changes. Source
    offsets remain authoritative; predictor output is never used as source.
    """
    return align_detailed(text, output)[0]


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
    if "\u0301" in text or "+" in text:
        raise ValueError("PREMARKED_OR_NONPLAIN_SOURCE")
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


def audit(rows: list[dict], primary, secondary, *, row_diagnostics: list[dict] | None = None) -> tuple[list[dict], dict]:
    """Call both predictors once; retain all occurrences and private replay evidence."""
    records = []
    reasons = Counter()
    baseline_errors = 0
    recovered = 0
    for row in rows:
        text = row["text"]
        a, b = primary(text), secondary(text)
        findings = compare(text, a, b)
        strict_a, _ = align_detailed(text, a, strict=True)
        strict_b, _ = align_detailed(text, b, strict=True)
        aligned_a, why_a = align_detailed(text, a)
        aligned_b, why_b = align_detailed(text, b)
        n = len(findings)
        if strict_a is None or strict_b is None:
            baseline_errors += n
            if aligned_a is not None and aligned_b is not None:
                recovered += n
        reasons["ruaccent:" + why_a] += 1
        reasons["silero:" + why_b] += 1
        if row_diagnostics is not None:
            row_diagnostics.append(dict(id=row["id"], hash=row["hash"],
                                        ruaccent_output=a, silero_output=b,
                                        ruaccent_alignment=why_a, silero_alignment=why_b,
                                        multisyllabic_occurrences=n))
        records.extend({"id": row["id"], "hash": row["hash"], **r} for r in findings)
    counts = Counter(r["status"] for r in records)
    total = len(records)
    return records, {"occurrences": total, "statuses": dict(sorted(counts.items())),
                     "agreement_fraction": counts["agree"] / total if total else None,
                     "not_agreed": total - counts["agree"], "acoustic_checked": 0,
                     "alignment_reasons_by_row": dict(sorted(reasons.items())),
                     "strict_baseline_alignment_error_occurrences": baseline_errors,
                     "format_recovered_occurrences": recovered}


def book_rows(text_dir: Path) -> tuple[list[dict], dict[Path, str]]:
    """Read canonical normalized sections, not stale accented files.

    IDs/hashes identify source lines here, NOT production chunks.
    """
    paths = sorted(text_dir.glob("[0-9][0-9]_*.norm.txt"))
    if not paths:
        raise ValueError("NO_NORMALIZED_SECTIONS")
    rows = []
    hashes = {}
    for path in paths:
        data = path.read_bytes()
        hashes[path] = hashlib.sha256(data).hexdigest()
        for line_no, line in enumerate(data.decode("utf-8").splitlines(), 1):
            if line.strip():
                rows.append({"id": f"{path.stem}:{line_no}", "text": line,
                             "hash": hashlib.sha256(line.encode("utf-8")).hexdigest()})
    if not rows:
        raise ValueError("EMPTY_BOOK")
    return rows, hashes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--book-text-dir", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    # Both packages/models must have been separately installed, vetted and pinned.
    # Operator runs in a network-disabled environment; never install at runtime.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from audiobook.accent import accent_lines
    from silero_stress import load_accentor
    from importlib.metadata import version

    if version("silero-stress") != "1.4":
        raise ValueError("UNEXPECTED_SILERO_VERSION")
    if a.manifest is not None:
        data = a.manifest.read_bytes()
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        hashes = {a.manifest: hashlib.sha256(data).hexdigest()}
        source_kind = "chunk_manifest"
    else:
        rows, hashes = book_rows(a.book_text_dir)
        source_kind = "normalized_book_lines"
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("INVALID_SOURCE")
    secondary = load_accentor()
    row_diagnostics: list[dict] = []
    records, summary = audit(rows, lambda t: accent_lines([t])[0], secondary, row_diagnostics=row_diagnostics)
    summary.update(source_kind=source_kind, source_files=len(hashes),
                   source_sha256={p.name: h for p, h in hashes.items()},
                   ruaccent_version=version("ruaccent"), silero_version=version("silero-stress"),
                   limitation="Agreement is not ground truth or acoustic correctness; local chunk/line context only.")
    if a.manifest is not None:
        summary["manifest_sha256"] = hashes[a.manifest]
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != h for p, h in hashes.items()):
        raise ValueError("SOURCE_CHANGED")
    if a.book_text_dir is not None and set(a.book_text_dir.glob("[0-9][0-9]_*.norm.txt")) != set(hashes):
        raise ValueError("SOURCE_FILES_CHANGED")
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (a.out / "occurrences.jsonl").open("x", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (a.out / "alignment_rows_PRIVATE.jsonl").open("x", encoding="utf-8") as f:
        for row in row_diagnostics:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    by_id: dict[str, list[dict]] = {}
    for record in records:
        by_id.setdefault(record["id"], []).append(record)
    trial_ready = 0
    with (a.out / "trial_inputs.jsonl").open("x", encoding="utf-8") as f:
        for row in rows:
            findings = by_id.get(row["id"], [])
            try:
                marked = candidate_input(row["text"], findings)
            except ValueError:
                marked = None
            complete = marked is not None and all(x["status"] == "agree" for x in findings)
            trial_ready += int(complete)
            f.write(json.dumps({"id": row["id"], "hash": row["hash"],
                                "marked_trial_text": marked,
                                "complete_consensus": complete}, ensure_ascii=False) + "\n")
    summary["complete_consensus_rows"] = trial_ready
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
