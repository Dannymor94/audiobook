"""Offline, occurrence-bound stress map. No TTS or production writes.

Collect RUAccent evidence once, then build repeatably from frozen evidence.
Historical Silero outputs remain evidence, not a newly verified model run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from audiobook.stress_consensus import VOWELS, WORD, align_detailed, book_rows, parse_marked
from audiobook.stress_context_replay import replay, standalone
from audiobook.stress_lexicon import WIKTIONARY_SHA256, evidence, load_candidates

POLICY = "stress-map-v1"
KNOWN_FORMS = ("голоден", "барсуки", "нахала", "материшь", "мужи", "топливо")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def jsonl(rows) -> bytes:
    return b"".join(canonical(r) for r in rows)


def read_jsonl(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line]


def title_input(text: str) -> str:
    """Lowercase standalone Title-case Cyrillic words only in predictor input."""
    chars = list(text)
    for m in WORD.finditer(text):
        w = m.group()
        if len(w) > 1 and w[0].isupper() and w[1:].islower() and standalone(text, m):
            chars[m.start()] = w[0].lower()
    return "".join(chars)


def valid_stress(word: str, value) -> bool:
    return type(value) is int and 0 <= value < len(word) and word[value].lower() in VOWELS


def candidate(word: str, marked) -> int | None:
    if not isinstance(marked, str):
        return None
    token, pos = parse_marked(marked)
    # Restoration of ё is separately reviewed. Never silently alter letters.
    if token.lower() != word.lower() or not valid_stress(word, pos):
        return None
    return pos


def inventory(text_dir: Path, expected: bytes):
    rows, hashes = book_rows(text_dir)
    source = {p.name: h for p, h in hashes.items()}
    names = json.loads(expected)
    if (not isinstance(names, list) or not all(isinstance(n, str) for n in names)
            or sorted(names) != sorted(source)):
        raise ValueError("SECTION_INVENTORY_MISMATCH")
    if any(unicodedata.normalize("NFC", r["text"]) != r["text"] for r in rows):
        raise ValueError("SOURCE_NOT_NFC")
    return rows, source


def tree_hashes(root: Path) -> dict[str, str]:
    files = sorted(p for d in ("nn", "dictionary") for p in (root / d).rglob("*") if p.is_file())
    if not all(any(p.is_relative_to(root / d) for p in files) for d in ("nn", "dictionary")):
        raise ValueError("MISSING_RUACCENT_MODEL_FILES")
    result = {}
    for p in files:
        h = hashlib.sha256()
        with p.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        result[p.relative_to(root).as_posix()] = h.hexdigest()
    return result


def collect(text_dir: Path, expected_path: Path, out: Path) -> None:
    """One paired pass; old RUAccent provenance was incomplete, so run both arms."""
    if out.exists():
        raise ValueError("OUTPUT_EXISTS")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from importlib.metadata import PackageNotFoundError, version
    from audiobook import paths
    from audiobook.accent import _get_accentizer

    expected = expected_path.read_bytes()
    rows, source = inventory(text_dir, expected)
    before = tree_hashes(paths.MODELS)
    acc = _get_accentizer()
    # Read the actual loaded inventories, not a lossy auxiliary lookup.
    attrs = ("accents", "omographs", "yo_homographs")
    if not all(isinstance(getattr(acc, name, None), dict) for name in attrs):
        raise ValueError("UNSUPPORTED_LOADED_RUACCENT_DICTIONARY_SCHEMA")
    words = {m.group().lower() for r in rows for m in WORD.finditer(r["text"])}
    # ё restoration can change which homograph inventory is relevant.
    wanted = words | {w.replace("ё", "е") for w in words}
    dictionaries = {name: {k: v for k, v in getattr(acc, name).items()
                           if isinstance(k, str) and k.lower().replace("ё", "е") in wanted}
                    for name in attrs}
    versions = {}
    for name in ("ruaccent", "onnxruntime", "numpy", "transformers", "tokenizers",
                 "huggingface-hub", "torch"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    result = []
    for row in rows:
        original = row["text"]
        lowered = title_input(original)
        primary = acc.process_all(original)
        alternate = acc.process_all(lowered) if lowered != original else primary
        result.append(dict(id=row["id"], hash=row["hash"],
                           original=primary, title_lower=alternate))
    if (inventory(text_dir, expected) != (rows, source)
            or expected_path.read_bytes() != expected or tree_hashes(paths.MODELS) != before):
        raise ValueError("COLLECT_INPUT_CHANGED")
    raw = jsonl(result)
    lex = canonical(dictionaries)
    meta = dict(source_sha256=source, inventory_sha256=digest(expected),
                model_tree_sha256=before, runtime_versions=versions,
                settings=dict(omograph_model_size="turbo", use_dictionary=True,
                              device="CPU", workdir="local models", custom_dict=None,
                              custom_homographs=None),
                predictor_sha256=digest(raw), loaded_dictionary_subset_sha256=digest(lex),
                case_experiment="original full lines vs standalone Title-case lowercased copy",
                limitation="File inventory includes unused variants; no acoustic truth claim.")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out / "predictions_PRIVATE.jsonl").write_bytes(raw)
    (out / "dictionary_subset_PRIVATE.json").write_bytes(lex)
    (out / "manifest_PRIVATE.json").write_bytes(canonical(meta))


def build(rows: list[dict], findings: list[dict], lexical: list[dict],
          predictions: list[dict], dictionaries: dict, decisions: list[dict],
          *, known_forms=KNOWN_FORMS) -> tuple[list[dict], dict]:
    """All rows retained, conflict defaults unresolved, human overrides exact only."""
    from audiobook.stress_coverage import build_ledger

    ledger, _ = build_ledger(rows, findings)
    by_span = {(t["id"], t["start"], t["end"]): t for t in ledger}
    by_id = {r["id"]: r for r in rows}
    raw = {p["id"]: p for p in predictions}
    if len(raw) != len(predictions) or raw.keys() != by_id.keys():
        raise ValueError("PREDICTION_INVENTORY_MISMATCH")
    if any(raw[k]["hash"] != r["hash"] for k, r in by_id.items()):
        raise ValueError("PREDICTION_IDENTITY_MISMATCH")
    key = lambda f: (f["id"], f["start"], f["end"])
    lex = {key(f): f for f in lexical}
    expected = {key(f) for f in findings}
    if len(lex) != len(lexical) or lex.keys() != expected:
        raise ValueError("LEXICAL_INVENTORY_MISMATCH")
    overrides = {key(d): d for d in decisions}
    if len(overrides) != len(decisions) or not overrides.keys() <= expected:
        raise ValueError("STALE_OR_DUPLICATE_DECISION")
    maps = {}
    case_counts = Counter()
    for r in rows:
        p = raw[r["id"]]
        original, lower = r["text"], title_input(r["text"])
        a, _ = align_detailed(original, p["original"])
        b, _ = align_detailed(lower, p["title_lower"])
        if lower != original:
            case_counts["affected_lines"] += 1
            if a is None and b is not None:
                case_counts["alignment_repaired"] += 1
            if a is not None and b is None:
                case_counts["alignment_regressed"] += 1
        maps[r["id"]] = (a, b)
    accents = dictionaries["accents"]
    homographs = {k.lower().replace("ё", "е") for k in dictionaries["omographs"]}
    yo_homographs = {k.lower().replace("ё", "е") for k in dictionaries["yo_homographs"]}
    result = []
    for f in findings:
        span = key(f)
        word = f["word"]
        w = word.lower()
        other = lex[span]
        if any(other.get(k) != v for k, v in f.items()):
            raise ValueError("LEXICAL_IDENTITY_MISMATCH")
        a, b = maps[f["id"]]
        i = f["ordinal"] - 1
        original = a[i] if a is not None else (None, None)
        lower = b[i] if b is not None else (None, None)
        x, y = (pos if isinstance(token, str) and token.lower() == w
                and valid_stress(word, pos) else None for token, pos in (original, lower))
        d = other["dictionary_stress"]
        if d is not None and not valid_stress(word, d):
            raise ValueError("INVALID_DICTIONARY_STRESS")
        own = candidate(word, accents.get(w))
        silero = f["silero_stress"]
        if (not valid_stress(word, silero) or not isinstance(f["silero_word"], str)
                or f["silero_word"].lower() != w):
            silero = None
        flags = set()
        homograph = w.replace("ё", "е") in homographs | yo_homographs
        if homograph:
            flags.add("homograph")
        if w.replace("ё", "е") in yo_homographs or any(
                isinstance(t, str) and t.lower() != w for t, _ in (original, lower)):
            flags.add("yo_review")
        if word[0].isupper():
            flags.add("capitalized")
        if w in known_forms:
            flags.add("known_model_error_form")
        if a is None:
            flags.add("alignment_review")
        if original != lower:
            flags.add("case_policy_change")
            case_counts["changed_occurrences"] += 1
            if x != y:
                case_counts["changed_stress"] += 1
            if original[0] != lower[0]:
                case_counts["changed_spelling_or_case"] += 1
        token = by_span.get(span)
        unsafe = token is None or not token["status"].startswith("dual_")
        if unsafe:
            flags.add("token_review")
        if d is None:
            flags.add("dictionary_missing")
        if own is not None and d is not None and own != d:
            flags.add("dictionary_conflict")
        if x is not None and d is not None and x != d:
            flags.add("dictionary_exception" if homograph else "dictionary_conflict")
        if x is not None and silero is not None and x != silero:
            flags.add("context_conflict")
        # Keep original-case policy for now. Lowercase experiment is diagnostic,
        # not proof that changed predictions are better. Resolve changes manually.
        stress, status, reason = None, "unresolved", "insufficient_or_conflicting_evidence"
        if not unsafe and not flags.intersection(
                {"yo_review", "dictionary_conflict", "context_conflict", "case_policy_change"}):
            if homograph and x is not None and x == silero:
                stress, status, reason = x, "auto", "context_consensus_homograph"
            elif not homograph and own is not None and (x == own or x is None) and (
                    d is None or d == own) and (silero is None or silero == own):
                stress, status, reason = own, "auto", "ruaccent_dictionary"
            elif not homograph and x is not None and x == silero == d:
                stress, status, reason = x, "auto", "context_and_auxiliary_agreement"
        if span in overrides:
            decision = overrides[span]
            if (decision.get("hash") != f["hash"] or decision.get("word") != word
                    or decision.get("ordinal") != f["ordinal"]
                    or not valid_stress(word, decision.get("stress_index"))
                    or not isinstance(decision.get("reason"), str) or not decision["reason"].strip()
                    or decision.get("authority") != "human"):
                raise ValueError("INVALID_HUMAN_DECISION")
            stress, status, reason = decision["stress_index"], "confirmed", decision["reason"]
            if d is not None and stress != d:
                flags.add("dictionary_exception")
        if status == "unresolved":
            flags.add("unresolved")
        # Only actionable flags enter listening. Capitalization and dictionary
        # absence alone are metadata; unresolved and changed cases are risks.
        risk_flags = sorted(flags - {"capitalized", "dictionary_missing"})
        result.append(dict(id=f["id"], hash=f["hash"], ordinal=f["ordinal"],
                           start=f["start"], end=f["end"], word=word,
                           stress_index=stress, status=status, reason=reason,
                           risk_flags=risk_flags, evidence_flags=sorted(flags),
                           candidates=dict(ruaccent=x, title_lower=y, silero=silero,
                                           ruaccent_dictionary=own, wiktionary=d),
                           acoustic_verified=False))
    result.sort(key=lambda r: (r["id"], r["start"], r["end"]))
    counts = Counter(r["status"] for r in result)
    risky = [r for r in result if r["risk_flags"]]
    return result, dict(rows=len(result), statuses={s: counts[s] for s in
                        ("auto", "confirmed", "unresolved")},
                        risk_flags=dict(sorted(Counter(f for r in result for f in r["risk_flags"]).items())),
                        risky_occurrences=len(risky), risky_forms=len({r["word"].lower() for r in risky}),
                        known_forms_without_exact_anchor=list(known_forms),
                        known_forms_present=sorted({r["word"].lower() for r in result
                                                    if "known_model_error_form" in r["risk_flags"]}),
                        title_case=dict(sorted(case_counts.items())),
                        case_policy="original; lowercase diagnostic only",
                        acoustic_verified=0, release_ready=False)


def assemble(args) -> None:
    expected = args.expected_sections.read_bytes()
    rows, source = inventory(args.book_text_dir, expected)
    paths = {name: folder / filename for name, folder, filename in (
        ("audit_summary", args.audit_dir, "summary.json"),
        ("findings", args.audit_dir, "occurrences.jsonl"),
        ("diagnostics", args.audit_dir, "alignment_rows_PRIVATE.jsonl"),
        ("lex_summary", args.lexicon_dir, "summary.json"),
        ("lexical", args.lexicon_dir, "lexical_evidence.jsonl"),
        ("fresh_manifest", args.evidence, "manifest_PRIVATE.json"),
        ("fresh_predictions", args.evidence, "predictions_PRIVATE.jsonl"),
        ("fresh_dicts", args.evidence, "dictionary_subset_PRIVATE.json"))}
    paths["wiktionary"] = args.dictionary
    if args.decisions is not None:
        paths["decisions"] = args.decisions
    payload = {name: path.read_bytes() for name, path in paths.items()}
    meta, lexmeta, fresh = (json.loads(payload[n]) for n in
                           ("audit_summary", "lex_summary", "fresh_manifest"))
    if (meta.get("source_kind") != "normalized_book_lines"
            or any(m.get("source_sha256") != source for m in (meta, lexmeta, fresh))
            or lexmeta.get("audit_sha256") != digest(payload["findings"])
            or lexmeta.get("dictionary_sha256") != WIKTIONARY_SHA256
            or fresh.get("inventory_sha256") != digest(expected)
            or fresh.get("predictor_sha256") != digest(payload["fresh_predictions"])
            or fresh.get("loaded_dictionary_subset_sha256") != digest(payload["fresh_dicts"])):
        raise ValueError("STALE_EVIDENCE")
    findings, diagnostics, lexical = (read_jsonl(payload[n]) for n in
                                       ("findings", "diagnostics", "lexical"))
    if (meta.get("occurrences") != len(findings)
            or meta.get("statuses") != dict(Counter(f["status"] for f in findings))):
        raise ValueError("AUDIT_SUMMARY_MISMATCH")
    # Recompute auxiliary evidence and validate exact historical raw predictor replay.
    candidates = load_candidates(payload["wiktionary"], {f["word"] for f in findings}, WIKTIONARY_SHA256)
    checked, summary = evidence(rows, findings, candidates)
    if lexical != checked or lexmeta.get("statuses") != summary["statuses"]:
        raise ValueError("LEXICAL_REPLAY_MISMATCH")
    replay(rows, findings, diagnostics, lexical)
    decisions = read_jsonl(payload.get("decisions", b""))
    records, report = build(rows, findings, lexical, read_jsonl(payload["fresh_predictions"]),
                            json.loads(payload["fresh_dicts"]), decisions)
    data = jsonl(records)
    # Risk queue is an occurrence index, not an audio timestamp. Chunk linkage
    # must be supplied by a subsequent proven source-to-chunk mapping step.
    queue = jsonl(dict(id=r["id"], hash=r["hash"], start=r["start"], end=r["end"],
                       ordinal=r["ordinal"], word=r["word"], stress_index=r["stress_index"],
                       risk_flags=r["risk_flags"], chunk_status="UNMAPPED")
                  for r in records if r["risk_flags"])
    if (inventory(args.book_text_dir, expected) != (rows, source)
            or args.expected_sections.read_bytes() != expected
            or any(path.read_bytes() != payload[n] for n, path in paths.items())):
        raise ValueError("BUILD_INPUT_CHANGED")
    report.update(policy=POLICY, map_sha256=digest(data), risk_queue_sha256=digest(queue),
                  complete=len(records) == len(findings), unmapped_risk_occurrences=report["risky_occurrences"])
    manifest = dict(policy=POLICY, builder_commit=args.builder_commit,
                    source_sha256=source, inventory_sha256=digest(expected),
                    input_sha256={n: digest(b) for n, b in payload.items()},
                    decision_sha256=digest(payload.get("decisions", b"")),
                    fresh_ruaccent=fresh, historical_silero_version=meta.get("silero_version"),
                    historical_silero_weight_provenance="not recorded in original audit",
                    auxiliary_dictionary=lexmeta.get("attribution"),
                    known_model_error_forms=list(KNOWN_FORMS), map_sha256=digest(data),
                    risk_queue_sha256=digest(queue))
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, content in (("stress_map.jsonl", data), ("risk_queue_PRIVATE.jsonl", queue),
                          ("manifest_PRIVATE.json", canonical(manifest)),
                          ("summary.json", canonical(report))):
        (args.out / name).write_bytes(content)
    print(json.dumps(report, ensure_ascii=False))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "build"):
        q = sub.add_parser(name)
        q.add_argument("--book-text-dir", type=Path, required=True)
        q.add_argument("--expected-sections", type=Path, required=True)
        q.add_argument("--out", type=Path, required=True)
        if name == "build":
            for flag in ("audit-dir", "lexicon-dir", "dictionary", "evidence"):
                q.add_argument("--" + flag, type=Path, required=True)
            q.add_argument("--decisions", type=Path)
            q.add_argument("--builder-commit", required=True)
    a = p.parse_args()
    if a.cmd == "collect":
        collect(a.book_text_dir, a.expected_sections, a.out)
    else:
        if len(a.builder_commit) != 40 or any(c not in "0123456789abcdef" for c in a.builder_commit):
            raise ValueError("INVALID_BUILDER_COMMIT")
        assemble(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
