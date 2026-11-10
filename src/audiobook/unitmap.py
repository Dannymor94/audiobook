"""Recover source unit identity and chunk kind via Cyrillic token-index alignment.

Public API:
  annotate_units(manifest_chunks, units, *, section="") -> list[dict]
  find_exact_in_unit(key, unit_text, *, orig_lb, orig_ub) -> list[tuple[int, int]]
  AnnotationError
"""
from __future__ import annotations

import re
import unicodedata

_CYR = re.compile(r"[а-яёА-ЯЁ]+")
_WS = re.compile(r"\s+")
_TRAILING_TERM = re.compile(r"[.!?…]+$")
# M2 tolerant matching: T = {".", "…"} — only characters text_prep can append.
_M2_TERMINAL: frozenset[str] = frozenset((".", "…"))
# Characters that, when following an M2 match, disqualify it.
_PUNCT_AFTER_M2: frozenset[str] = frozenset((".", "!", "?", "…"))


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


def _m2_ok(unit_text: str, orig_e: int) -> bool:
    """True when an M2 match ending at orig_e is valid: at boundary or followed by whitespace.

    Rejects if followed by sentence punctuation [.!?…].
    """
    if orig_e >= len(unit_text):
        return True
    ch = unit_text[orig_e]
    if ch in _PUNCT_AFTER_M2:
        return False
    return ch.isspace()


def _combining_seqs(text: str) -> list[tuple[int, int]]:
    """Return (orig_start, orig_end) for each Unicode combining character sequence.

    Each sequence is a maximal run: a base character (combining class 0, or any
    character when at index 0 or following a class-0 char) followed by zero or more
    combining marks (combining class != 0).  Lone combiners at the start of a string
    form their own sequence.  Canonical reordering within a sequence is handled by
    applying NFC to the whole sequence, so all NFC chars it produces map to the same
    [orig_start, orig_end) span.
    """
    seqs: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        start = i
        i += 1
        while i < n and unicodedata.combining(text[i]) != 0:
            i += 1
        seqs.append((start, i))
    return seqs


def _build_offset_map(text: str) -> tuple[str, list[int], list[int]]:
    """NFC-normalize text and collapse whitespace, tracking original char offsets.

    Returns (norm, orig_start_map, orig_end_map):
      norm             — NFC text with str.split()-collapsed whitespace
      orig_start_map[i] — start index in original text for norm[i]; -1 for sep spaces
      orig_end_map[i]   — exclusive end index in original text for norm[i]; -1 for seps

    Uses str.split() whitespace semantics (handles NBSP, tabs, repeated whitespace).
    Handles decomposed Unicode and canonical combining-mark reordering via
    _combining_seqs: each combining character sequence is NFC-normalised as a unit,
    and every NFC codepoint it produces maps to the whole sequence's original span.
    This prevents zero-length or wrong spans caused by reordering (e.g. NFC of
    "à̕" = "à̕" where both NFC chars map to original span (0, 3)).
    """
    # Build nfc_to_orig: (orig_start, orig_end) in original text for each NFC codepoint.
    nfc_to_orig: list[tuple[int, int]] = []
    for orig_start, orig_end in _combining_seqs(text):
        seq_nfc = unicodedata.normalize("NFC", text[orig_start:orig_end])
        for _ in seq_nfc:
            nfc_to_orig.append((orig_start, orig_end))

    nfc = "".join(c for orig_s, orig_e in _combining_seqs(text)
                  for c in unicodedata.normalize("NFC", text[orig_s:orig_e]))

    # Collapse whitespace using isspace() (matches str.split() semantics: NBSP etc.).
    tokens: list[tuple[int, int]] = []  # (nfc_start, nfc_end) per non-ws token
    i, n = 0, len(nfc)
    while i < n:
        if nfc[i].isspace():
            i += 1
            continue
        j = i + 1
        while j < n and not nfc[j].isspace():
            j += 1
        tokens.append((i, j))
        i = j

    if not tokens:
        return "", [], []

    norm_chars: list[str] = []
    orig_start_map: list[int] = []
    orig_end_map: list[int] = []
    for k, (ts, te) in enumerate(tokens):
        for ci in range(ts, te):
            norm_chars.append(nfc[ci])
            os, oe = nfc_to_orig[ci]
            orig_start_map.append(os)
            orig_end_map.append(oe)
        if k < len(tokens) - 1:
            norm_chars.append(" ")
            orig_start_map.append(-1)
            orig_end_map.append(-1)

    return "".join(norm_chars), orig_start_map, orig_end_map


def find_exact_in_unit(
    key: str,
    unit_text: str,
    *,
    orig_lb: int = 0,
    orig_ub: int | None = None,
) -> list[tuple[int, int]]:
    """Find all NFC, whitespace-collapsed exact occurrences of key in unit_text.

    Returns list of (orig_start, orig_end) in original unit_text coordinates
    (orig_end is exclusive).  Uses str.split() whitespace semantics (handles NBSP,
    repeated whitespace) and Unicode NFC (handles decomposed input).

    orig_lb: minimum acceptable orig_start (inclusive).
    orig_ub: maximum acceptable orig_end (exclusive); None = len(unit_text).

    Caller ensures single-unit scope; this function never crosses unit boundaries.
    """
    if orig_ub is None:
        orig_ub = len(unit_text)

    norm_key, _, _ = _build_offset_map(key)
    if not norm_key:
        return []

    norm_src, src_start_map, src_end_map = _build_offset_map(unit_text)
    if not norm_src:
        return []

    results: list[tuple[int, int]] = []
    pos = 0
    while True:
        idx = norm_src.find(norm_key, pos)
        if idx == -1:
            break
        end_idx = idx + len(norm_key) - 1  # inclusive last char index in norm

        orig_s = src_start_map[idx]
        orig_e = src_end_map[end_idx]

        # Reject separator spaces (-1) and zero-length spans (combining-mark reordering
        # can produce NFC chars whose sequence's orig span has already been fully consumed).
        if orig_s != -1 and orig_e != -1 and orig_s < orig_e and orig_s >= orig_lb and orig_e <= orig_ub:
            results.append((orig_s, orig_e))

        pos = idx + 1

    return results


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
    manifest_chunks: list[dict],
    all_chunk_toks: list[list[str]],
    abs_pos: int,
    unit_stream: list[tuple[str, int, str, int, int]],
    units: list[dict],
    unit_match_end: dict[int, int],
    consumed_end: dict[int, int],
    global_zero_pos: tuple[int, int],
    section: str,
) -> tuple[int, str, str]:
    """I2′: resolve a zero-Cyrillic-token chunk via M1 (exact) or M2 (tolerant) matching.

    M1: NFC + ws-collapsed exact match of the full normalized chunk text.
    M2: permitted only when the normalized chunk ends with a character in T = {".", "…"}.
        Removes exactly one terminal char; the remaining key must contain a letter or digit.
        Source occurrence must end at unit boundary or be followed by whitespace, and must
        NOT be followed by sentence punctuation [.!?…].

    All M1 and M2 candidates are gathered across the anchor interval bounded by:
      - consumed_end: excludes text claimed by prior Cyrillic chunks
      - unit_match_end: enforces per-unit ordering of zero-token matches (original coords)
      - global_zero_pos: enforces global monotonic source order across units
      - upper_char_start: stays before the next Cyrillic anchor token

    Accepts only when the union of all candidate positions is exactly one distinct
    (unit_id, orig_start, orig_end) triple.

    Returns (unit_id, kind, match) where match is "exact" or "tolerant:<codepoint>".
    Raises AnnotationError on failure — no manuscript text in error messages.
    """
    chunk_id = str(chunk.get("id", ""))
    raw_text = chunk.get("text", "")

    if not raw_text.strip():
        raise AnnotationError(
            "empty/whitespace-only chunk (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    norm_key, _, _ = _build_offset_map(raw_text)
    if not norm_key:
        raise AnnotationError(
            "chunk text reduces to empty after normalization (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    # Lower anchor: unit owning the last consumed Cyrillic token.
    lower_uid = 0
    if abs_pos > 0:
        _, lower_uid, _, _, _ = unit_stream[abs_pos - 1]

    # Upper anchor: unit owning the first token of the next Cyrillic chunk.
    # abs_pos is not advanced for zero-token chunks, so unit_stream[abs_pos] is always next.
    upper_uid = len(units) - 1
    upper_char_start: int | None = None
    next_cyr_chunk_idx: int | None = None
    for j in range(chunk_idx + 1, len(all_chunk_toks)):
        if all_chunk_toks[j]:
            if abs_pos < len(unit_stream):
                _, upper_uid, _, upper_char_start, _ = unit_stream[abs_pos]
            next_cyr_chunk_idx = j
            break

    # Prefix-adjusted upper bound (fix 6C7c): if the next Cyrillic chunk has a
    # non-Cyrillic prefix, its source span starts before upper_char_start.
    # Zero-token match must end strictly before the prefix, not just before the
    # Cyrillic anchor.  Fail closed if the prefix cannot be located.
    prefix_ub: int | None = upper_char_start
    if upper_char_start is not None and next_cyr_chunk_idx is not None:
        next_raw = manifest_chunks[next_cyr_chunk_idx].get("text", "")
        cyr_in_next = list(_CYR.finditer(next_raw))
        if cyr_in_next:
            prefix = next_raw[:cyr_in_next[0].start()]
            norm_prefix, _, _ = _build_offset_map(prefix)
            if norm_prefix:
                unit_text = units[upper_uid].get("text", "")
                p_matches = find_exact_in_unit(prefix, unit_text, orig_ub=upper_char_start)
                if not p_matches:
                    raise AnnotationError(
                        "zero-token chunk: next chunk's non-Cyrillic prefix not found "
                        "in unit before its Cyrillic content (I2′)",
                        section=section,
                        chunk_id=chunk_id,
                    )
                # Rightmost match = closest to the Cyrillic anchor = actual prefix position.
                prefix_ub = p_matches[-1][0]

    global_uid, global_end = global_zero_pos

    # M2 key: strip exactly one terminal char in T, keep only if alphanumeric content remains.
    m2_key: str | None = None
    m2_terminal_cp: int = 0
    if norm_key[-1] in _M2_TERMINAL and len(norm_key) > 1:
        candidate = norm_key[:-1]
        if any(c.isalpha() or c.isdigit() for c in candidate):
            m2_key = candidate
            m2_terminal_cp = ord(norm_key[-1])

    # Gather M1 and M2 candidates: (uid, orig_start, orig_end, match_str).
    # All bounds are in original text coordinates.
    candidates: list[tuple[int, int, int, str]] = []
    for uid in range(lower_uid, upper_uid + 1):
        unit_text = units[uid].get("text", "")

        if uid == lower_uid:
            lb = max(consumed_end.get(uid, 0), unit_match_end.get(uid, 0))
        else:
            lb = unit_match_end.get(uid, 0)

        ub: int | None = prefix_ub if (uid == upper_uid and prefix_ub is not None) else None

        # Enforce global monotonic source order across units.
        if uid < global_uid:
            continue
        if uid == global_uid:
            lb = max(lb, global_end)

        for orig_s, orig_e in find_exact_in_unit(norm_key, unit_text, orig_lb=lb, orig_ub=ub):
            candidates.append((uid, orig_s, orig_e, "exact"))

        if m2_key is not None:
            for orig_s, orig_e in find_exact_in_unit(m2_key, unit_text, orig_lb=lb, orig_ub=ub):
                if _m2_ok(unit_text, orig_e):
                    candidates.append((uid, orig_s, orig_e, f"tolerant:{m2_terminal_cp}"))

    distinct: set[tuple[int, int, int]] = {(u, s, e) for u, s, e, _ in candidates}

    if not distinct:
        raise AnnotationError(
            f"zero-token chunk: no M1/M2 match in units {lower_uid}–{upper_uid} (I2′)",
            section=section,
            chunk_id=chunk_id,
        )
    if len(distinct) > 1:
        raise AnnotationError(
            f"zero-token chunk: {len(distinct)} ambiguous positions (I2′)",
            section=section,
            chunk_id=chunk_id,
        )

    uid_m, orig_s_m, orig_e_m = next(iter(distinct))
    match_types = {mt for u, s, e, mt in candidates if u == uid_m and s == orig_s_m and e == orig_e_m}
    match_str = "exact" if "exact" in match_types else next(iter(match_types))

    unit_match_end[uid_m] = orig_e_m
    return uid_m, _unit_kind(units[uid_m]), match_str


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
    # Build flat unit token stream with char spans: (token, unit_id, kind, char_start, char_end).
    unit_stream: list[tuple[str, int, str, int, int]] = []
    for uid, unit in enumerate(units):
        kind = _unit_kind(unit)
        for m in _CYR.finditer(unit.get("text", "")):
            tok = m.group().lower().replace("ё", "е")
            unit_stream.append((tok, uid, kind, m.start(), m.end()))

    # Precompute token lists for all chunks (needed for I2′ lookahead).
    all_chunk_toks = [_tokens(c.get("text", "")) for c in manifest_chunks]

    # unit_match_end: orig_end of last I2′ match per unit (original text coordinates).
    unit_match_end: dict[int, int] = {}
    # consumed_end: char end of each unit's last Cyrillic chunk including non-Cyrillic suffix,
    # used to restrict I2′ search to unconsumed source text.
    consumed_end: dict[int, int] = {}
    # global_zero_pos: (unit_id, char_end) of the last resolved zero-token chunk.
    # Enforces that consecutive zero-token chunks map to monotonically increasing source positions
    # across unit boundaries (within-unit ordering is also covered by unit_match_end).
    global_zero_pos: tuple[int, int] = (-1, -1)

    annotated: list[dict] = []
    abs_pos = 0

    for i, chunk in enumerate(manifest_chunks):
        chunk_id = str(chunk.get("id", ""))
        toks = all_chunk_toks[i]

        if not toks:
            # I2′: resolve via M1/M2 matching
            uid, kind, match = _resolve_zero_token(
                chunk, i, manifest_chunks, all_chunk_toks, abs_pos,
                unit_stream, units, unit_match_end, consumed_end,
                global_zero_pos, section,
            )
            annotated.append({**chunk, "unit_id": uid, "kind": kind, "match": match})
            global_zero_pos = (uid, unit_match_end[uid])
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
            unit_tok, uid, kind, _, _ = unit_stream[abs_idx]
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

        # Track consumed_end: advance past any non-Cyrillic suffix of this chunk.
        # Uses NFC+ws-aware matching (fix 6C7b) so double-space / NBSP / decomposed
        # Unicode in the chunk suffix correctly block the same span in the unit text.
        _, uid_last, _, _, char_end_last = unit_stream[abs_pos - 1]
        chunk_raw = chunk.get("text", "")
        last_cyr = list(_CYR.finditer(chunk_raw))
        suffix = chunk_raw[last_cyr[-1].end():] if last_cyr else ""
        if suffix:
            unit_text = units[uid_last].get("text", "")
            norm_suffix, _, _ = _build_offset_map(suffix)
            if norm_suffix:
                matches = find_exact_in_unit(suffix, unit_text, orig_lb=char_end_last)
                if not matches:
                    raise AnnotationError(
                        "chunk non-Cyrillic suffix not found in unit after Cyrillic anchor; "
                        "cannot establish consumed end",
                        section=section,
                        chunk_id=chunk_id,
                    )
                consumed_end[uid_last] = matches[0][1]  # first = closest to anchor
            else:
                consumed_end[uid_last] = char_end_last
        else:
            consumed_end[uid_last] = char_end_last

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
