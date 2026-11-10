"""Recover source unit identity and chunk kind via Cyrillic token-index alignment.

Public API:
  annotate_units(manifest_chunks, units, *, section="") -> list[dict]
  AnnotationError
"""
from __future__ import annotations

import re

_CYR = re.compile(r"[а-яёА-ЯЁ]+")


def _tokens(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in _CYR.findall(text)]


def _unit_kind(unit: dict) -> str:
    t = unit.get("type", "")
    if t == "heading":
        return "heading"
    if t == "stack":
        return "stack"
    return "text"


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


def annotate_units(
    manifest_chunks: list[dict],
    units: list[dict],
    *,
    section: str = "",
) -> list[dict]:
    """Return manifest_chunks annotated with 'unit_id' (int) and 'kind' (str).

    Aligns each manifest chunk to its source unit using absolute Cyrillic token
    indices.  Does not call build_chunks().

    Raises AnnotationError on:
      I1 — token stream mismatch between units and manifest (content or length)
      I2 — manifest chunk with zero Cyrillic tokens
      I3 — chunk spans multiple source units or units with conflicting kinds
    """
    # Build flat unit token stream: one (token, unit_id, kind) per Cyrillic word.
    unit_stream: list[tuple[str, int, str]] = []
    for uid, unit in enumerate(units):
        kind = _unit_kind(unit)
        for tok in _tokens(unit.get("text", "")):
            unit_stream.append((tok, uid, kind))

    annotated: list[dict] = []
    abs_pos = 0

    for chunk in manifest_chunks:
        chunk_id = str(chunk.get("id", ""))
        chunk_toks = _tokens(chunk.get("text", ""))

        if not chunk_toks:
            raise AnnotationError("zero-token chunk (I2)", section=section, chunk_id=chunk_id)

        seen_units: set[int] = set()
        seen_kinds: set[str] = set()

        for local_k, tok in enumerate(chunk_toks):
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

        abs_pos += len(chunk_toks)
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
