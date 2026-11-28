"""Read-only ALG-03 boundary audit. No synthesis, text edits or cache writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audiobook.chunker import _depths, _split_sentences, enum_splits

_WORD = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
_FUNCTION = frozenset("а и но или либо да не ни в во на за из от до с со к ко по о об обо у для без над под при перед через между что чтобы когда если как где кто".split())


def _consume(text: str, cursor: int, part: str) -> tuple[int, int]:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if not part or not text.startswith(part, cursor):
        raise ValueError("RHYTHM_SPAN_MISMATCH")
    return cursor, cursor + len(part)


def _simple_item(s: str) -> bool:
    # Deliberately narrow: one or two lexical words, no numbers/quotes,
    # no standalone function word. These are review candidates, not proof
    # of syntactic coordination.
    words = s.strip().split()
    return (1 <= len(words) <= 2
            and all(_WORD.fullmatch(w) and w.lower() not in _FUNCTION for w in words))


def analyze(text: str) -> dict:
    """Identify exact comma offsets, not guesses from matching substrings."""
    cursor = 0
    legacy, candidates, protected, uncertain = [], [], [], []
    sentences = _split_sentences(text)
    for sentence in sentences:
        start, cursor = _consume(text, cursor, sentence)
        depth = _depths(sentence)
        commas = [i for i, c in enumerate(sentence) if c == ","]
        top = [i for i in commas if depth[i] == 0]
        numeric = {i for i in commas if i > 0 and i + 1 < len(sentence)
                   and sentence[i-1].isdigit() and sentence[i+1].isdigit()}
        protected.extend(start+i for i in commas if depth[i] or i in numeric)
        parts = enum_splits(sentence)
        pos = 0
        for j, part in enumerate(parts):
            _, pos = _consume(sentence, pos, part)
            if j < len(parts)-1:
                while pos < len(sentence) and sentence[pos].isspace():
                    pos += 1
                if pos >= len(sentence) or sentence[pos] != ",":
                    raise ValueError("RHYTHM_COMMA_MISMATCH")
                legacy.append(start+pos)
                pos += 1
        if sentence[pos:].strip():
            raise ValueError("RHYTHM_SENTENCE_NOT_EXHAUSTED")

        # Only explicit colon-led lists with at least three simple items.
        # Preserve all source characters; offsets are advisory and never
        # applied automatically, including when the list looks plausible.
        colons = [i for i, c in enumerate(sentence) if c == ":" and depth[i] == 0]
        if len(colons) == 1:
            colon = colons[0]
            cuts = [i for i in top if i > colon]
            tail = sentence[colon+1:].rstrip(".!?…").strip()
            if len(cuts) >= 2 and not numeric.intersection(cuts):
                items = tail.split(",")
                if len(items) == len(cuts)+1 and all(_simple_item(x) for x in items):
                    candidates.extend(start+i for i in cuts)
        uncertain.extend(start+i for i in top if i not in numeric)
    if text[cursor:].strip():
        raise ValueError("RHYTHM_CHUNK_NOT_EXHAUSTED")
    return {"sentence_count": len(sentences),
            "legacy_comma_offsets": legacy,
            "review_candidate_offsets": candidates,
            "protected_comma_offsets": protected,
            "other_comma_offsets": sorted(set(uncertain)-set(candidates)),
            # Existing synth.chunk_fragments splits ordinary sentences
            # when enum_pause_ms > 0, but build_manifest hashes enum only.
            "legacy_unhashed_sentence_split_risk": len(sentences) > 1 and not legacy}


def audit(manifest: Path) -> dict:
    data = manifest.read_bytes()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    ids = [r["id"] for r in rows]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("INVALID_MANIFEST_INVENTORY")
    results = []
    for row in rows:
        report = analyze(row["text"])
        results.append({"id": row["id"], "hash": row["hash"], **report})
    return {"manifest_sha256": hashlib.sha256(data).hexdigest(),
            "chunk_count": len(rows),
            "legacy_chunks": sum(bool(r["legacy_comma_offsets"]) for r in results),
            "candidate_chunks": sum(bool(r["review_candidate_offsets"]) for r in results),
            "protected_legacy_conflicts": sum(
                bool(set(r["legacy_comma_offsets"]) & set(r["protected_comma_offsets"]))
                for r in results),
            "unhashed_split_risk_chunks": sum(r["legacy_unhashed_sentence_split_risk"] for r in results),
            "rows": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
