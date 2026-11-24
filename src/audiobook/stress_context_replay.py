"""Replay saved predictor outputs, localize alignment failures, queue context review.

No inference, source edits, dictionary approvals, or production decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from audiobook.stress_consensus import (
    MARKED, WORD, align_detailed, book_rows, compare, fold, parse_marked,
)
from audiobook.stress_coverage import build_ledger


def standalone(text: str, match) -> bool:
    for pos in (match.start() - 1, match.end()):
        if 0 <= pos < len(text):
            c = text[pos]
            if unicodedata.category(c)[0] in "LMNS" or c in "-‐‑":
                return False
    return True


def local_candidates(text: str, output: str) -> dict:
    """Exact full alignment first; on failure use unique intact triples only.

    Local results are diagnostic candidates, not an assertion of contextual
    correctness, because changes elsewhere may affect a predictor's decision.
    """
    source = list(WORD.finditer(text))
    aligned, _ = align_detailed(text, output)
    if aligned is not None:
        return {i: (word, stress, "full") for i, (word, stress) in enumerate(aligned, 1)}
    marked = list(MARKED.finditer(output))
    src = [fold(m.group()) for m in source]
    dst = [fold(parse_marked(m.group())[0]) for m in marked]
    src_counts, dst_counts = Counter(src), Counter(dst)
    triples = defaultdict(list)
    for j in range(1, len(dst) - 1):
        triples[tuple(dst[j - 1:j + 2])].append(j)
    result = {}
    for i in range(1, len(src) - 1):
        if src_counts[src[i]] != 1 or dst_counts[src[i]] != 1:
            continue
        hits = triples.get(tuple(src[i - 1:i + 2]), [])
        if len(hits) != 1:
            continue
        j = hits[0]
        a, b = source[i - 1:i + 2], marked[j - 1:j + 2]
        if not all(standalone(text, m) for m in a) or not all(standalone(output, m) for m in b):
            continue
        x = text[a[0].start():a[-1].end()]
        y = output[b[0].start():b[-1].end()]
        pair, _ = align_detailed(x, y)
        if pair is not None and len(pair) == 3:
            word, stress = pair[1]
            result[i + 1] = (word, stress, "local_context")
    return result


def replay(rows: list[dict], findings: list[dict], diagnostics: list[dict],
           lexical: list[dict]) -> tuple[list[dict], dict]:
    ledger, _ = build_ledger(rows, findings)
    token_by_span = {(t["id"], t["start"], t["end"]): t for t in ledger}
    row_by_id = {r["id"]: r for r in rows}
    raw = {}
    for d in diagnostics:
        key = d["id"]
        if key in raw or key not in row_by_id or d["hash"] != row_by_id[key]["hash"]:
            raise ValueError("DIAGNOSTIC_IDENTITY_MISMATCH")
        raw[key] = d
    if raw.keys() != row_by_id.keys():
        raise ValueError("MISSING_DIAGNOSTICS")
    by_row = defaultdict(list)
    for f in findings:
        by_row[f["id"]].append(f)
    lexical_by_span = {}
    for f in lexical:
        key = (f["id"], f["start"], f["end"])
        if key in lexical_by_span:
            raise ValueError("DUPLICATE_LEXICAL_EVIDENCE")
        lexical_by_span[key] = f
    expected_keys = {(f["id"], f["start"], f["end"]) for f in findings}
    if lexical_by_span.keys() != expected_keys:
        raise ValueError("LEXICAL_INVENTORY_MISMATCH")
    result = []
    for row in rows:
        key, text = row["id"], row["text"]
        d = raw[key]
        a, b = d["ruaccent_output"], d["silero_output"]
        old = by_row[key]
        reproduced = compare(text, a, b)
        if (reproduced != [{k: v for k, v in f.items() if k not in ("id", "hash")} for f in old]
                or d["multisyllabic_occurrences"] != len(old)
                or d["ruaccent_alignment"] != align_detailed(text, a)[1]
                or d["silero_alignment"] != align_detailed(text, b)[1]):
            raise ValueError("REPLAY_MISMATCH")
        maps = (local_candidates(text, a), local_candidates(text, b)) if any(
            f["status"] == "alignment_error" for f in old) else ({}, {})
        for f in old:
            span = (key, f["start"], f["end"])
            lex = lexical_by_span[span]
            if any(lex.get(k) != v for k, v in f.items()):
                raise ValueError("LEXICAL_IDENTITY_MISMATCH")
            flags = []
            if f["status"] != "agree":
                flags.append(f["status"])
            if lex["lexical_evidence"] != "supports_dual_candidate":
                flags.append(lex["lexical_evidence"])
            token = token_by_span.get(span)
            if token is None or not token["status"].startswith("dual_"):
                flags.append("nonstandalone")
            if not flags:
                continue
            x, y = (m.get(f["ordinal"]) for m in maps)
            recovery = "not_applicable"
            if f["status"] == "alignment_error":
                if x is None or y is None:
                    recovery = "unmapped"
                elif x[1] is None or y[1] is None:
                    recovery = "missing_stress"
                elif x[1] == y[1] and x[0].lower() == y[0].lower():
                    recovery = "candidate_agreement"
                elif x[1] == y[1]:
                    recovery = "yo_spelling_review"
                else:
                    recovery = "candidate_conflict"
            elif (f["status"] == "disagree" and f["ruaccent_stress"] == f["silero_stress"]
                  and f["ruaccent_stress"] is not None):
                flags.append("yo_spelling_review")
            result.append(dict(id=key, hash=row["hash"], ordinal=f["ordinal"],
                               start=f["start"], end=f["end"], word=f["word"],
                               flags=sorted(set(flags)), recovery=recovery,
                               ruaccent_candidate=x, silero_candidate=y,
                               lexical_evidence=lex["lexical_evidence"],
                               dictionary_stress=lex["dictionary_stress"],
                               decision=None))
    counts = Counter(r["recovery"] for r in result)
    return result, dict(multisyllabic_occurrences=len(findings),
                        queued_occurrences=len(result),
                        distinct_queued_forms=len({r["word"].lower() for r in result}),
                        recovery=dict(sorted(counts.items())),
                        flags=dict(sorted(Counter(flag for r in result for flag in r["flags"]).items())),
                        original_alignment_errors=sum(f["status"] == "alignment_error" for f in findings),
                        decisions_approved=0, release_ready=False)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--book-text-dir", type=Path, required=True)
    p.add_argument("--audit-dir", type=Path, required=True)
    p.add_argument("--lexicon-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows, hashes = book_rows(a.book_text_dir)
    paths = [a.audit_dir / n for n in ("summary.json", "occurrences.jsonl", "alignment_rows_PRIVATE.jsonl")]
    paths += [a.lexicon_dir / n for n in ("summary.json", "lexical_evidence.jsonl")]
    payloads = {p: p.read_bytes() for p in paths}
    audit_meta, lex_meta = (json.loads(payloads[paths[i]]) for i in (0, 3))
    source_hashes = {p.name: h for p, h in hashes.items()}
    digest = hashlib.sha256(payloads[paths[1]]).hexdigest()
    if (audit_meta.get("source_kind") != "normalized_book_lines"
            or audit_meta.get("source_sha256") != source_hashes
            or lex_meta.get("source_sha256") != source_hashes
            or lex_meta.get("audit_sha256") != digest):
        raise ValueError("STALE_EVIDENCE")
    findings, diagnostics, lexical = ([json.loads(line) for line in payloads[paths[i]].decode("utf-8").splitlines()
                                       if line.strip()] for i in (1, 2, 4))
    if audit_meta.get("occurrences") != len(findings) or audit_meta.get("statuses") != dict(Counter(f["status"] for f in findings)):
        raise ValueError("AUDIT_SUMMARY_MISMATCH")
    if lex_meta.get("multisyllabic_occurrences") != len(lexical) or lex_meta.get("statuses") != dict(Counter(f["lexical_evidence"] for f in lexical)):
        raise ValueError("LEXICON_SUMMARY_MISMATCH")
    queue, summary = replay(rows, findings, diagnostics, lexical)
    if (any(p.read_bytes() != data for p, data in payloads.items())
            or any(hashlib.sha256(p.read_bytes()).hexdigest() != h for p, h in hashes.items())
            or set(a.book_text_dir.glob("[0-9][0-9]_*.norm.txt")) != set(hashes)):
        raise ValueError("EVIDENCE_CHANGED")
    summary.update(audit_sha256=digest, source_sha256=source_hashes,
                   replay_sha256=hashlib.sha256(payloads[paths[2]]).hexdigest(),
                   lexical_sha256=hashlib.sha256(payloads[paths[4]]).hexdigest(),
                   limitation="Diagnostic candidates only; no context-correctness claim or acoustic approval.")
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (a.out / "review_queue_PRIVATE.jsonl").open("x", encoding="utf-8") as f:
        for record in queue:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
