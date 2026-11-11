"""Read-only corpus audit: python -m audiobook.stress_map_audit.

JSON output contains identifiers, counts and SHA-256 only, never manuscript text.
No inventory publishing, model loading, chunk building or source writes occur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re

from audiobook import paths
from audiobook.stress_inventory import (
    _cyrillic_tokens, _load_mapped_section, _load_section_skip, _section_data_from_map,
)
from audiobook.unitmap import AnnotationError, chunk_atoms, validate_section


def _checksums() -> dict[str, dict[str, str | None]]:
    """Hash raw inputs and the manifest's ordered pre-synthesis chunk sources."""
    result: dict[str, dict[str, str | None]] = {
        "manifests": {}, "norm": {}, "blocks": {}, "chunk_sources": {},
        "policy": {},
    }
    policy = paths.TEXT / "stress_inventory_exclude.yaml"
    if policy.exists():
        result["policy"][policy.name] = hashlib.sha256(policy.read_bytes()).hexdigest()
    for group, files in (
        ("norm", paths.TEXT.glob("*.norm.txt")),
        ("blocks", (paths.TEXT / "blocks").glob("*.blocks.json")),
        ("manifests", (paths.OUT / "sections").glob("*/manifest.jsonl")),
    ):
        for path in sorted(files):
            key = path.parent.name if group == "manifests" else path.name
            raw = path.read_bytes()
            result[group][key] = hashlib.sha256(raw).hexdigest()
            if group == "manifests":
                try:
                    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
                    sources = [(row["n"], row["id"], row["text"]) for row in rows]
                    encoded = json.dumps(sources, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    result["chunk_sources"][key] = hashlib.sha256(encoded).hexdigest()
                except (ValueError, KeyError, TypeError):
                    result["chunk_sources"][key] = None
    return result


def _verify_section(units, rows, sm, paragraph_ms: int) -> dict:
    """Independently project original source offsets; do not trust span fields."""
    expected = [
        (match.group(), uid, match.start(), match.end())
        for uid, unit in enumerate(units)
        for match in re.finditer(r"\S+", unit["text"])
    ]
    if [(a.text, a.unit_id, a.start, a.end) for a in sm.stream] != expected:
        raise AnnotationError("AUDIT_SOURCE_STREAM", section=sm.section) from None
    cursor = multi = zero = 0
    for row, span in zip(rows, sm.spans, strict=True):
        tokens = re.findall(r"\S+", row["text"])
        end = cursor + len(tokens)
        source = expected[cursor:end]
        ids = frozenset(a[1] for a in source)
        kinds = {units[uid]["type"] if units[uid]["type"] in ("heading", "stack") else "text" for uid in ids}
        if (
            not tokens or span.chunk_id != row["id"]
            or span.atom_start != cursor or span.atom_end != end
            or tokens != [a[0] for a in source]
            or span.spans != tuple((a[2], a[3]) for a in source)
            or span.unit_ids != ids or kinds != {span.kind} or span.end_modes is not None
        ):
            raise AnnotationError("AUDIT_PROVENANCE", section=sm.section, chunk_id=row["id"]) from None
        stored = chunk_atoms(sm, row["id"])
        if len(stored) != len(tokens) or not all(a is b for a, b in zip(stored, sm.stream[cursor:end])):
            raise AnnotationError("AUDIT_ATOM_IDENTITY", section=sm.section, chunk_id=row["id"]) from None
        cursor = end
        multi += len(ids) > 1
        zero += not bool(_cyrillic_tokens(row["text"]))
    if cursor != len(expected):
        raise AnnotationError("AUDIT_CONSUMPTION", section=sm.section) from None
    text, starts, chunk_ids, diagnostics = _section_data_from_map(rows, sm, paragraph_ms)
    if (
        len(starts) != len(rows) or chunk_ids != [r["id"] for r in rows]
        or any(text[start:start + len(row["text"])] != row["text"] for start, row in zip(starts, rows))
        or len(diagnostics) != zero
    ):
        raise AnnotationError("AUDIT_INVENTORY_OFFSETS", section=sm.section) from None
    return {
        "units": len(units), "chunks": len(rows), "source_atoms": len(expected),
        "consumed_atoms": cursor, "multi_unit_chunks": multi, "zero_cyrillic_chunks": zero,
        "repeated_atoms": len(expected) - len({a[0] for a in expected}),
        "atom_consumption_verified": True, "provenance_verified": True,
        "stored_atom_identity_verified": True, "inventory_offsets_verified": True,
    }


def audit_corpus(paragraph_ms: int = 900) -> dict:
    """Audit every norm section with the same approved exclusions as inventory."""
    before = _checksums()
    records, excluded, failures = [], [], []
    skips = _load_section_skip(paths.TEXT / "stress_inventory_exclude.yaml")
    for norm in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm.name.removesuffix(".norm.txt")
        safe_section = None
        try:
            validate_section(section)
            safe_section = section
            if section in skips:
                if (paths.OUT / "sections" / section / "manifest.jsonl").exists():
                    raise AnnotationError("STALE_EXCLUSION", section=section) from None
                tokens = len(_cyrillic_tokens(norm.read_text(encoding="utf-8")))
                if tokens != skips[section]["tokens"]:
                    raise AnnotationError("EXCLUSION_TOKEN_MISMATCH", section=section) from None
                excluded.append({"section": section, "tokens": tokens})
                continue
            units, rows, sm = _load_mapped_section(section)
            record = _verify_section(units, rows, sm, paragraph_ms)
            if _cyrillic_tokens(norm.read_text(encoding="utf-8")) != _cyrillic_tokens(
                _section_data_from_map(rows, sm, paragraph_ms)[0]
            ):
                raise AnnotationError("NORM_TOKEN_MISMATCH", section=section) from None
            records.append({"section": section, **record})
        except AnnotationError as exc:
            failures.append({"section": safe_section, "chunk_id": exc.chunk_id, "code": exc.code})
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            failures.append({"section": safe_section, "chunk_id": None, "code": "AUDIT_INPUT_ERROR"})
    after = _checksums()
    unchanged = before == after
    return {
        "status": "PASS" if records and not failures and unchanged else "BLOCKED",
        "paragraph_ms": paragraph_ms,
        "sections_total": len(records) + len(excluded) + len(failures),
        "sections_mapped": len(records), "sections_failed": len(failures),
        "sections_excluded": len(excluded),
        "totals": {key: sum(r[key] for r in records) for key in (
            "units", "chunks", "source_atoms", "consumed_atoms", "multi_unit_chunks",
            "zero_cyrillic_chunks", "repeated_atoms",
        )},
        "sections": records, "excluded": excluded, "failures": failures,
        "checksums": {"before": before, "after": after, "unchanged": unchanged},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only аудит atom mapping без вывода текста книги.")
    parser.add_argument("--paragraph-ms", type=int, default=900, help="Порог паузы inventory, мс.")
    args = parser.parse_args()
    try:
        summary = audit_corpus(args.paragraph_ms)
    except Exception:
        # Parser/IO exceptions can contain source lines. Fail closed without
        # serializing exception messages, reprs or implicit exception context.
        summary = {
            "status": "BLOCKED",
            "failures": [{"section": None, "chunk_id": None, "code": "AUDIT_INPUT_ERROR"}],
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
