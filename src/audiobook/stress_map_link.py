"""Read-only binding of a frozen lexical risk map to existing render manifests.

Require complete ordered equality of non-whitespace tokens per section.
Never guess using substrings, fuzzy matches, or text hashes alone.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from audiobook.stress_consensus import VOWELS, WORD, book_rows
from audiobook.stress_map import canonical, digest, jsonl, read_jsonl, valid_stress

TOKEN = re.compile(r"\S+")


def bind_section(source: list[dict], manifest: list[dict]) -> dict | None:
    """Whole section positional proof, allowing only whitespace-run changes."""
    if not manifest:
        return None
    if len({r["id"] for r in manifest}) != len(manifest):
        raise ValueError("DUPLICATE_CHUNK_ID")
    if any(type(r.get("n")) is not int or r["n"] != i
           or not isinstance(r.get("hash"), str) or not r["hash"]
           or not isinstance(r.get("text"), str)
           for i, r in enumerate(manifest, 1)):
        raise ValueError("INVALID_MANIFEST_ORDER_OR_IDENTITY")
    a = [(r, m) for r in source for m in TOKEN.finditer(r["text"])]
    b = [(r, m) for r in manifest for m in TOKEN.finditer(r["text"])]
    if [m.group() for _, m in a] != [m.group() for _, m in b]:
        return None
    return {(r["id"], m.start(), m.end()): (c, n.start())
            for (r, m), (c, n) in zip(a, b)}


def link(rows: list[dict], records: list[dict], manifests: dict[str, list[dict]]):
    source = defaultdict(list)
    by_id = {}
    expected = {}
    for r in rows:
        by_id[r["id"]] = r
        section = r["id"].rsplit(":", 1)[0].removesuffix(".norm")
        source[section].append(r)
        for ordinal, m in enumerate(WORD.finditer(r["text"]), 1):
            if sum(c.lower() in VOWELS for c in m.group()) >= 2:
                expected[r["id"], m.start(), m.end()] = (r["hash"], ordinal, m.group())
    actual = {}
    for r in records:
        key = (r["id"], r["start"], r["end"])
        if key in actual or expected.get(key) != (r["hash"], r["ordinal"], r["word"]):
            raise ValueError("MAP_OCCURRENCE_MISMATCH")
        if (r["status"] not in ("auto", "confirmed", "unresolved")
                or (r["stress_index"] is not None if r["status"] == "unresolved"
                    else not valid_stress(r["word"], r["stress_index"]))):
            raise ValueError("INVALID_MAP_DECISION")
        actual[key] = r
    if actual.keys() != expected.keys():
        raise ValueError("INCOMPLETE_MAP")
    maps = {s: bind_section(rs, manifests[s]) for s, rs in source.items() if s in manifests}
    # Build an index for each source word, including components of mixed tokens.
    token_index = {}
    for r in rows:
        tokens = list(TOKEN.finditer(r["text"]))
        j = 0
        for m in WORD.finditer(r["text"]):
            while j < len(tokens) and tokens[j].end() <= m.start():
                j += 1
            if j < len(tokens) and tokens[j].start() <= m.start() and m.end() <= tokens[j].end():
                token_index[r["id"], m.start(), m.end()] = tokens[j]
    grouped = defaultdict(list)
    unmapped = []
    for key, r in sorted(actual.items()):
        if not r["risk_flags"]:
            continue
        section = r["id"].rsplit(":", 1)[0].removesuffix(".norm")
        binding = maps.get(section)
        token = token_index.get(key)
        if binding is None or token is None:
            unmapped.append({**r, "section": section, "chunk_status": "UNMAPPED",
                             "reason": "no_manifest" if section not in manifests else "section_text_mismatch"})
            continue
        chunk, pos = binding[r["id"], token.start(), token.end()]
        start = pos + r["start"] - token.start()
        end = start + len(r["word"])
        if chunk["text"][start:end] != r["word"]:
            raise ValueError("CHUNK_SPAN_MISMATCH")
        grouped[section, chunk["id"], chunk["hash"]].append(dict(
            source_id=r["id"], source_hash=r["hash"], source_start=r["start"],
            source_end=r["end"], ordinal=r["ordinal"], chunk_start=start, chunk_end=end,
            word=r["word"], stress_index=r["stress_index"], status=r["status"],
            risk_flags=r["risk_flags"]))
    queue = [dict(section=s, chunk_id=c, chunk_hash=h, occurrences=rs,
                  chunk_status="MAPPED_TEXT_ONLY")
             for (s, c, h), rs in sorted(grouped.items())]
    counts = Counter(r["reason"] for r in unmapped)
    summary = dict(map_rows=len(records), risk_occurrences=sum(len(r["occurrences"]) for r in queue) + len(unmapped),
                   mapped_occurrences=sum(len(r["occurrences"]) for r in queue),
                   mapped_chunks=len(queue), unmapped_occurrences=len(unmapped),
                   unmapped_reasons=dict(sorted(counts.items())),
                   sections_with_manifest=len(maps),
                   exact_section_matches=sum(v is not None for v in maps.values()),
                   section_text_mismatches=sum(v is None for v in maps.values()),
                   sections_without_manifest=len(source.keys() - manifests.keys()),
                   acoustic_verified=0, release_ready=False)
    return queue, unmapped, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--book-text-dir", type=Path, required=True)
    p.add_argument("--map-dir", type=Path, required=True)
    p.add_argument("--sections-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows, source_hashes = book_rows(a.book_text_dir)
    meta_path = a.map_dir / "manifest_PRIVATE.json"
    map_path = a.map_dir / "stress_map.jsonl"
    meta_bytes, data = meta_path.read_bytes(), map_path.read_bytes()
    meta = json.loads(meta_bytes)
    if (meta.get("map_sha256") != digest(data)
            or meta.get("source_sha256") != {p.name: h for p, h in source_hashes.items()}):
        raise ValueError("STALE_MAP")
    paths = sorted(a.sections_dir.glob("*/manifest.jsonl"))
    payload = {p: p.read_bytes() for p in paths}
    manifests = {p.parent.name: read_jsonl(b) for p, b in payload.items()}
    queue, unmapped, summary = link(rows, read_jsonl(data), manifests)
    if (meta_path.read_bytes() != meta_bytes or map_path.read_bytes() != data
            or book_rows(a.book_text_dir) != (rows, source_hashes)
            or sorted(a.sections_dir.glob("*/manifest.jsonl")) != paths
            or any(p.read_bytes() != b for p, b in payload.items())):
        raise ValueError("INPUT_CHANGED")
    summary.update(map_sha256=digest(data),
                   manifest_sha256={p.parent.name: digest(b) for p, b in payload.items()})
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, content in (("chunk_risks_PRIVATE.jsonl", jsonl(queue)),
                          ("unmapped_PRIVATE.jsonl", jsonl(unmapped)),
                          ("summary_PRIVATE.json", canonical(summary))):
        (a.out / name).write_bytes(content)
    print(json.dumps({k: v for k, v in summary.items() if k != "manifest_sha256"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
