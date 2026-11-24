"""Offline auxiliary lexical evidence; never a majority-vote stress resolver."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from audiobook.stress_consensus import VOWELS, WORD, book_rows
from audiobook.stress_coverage import build_ledger

WIKTIONARY_SHA256 = "adf32b9cd1059597a14519a8f9348f9dc53e9dfb79e0e42989e884e108f41185"
ATTRIBUTION = {
    "source": "Wiktionary contributors",
    "derivative": "https://github.com/eugenysilin/russian-ukrainian-stress-data",
    "license": "CC-BY-SA-4.0",
    "changes": "Exact lowercase lookup; convert post-vowel codepoint position to zero-based vowel index.",
}


def load_candidates(data: bytes, words: set[str], expected_sha256: str) -> dict[str, int]:
    """Scan pinned compressed UTF-8 table, retain only requested exact forms.

    No automatic ё folding or morphology. The table drops alternative readings.
    """
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("DICTIONARY_SHA256_MISMATCH")
    wanted = {w.lower() for w in words}
    result: dict[str, int] = {}
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        for line in stream:
            fields = line.decode("utf-8").rstrip("\r\n").split("\t")
            word = fields[0]
            if word not in wanted:
                continue
            if len(fields) != 2 or not fields[1].isascii() or not fields[1].isdigit():
                raise ValueError("INVALID_MATCHED_DICTIONARY_ROW")
            index = int(fields[1]) - 1
            if (WORD.fullmatch(word) is None or not 0 <= index < len(word)
                    or word[index] not in VOWELS or word in result):
                raise ValueError("INVALID_MATCHED_DICTIONARY_ROW")
            result[word] = index
    return result


def _stress(finding: dict, source: str) -> int | None:
    value = finding[source + "_stress"]
    if value is None:
        return None
    word = finding["word"]
    if type(value) is not int or not 0 <= value < len(word) or word[value].lower() not in VOWELS:
        raise ValueError("INVALID_PREDICTOR_INDEX")
    return value


def evidence(rows: list[dict], findings: list[dict], candidates: dict[str, int]) -> tuple[list[dict], dict]:
    ledger, _ = build_ledger(rows, findings)
    by_span = {(r["id"], r["start"], r["end"]): r for r in ledger}
    result = []
    for f in findings:
        key = (f["id"], f["start"], f["end"])
        # A Cyrillic substring inside a mixed token is not a standalone word.
        token = by_span.get(key)
        if token is None or not token["status"].startswith("dual_"):
            status = "context_or_token_review"
            d = None
        else:
            a, b = _stress(f, "ruaccent"), _stress(f, "silero")
            d = candidates.get(f["word"].lower())
            if f["status"] == "alignment_error":
                status = "alignment_review"
            elif d is None:
                status = "dictionary_missing"
            elif f["status"] == "agree":
                status = "supports_dual_candidate" if d == a == b else "dictionary_conflict"
            elif f["status"] == "single_source":
                status = "supports_single_candidate" if d in (a, b) else "dictionary_conflict"
            elif f["status"] == "disagree":
                status = "context_conflict"
            else:
                status = "dictionary_only_candidate"
        result.append({**f, "dictionary_stress": d, "lexical_evidence": status,
                       "decision": None, "pronunciation_verified": False})
    counts = Counter(r["lexical_evidence"] for r in result)
    return result, {
        "multisyllabic_occurrences": len(findings),
        "dictionary_hits": sum(r["dictionary_stress"] is not None for r in result),
        "statuses": dict(sorted(counts.items())),
        "decisions_approved": 0,
        "acoustic_verified": 0,
        "release_ready": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--book-text-dir", type=Path, required=True)
    p.add_argument("--audit-dir", type=Path, required=True)
    p.add_argument("--dictionary", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    rows, hashes = book_rows(args.book_text_dir)
    meta = (args.audit_dir / "summary.json").read_bytes()
    audit = json.loads(meta)
    source_hashes = {p.name: h for p, h in hashes.items()}
    if audit.get("source_kind") != "normalized_book_lines" or audit.get("source_sha256") != source_hashes:
        raise ValueError("STALE_OR_WRONG_AUDIT")
    payload = (args.audit_dir / "occurrences.jsonl").read_bytes()
    findings = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    if audit.get("occurrences") != len(findings) or audit.get("statuses") != dict(Counter(f["status"] for f in findings)):
        raise ValueError("AUDIT_SUMMARY_MISMATCH")
    data = args.dictionary.read_bytes()
    candidates = load_candidates(data, {r["word"] for r in findings}, WIKTIONARY_SHA256)
    records, summary = evidence(rows, findings, candidates)
    if (any(hashlib.sha256(p.read_bytes()).hexdigest() != h for p, h in hashes.items())
            or set(args.book_text_dir.glob("[0-9][0-9]_*.norm.txt")) != set(hashes)
            or (args.audit_dir / "summary.json").read_bytes() != meta
            or (args.audit_dir / "occurrences.jsonl").read_bytes() != payload):
        raise ValueError("EVIDENCE_CHANGED")
    summary.update(source_sha256=source_hashes, audit_sha256=hashlib.sha256(payload).hexdigest(),
                   dictionary_sha256=WIKTIONARY_SHA256, attribution=ATTRIBUTION,
                   limitation="Auxiliary lossy dictionary; no contextual decision or acoustic proof.")
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (args.out / "lexical_evidence.jsonl").open("x", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
