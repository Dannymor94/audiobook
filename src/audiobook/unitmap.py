"""Recover source unit identity and chunk kind via Cyrillic token-index alignment.

Public API:
  annotate_units(manifest_chunks, units, *, section="") -> list[dict]
  AnnotationError
"""
from __future__ import annotations

import re

_CYR = re.compile(r"[а-яёА-ЯЁ]+")
_WS = re.compile(r"\s+")
_TRAILING_TERM = re.compile(r"[.!?…]+$")


def _tokens(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in _CYR.findall(text)]


def _unit_kind(unit: dict) -> str:
    t = unit.get("type", "")
    if t == "heading":
        return "heading"
    if t == "stack":
        return "stack"
    return "text"


def _norm_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _match_key(text: str) -> str:
    """Normalize whitespace and strip trailing sentence-terminal punctuation."""
    return _TRAILING_TERM.sub("", _norm_ws(text))


class AnnotationError(Exception):
    """Raised when manifest chunks cannot be reliably mapped to source units.

    Attributes:
        reason      — human-readable failure description
        section     — section slug (empty if caller did not pass it)
        chunk_id    — manifest chunk id (empty if unavailable)
        mismatch_idx — absolute token index of first mismatch (-1 if N/A)
    """

    def __init__(
        self,
        reason: str,
        *,
        section: str = "",
        chunk_id: str = "",
        mismatch_idx: int = -1,
    ) -> None:
        self.reason = reason
        self.section = section
        self.chunk_id = chunk_id
        self.mismatch_idx = mismatch_idx
        parts = []
        if section:
            parts.append(f"section={section!r}")
        if chunk_id:
            parts.append(f"chunk={chunk_id!r}")
        if mismatch_idx >= 0:
            parts.append(f"tok={mismatch_idx}")
        detail = f" ({', '.join(parts)})" if parts else ""
        super().__init__(f"unitmap: {reason}{detail}")


def _resolve_zero_token(
    chunk: dict,
    chunk_idx: int,
    all_chunk_toks: list[list[str]],
    abs_pos: int,
    unit_stream: list[tuple[str, int, str]],
    units: list[dict],
    unit_match_end: dict[int, int],
    section: str,
) -> tuple[int, str]:
    """I2′: resolve a zero-Cyrillic-token chunk via text-anchor search.

    Anchors are the nearest preceding/following Cyrillic chunks.  Searches only
    source units between those anchors.  Zero-token chunks do not advance abs_pos,
    so consecutive zero-token chunks share the same anchor boundaries and ordering
    is enforced via unit_match_end.

    Returns (unit_id, kind).  Raises AnnotationError on any ambiguity or failure.
    """
    chunk_id = str(chunk.get("id", ""))
    raw_text = chunk.get("text", "")

    if not raw_text.strip():
        raise AnnotationError(
            "empty/whitespace-only chunk (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    key = _match_key(raw_text)
    if not key:
        raise AnnotationError(
            "chunk text reduces to empty after normalization (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    # Lower anchor: unit owning the last token consumed before this chunk.
    lower_uid = 0
    if abs_pos > 0:
        _, lower_uid, _ = unit_stream[abs_pos - 1]

    # Upper anchor: unit owning the first token of the next Cyrillic chunk.
    # Zero-token chunks don't advance abs_pos, so the next Cyrillic chunk's
    # first token is always at abs_pos in unit_stream.
    upper_uid = len(units) - 1
    for j in range(chunk_idx + 1, len(all_chunk_toks)):
        if all_chunk_toks[j]:
            if abs_pos < len(unit_stream):
                _, upper_uid, _ = unit_stream[abs_pos]
            break

    # Search for key in whitespace-normalised unit texts[lower_uid..upper_uid].
    # Only consider occurrences at or after unit_match_end[uid] (consecutive order).
    matches: list[tuple[int, int]] = []  # (unit_id, start_pos_in_norm_text)
    for uid in range(lower_uid, upper_uid + 1):
        norm_unit = _norm_ws(units[uid].get("text", ""))
        min_start = unit_match_end.get(uid, 0)
        search_from = 0
        while True:
            pos = norm_unit.find(key, search_from)
            if pos == -1:
                break
            if pos >= min_start:
                matches.append((uid, pos))
            search_from = pos + 1

    if not matches:
        raise AnnotationError(
            f"zero-token chunk: no occurrence in units {lower_uid}–{upper_uid} (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    matched_uids = {uid for uid, _ in matches}
    if len(matched_uids) > 1:
        raise AnnotationError(
            f"zero-token chunk: occurrence spans units {sorted(matched_uids)} (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    if len(matches) > 1:
        raise AnnotationError(
            f"zero-token chunk: duplicate occurrence in unit {matches[0][0]} (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    matched_uid, match_pos = matches[0]
    unit_match_end[matched_uid] = match_pos + len(key)
    return matched_uid, _unit_kind(units[matched_uid])


def annotate_units(
    manifest_chunks: list[dict],
    units: list[dict],
    *,
    section: str = "",
) -> list[dict]:
    """Return manifest_chunks annotated with 'unit_id' (int) and 'kind' (str).

    Aligns each manifest chunk to its source unit using absolute Cyrillic token
    indices (I1/I3) or text-anchor search for zero-Cyrillic-token chunks (I2′).
    Does not call build_chunks().

    Raises AnnotationError on:
      I1  — token stream mismatch between units and manifest (content or length)
      I2′ — zero-token chunk that is empty, unresolvable, duplicate, or cross-unit
      I3  — chunk spans multiple source units or units with conflicting kinds
    """
    # Build flat unit token stream: (token, unit_id, kind) per Cyrillic word.
    unit_stream: list[tuple[str, int, str]] = []
    for uid, unit in enumerate(units):
        kind = _unit_kind(unit)
        for tok in _tokens(unit.get("text", "")):
            unit_stream.append((tok, uid, kind))

    # Precompute token lists for all chunks (needed for I2′ lookahead).
    all_chunk_toks = [_tokens(c.get("text", "")) for c in manifest_chunks]

    # Tracks last match end position (in norm unit text) per unit for I2′ ordering.
    unit_match_end: dict[int, int] = {}

    annotated: list[dict] = []
    abs_pos = 0

    for i, chunk in enumerate(manifest_chunks):
        chunk_id = str(chunk.get("id", ""))
        toks = all_chunk_toks[i]

        if not toks:
            # I2′: resolve via text-anchor search
            uid, kind = _resolve_zero_token(
                chunk, i, all_chunk_toks, abs_pos,
                unit_stream, units, unit_match_end, section,
            )
            annotated.append({**chunk, "unit_id": uid, "kind": kind})
            # abs_pos is NOT advanced — zero-token chunks consume no token positions
            continue

        seen_units: set[int] = set()
        seen_kinds: set[str] = set()

        for local_k, tok in enumerate(toks):
            abs_idx = abs_pos + local_k
            if abs_idx >= len(unit_stream):
                raise AnnotationError(
                    "manifest token stream exceeds unit stream (I1)",
                    section=section,
                    chunk_id=chunk_id,
                    mismatch_idx=abs_idx,
                )
            unit_tok, uid, kind = unit_stream[abs_idx]
            if unit_tok != tok:
                raise AnnotationError(
                    f"token mismatch: manifest={tok!r} unit={unit_tok!r} (I1)",
                    section=section,
                    chunk_id=chunk_id,
                    mismatch_idx=abs_idx,
                )
            seen_units.add(uid)
            seen_kinds.add(kind)

        if len(seen_units) > 1:
            raise AnnotationError(
                f"chunk spans units {sorted(seen_units)} (I3)",
                section=section,
                chunk_id=chunk_id,
                mismatch_idx=abs_pos,
            )
        if len(seen_kinds) > 1:
            raise AnnotationError(
                f"chunk has conflicting kinds {sorted(seen_kinds)} (I3)",
                section=section,
                chunk_id=chunk_id,
                mismatch_idx=abs_pos,
            )

        abs_pos += len(toks)
        annotated.append({
            **chunk,
            "unit_id": next(iter(seen_units)),
            "kind": next(iter(seen_kinds)),
        })

    if abs_pos != len(unit_stream):
        raise AnnotationError(
            f"unit stream has {len(unit_stream)} tokens, manifest consumed {abs_pos} (I1)",
            section=section,
        )

    return annotated
