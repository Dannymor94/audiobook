"""Read-only full-token accounting of an existing stress-consensus audit.

No new inference, TTS, source edits or production decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path

from audiobook.stress_consensus import VOWELS, WORD, book_rows

STATUSES = {"agree", "disagree", "single_source", "unresolved", "alignment_error"}


def spans(text: str):
    """Every run of Unicode letters, numbers, marks or symbols, exact offsets.

    Punctuation separates runs; hyphenated words remain separate components
    for accounting, not independently approved pronunciations.
    """
    start = None
    for i, ch in enumerate(text):
        relevant = unicodedata.category(ch)[0] in "LMNS"
        if relevant and start is None:
            start = i
        elif not relevant and start is not None:
            yield start, i
            start = None
    if start is not None:
        yield start, len(text)


def build_ledger(rows: list[dict], findings: list[dict]) -> tuple[list[dict], dict]:
    expected = {}
    ids = set()
    for row in rows:
        if row["id"] in ids:
            raise ValueError("DUPLICATE_ROW")
        ids.add(row["id"])
        for ordinal, m in enumerate(WORD.finditer(row["text"]), 1):
            if sum(c.lower() in VOWELS for c in m.group()) >= 2:
                expected[(row["id"], m.start(), m.end())] = (row["hash"], ordinal, m.group())
    actual = {}
    for f in findings:
        key = (f["id"], f["start"], f["end"])
        if key in actual or key not in expected:
            raise ValueError("UNEXPECTED_OR_DUPLICATE_FINDING")
        if (f["hash"], f["ordinal"], f["word"]) != expected[key] or f["status"] not in STATUSES:
            raise ValueError("FINDING_IDENTITY_MISMATCH")
        actual[key] = f["status"]
    if actual.keys() != expected.keys():
        raise ValueError("MISSING_FINDINGS")
    result = []
    for row in rows:
        text = row["text"]
        for start, end in spans(text):
            token = text[start:end]
            key = (row["id"], start, end)
            vowels = sum(c.lower() in VOWELS for c in token)
            russian = WORD.fullmatch(token) is not None
            compound = ((start > 0 and text[start - 1] in "-‐‑") or
                        (end < len(text) and text[end] in "-‐‑"))
            if not russian:
                status = "other_pronunciation_review"
            elif compound:
                status = "compound_review"
            elif vowels == 0:
                status = "vowelless_context_review"
            elif vowels == 1:
                status = "monosyllable_context_review"
            else:
                status = "dual_" + actual[key]
            result.append(dict(id=row["id"], hash=row["hash"], start=start,
                               end=end, token=token, status=status,
                               pronunciation_verified=False))
    if not result:
        raise ValueError("EMPTY_TOKEN_INVENTORY")
    counts = Counter(r["status"] for r in result)
    return result, dict(token_runs=len(result), statuses=dict(sorted(counts.items())),
                        multisyllabic_findings=len(actual),
                        dual_agreement_tokens=counts["dual_agree"],
                        pronunciation_verified=0, acoustic_verified=0,
                        release_ready=False)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--book-text-dir", type=Path, required=True)
    p.add_argument("--audit-dir", type=Path, required=True)
    p.add_argument("--expected-sections", type=Path, required=True,
                   help="Private JSON list of exact normalized filenames independently derived from canonical book metadata")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows, hashes = book_rows(a.book_text_dir)
    names = sorted(path.name for path in hashes)
    inventory_bytes = a.expected_sections.read_bytes()
    inventory = json.loads(inventory_bytes)
    if not isinstance(inventory, list) or not all(isinstance(n, str) for n in inventory) or sorted(inventory) != names:
        raise ValueError("SECTION_INVENTORY_MISMATCH")
    summary_bytes = (a.audit_dir / "summary.json").read_bytes()
    previous = json.loads(summary_bytes)
    if previous.get("source_kind") != "normalized_book_lines" or previous.get("source_sha256") != {p.name: h for p, h in hashes.items()}:
        raise ValueError("STALE_OR_WRONG_AUDIT")
    data = (a.audit_dir / "occurrences.jsonl").read_bytes()
    findings = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    ledger, summary = build_ledger(rows, findings)
    if previous.get("occurrences") != len(findings) or previous.get("statuses") != dict(Counter(f["status"] for f in findings)):
        raise ValueError("AUDIT_SUMMARY_MISMATCH")
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in hashes.items()) or set(a.book_text_dir.glob("[0-9][0-9]_*.norm.txt")) != set(hashes):
        raise ValueError("SOURCE_CHANGED")
    if a.expected_sections.read_bytes() != inventory_bytes or (a.audit_dir / "summary.json").read_bytes() != summary_bytes or (a.audit_dir / "occurrences.jsonl").read_bytes() != data:
        raise ValueError("EVIDENCE_CHANGED")
    summary.update(source_files=len(hashes), source_lines=len(rows),
                   source_sha256={p.name: h for p, h in hashes.items()},
                   audit_sha256=hashlib.sha256(data).hexdigest(),
                   inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
                   limitation="Token-run accounting only; inventory authority is external; agreement is not verified pronunciation.")
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (a.out / "ledger.jsonl").open("x", encoding="utf-8") as f:
        for r in ledger:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
