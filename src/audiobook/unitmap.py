"""Recover source unit identity and chunk kind via Cyrillic token-index alignment.

Public API:
  Atom, ChunkSpan                                      — data structures
  atoms(unit_text, unit_id) -> list[Atom]              — non-whitespace atom extractor
  validate_gates(chunks, units, *, section) -> list[AnnotationError]
  check_gates(chunks, units, *, section) -> None       — raises on first gate error
  annotate_units(manifest_chunks, units, *, section="") -> list[dict]
  find_exact_in_unit(key, unit_text, *, orig_lb, orig_ub) -> list[tuple[int, int]]
  AnnotationError
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_CYR = re.compile(r"[а-яёА-ЯЁ]+")
_WS = re.compile(r"\s+")
_TRAILING_TERM = re.compile(r"[.!?…]+$")
_INNER_PARA = re.compile(r"\n[ \t]*\n")
# M2 tolerant matching: T = {".", "…"} — only characters text_prep can append.
_M2_TERMINAL: frozenset[str] = frozenset((".", "…"))
# Characters that, when following an M2 match, disqualify it.
_PUNCT_AFTER_M2: frozenset[str] = frozenset((".", "!", "?", "…"))


@dataclass(frozen=True)
class Atom:
    """Non-whitespace token with its position in the source unit text."""
    text: str
    unit_id: int
    start: int
    end: int


@dataclass(frozen=True)
class ChunkSpan:
    """Architect-approved view of a mapped chunk; populated by map_chunks() (future).

    Fields:
      chunk_id   — manifest chunk id string (e.g. "0001")
      atom_start — index of first atom in the section-level atom list (inclusive)
      atom_end   — index past last atom (exclusive); atom_end == atom_start → zero-atom chunk
      spans      — per-atom (start, end) offsets in the source unit text, in order
      unit_ids   — set of source unit indices this chunk spans
      kind       — chunk kind string ("text", "heading", "stack", …)
      end_modes  — set of active end-mode flags (e.g. {"open_end"}), or None
    """
    chunk_id: str
    atom_start: int
    atom_end: int
    spans: tuple[tuple[int, int], ...]
    unit_ids: frozenset[int]
    kind: str
    end_modes: frozenset[str] | None


class AnnotationError(Exception):
    """Raised when manifest chunks cannot be reliably mapped to source units.

    Attributes:
        code        — structured error code (e.g. NOT_NFC, MANIFEST_ORDER) or
                      human-readable failure description for legacy callers
        reason      — alias for code (backward compat)
        section     — section slug (empty if caller did not pass it)
        chunk_id    — manifest chunk id (empty if unavailable)
        detail      — additional structured detail (empty if unused)
        mismatch_idx — absolute token index of first mismatch (-1 if N/A)
    """

    def __init__(
        self,
        code: str,
        *,
        section: str = "",
        chunk_id: str = "",
        detail: str = "",
        mismatch_idx: int = -1,
    ) -> None:
        self.code = code
        self.reason = code  # backward-compat alias
        self.section = section
        self.chunk_id = chunk_id
        self.detail = detail
        self.mismatch_idx = mismatch_idx
        parts = []
        if section:
            parts.append(f"section={section!r}")
        if chunk_id:
            parts.append(f"chunk={chunk_id!r}")
        if mismatch_idx >= 0:
            parts.append(f"tok={mismatch_idx}")
        if detail:
            parts.append(f"detail={detail!r}")
        ctx = f" ({', '.join(parts)})" if parts else ""
        super().__init__(f"unitmap: {code}{ctx}")


def atoms(unit_text: str, unit_id: int) -> list[Atom]:
    """Return one Atom per non-whitespace token with its original offsets."""
    return [Atom(m.group(), unit_id, m.start(), m.end()) for m in re.finditer(r"\S+", unit_text)]


def validate_gates(
    manifest_chunks: list[dict],
    units: list[dict],
    *,
    section: str = "",
) -> list[AnnotationError]:
    """Run pre-mapping gates; return list of AnnotationErrors (empty = all pass).

    Gates (in order):
      NOT_NFC        — unit or chunk text is not NFC-normalized
      UNIT_INNER_PARA — unit text contains a blank line (\\n\\s*\\n)
      MANIFEST_ORDER  — n not sequential from 1, id != f"{n:04d}", or duplicate id
      EMPTY_CHUNK     — chunk has no non-whitespace atoms
    """
    errors: list[AnnotationError] = []

    for uid, unit in enumerate(units):
        text = unit.get("text", "")
        if unicodedata.normalize("NFC", text) != text:
            errors.append(AnnotationError("NOT_NFC", section=section, chunk_id=str(uid)))
            continue  # inner-para check on non-NFC text is unreliable
        if _INNER_PARA.search(text):
            errors.append(AnnotationError("UNIT_INNER_PARA", section=section, chunk_id=str(uid)))

    seen_ids: set[str] = set()
    for i, chunk in enumerate(manifest_chunks):
        chunk_id = str(chunk.get("id", ""))
        n = chunk.get("n")
        expected_n = i + 1
        if n != expected_n or chunk_id != f"{expected_n:04d}" or chunk_id in seen_ids:
            errors.append(AnnotationError("MANIFEST_ORDER", section=section, chunk_id=chunk_id))
        seen_ids.add(chunk_id)

    for chunk in manifest_chunks:
        chunk_id = str(chunk.get("id", ""))
        text = chunk.get("text", "")
        if unicodedata.normalize("NFC", text) != text:
            errors.append(AnnotationError("NOT_NFC", section=section, chunk_id=chunk_id))
            continue
        if not atoms(text, 0):
            errors.append(AnnotationError("EMPTY_CHUNK", section=section, chunk_id=chunk_id))

    return errors


def check_gates(
    manifest_chunks: list[dict],
    units: list[dict],
    *,
    section: str = "",
) -> None:
    """Run pre-mapping gates and raise AnnotationError on the first failure.

    Guarantees that cursor processing never starts on invalid input.
    """
    errors = validate_gates(manifest_chunks, units, section=section)
    if errors:
        raise errors[0]


def map_chunks(
    units: list[dict],
    chunks: list[dict],
    *,
    section: str = "",
) -> list[ChunkSpan]:
    """Map manifest chunks to source atoms, returning one ChunkSpan per chunk.

    Algorithm: build an ordered atom stream from all units, then advance a
    single global cursor by each chunk's atom count.  Comparison is exact
    codepoint equality — no normalization, no Cyrillic filtering.

    Raises AnnotationError with codes:
      ATOM_MISMATCH    — chunk atom text ≠ source atom text at cursor position
      STREAM_EXHAUSTED — chunk needs atoms past the end of the source stream
      TRAILING_SOURCE  — source atoms remain after all chunks are consumed
      KIND_AMBIGUOUS   — chunk spans atoms from units with different kinds
      (gate codes via check_gates before cursor processing)
    """
    check_gates(chunks, units, section=section)

    # Build ordered source atom stream from all units.
    source_atoms: list[Atom] = []
    for uid, unit in enumerate(units):
        source_atoms.extend(atoms(unit.get("text", ""), uid))

    unit_kinds = [_unit_kind(u) for u in units]

    result: list[ChunkSpan] = []
    cursor = 0

    for chunk in chunks:
        chunk_id = str(chunk.get("id", ""))
        chunk_atoms = atoms(chunk.get("text", ""), -1)
        n = len(chunk_atoms)

        if cursor + n > len(source_atoms):
            raise AnnotationError("STREAM_EXHAUSTED", section=section, chunk_id=chunk_id)

        seen_unit_ids: set[int] = set()
        seen_kinds: set[str] = set()
        spans_list: list[tuple[int, int]] = []

        for j in range(n):
            src = source_atoms[cursor + j]
            if src.text != chunk_atoms[j].text:
                raise AnnotationError("ATOM_MISMATCH", section=section, chunk_id=chunk_id)
            seen_unit_ids.add(src.unit_id)
            seen_kinds.add(unit_kinds[src.unit_id])
            spans_list.append((src.start, src.end))

        if len(seen_kinds) > 1:
            raise AnnotationError("KIND_AMBIGUOUS", section=section, chunk_id=chunk_id)

        result.append(ChunkSpan(
            chunk_id=chunk_id,
            atom_start=cursor,
            atom_end=cursor + n,
            spans=tuple(spans_list),
            unit_ids=frozenset(seen_unit_ids),
            kind=next(iter(seen_kinds)),
            end_modes=None,
        ))
        cursor += n

    if cursor < len(source_atoms):
        raise AnnotationError("TRAILING_SOURCE", section=section)

    return result


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

    Each sequence is a base character (combining class 0) followed by zero or more
    combining marks (class != 0).  Lone combiners at index 0 form their own sequence.
    NFC is applied per-sequence so all resulting codepoints map to the same orig span,
    correctly handling canonical combining-mark reordering.
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
      norm              -- NFC text with str.split()-collapsed whitespace
      orig_start_map[i] -- start index in original text for norm[i]; -1 for sep spaces
      orig_end_map[i]   -- exclusive end index in original text for norm[i]; -1 for seps

    Two-stage normalization:
    1. Per-combining-sequence NFC: groups each base char + its combining marks and
       NFC-normalizes as a unit, mapping all resulting codepoints to the whole
       sequence span.  Handles canonical combining-mark reordering correctly.
    2. Cross-sequence Hangul Jamo composition: Jamo (all ccc=0) are separate
       combining sequences but compose via NFC into precomposed syllable blocks.
       A second NFC pass detects and merges these, unioning the orig spans.
    """
    # Stage 1: per-combining-sequence NFC.
    nfc_to_orig: list[tuple[int, int]] = []
    for orig_start, orig_end in _combining_seqs(text):
        seq_nfc = unicodedata.normalize("NFC", text[orig_start:orig_end])
        for _ in seq_nfc:
            nfc_to_orig.append((orig_start, orig_end))

    nfc = "".join(c for orig_s, orig_e in _combining_seqs(text)
                  for c in unicodedata.normalize("NFC", text[orig_s:orig_e]))

    # Stage 2: cross-sequence Hangul Jamo composition.
    # Per-sequence NFC leaves Jamo uncomposed; full NFC composes them.
    nfc_full = unicodedata.normalize("NFC", nfc)
    if nfc_full != nfc:
        new_nfc_to_orig: list[tuple[int, int]] = []
        nfc_i = 0
        for full_ch in nfc_full:
            for end in range(nfc_i + 1, len(nfc) + 1):
                if unicodedata.normalize("NFC", nfc[nfc_i:end]) == full_ch:
                    span = (
                        min(nfc_to_orig[j][0] for j in range(nfc_i, end)),
                        max(nfc_to_orig[j][1] for j in range(nfc_i, end)),
                    )
                    new_nfc_to_orig.append(span)
                    nfc_i = end
                    break
            else:
                new_nfc_to_orig.append(nfc_to_orig[nfc_i])
                nfc_i += 1
        nfc = nfc_full
        nfc_to_orig = new_nfc_to_orig

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

def _find_normalized(
    key: str,
    unit_text: str,
    *,
    orig_lb: int,
    orig_ub: int,
) -> list[tuple[int, int, int]]:
    """Return (norm_pos, orig_start, orig_end) for each valid match of key in unit_text.

    norm_pos is the start index in the NFC+ws-collapsed unit text.  Two matches at
    different norm_pos are distinct occurrences even if their source spans coincide
    (e.g. two identical combining marks inside the same combining sequence).
    """
    norm_key, _, _ = _build_offset_map(key)
    if not norm_key:
        return []
    norm_src, src_start_map, src_end_map = _build_offset_map(unit_text)
    if not norm_src:
        return []

    results: list[tuple[int, int, int]] = []
    pos = 0
    while True:
        idx = norm_src.find(norm_key, pos)
        if idx == -1:
            break
        end_idx = idx + len(norm_key) - 1  # inclusive last char index in norm
        orig_s = src_start_map[idx]
        orig_e = src_end_map[end_idx]
        # Reject separator spaces (-1) and zero-length spans.
        if orig_s != -1 and orig_e != -1 and orig_s < orig_e and orig_s >= orig_lb and orig_e <= orig_ub:
            results.append((idx, orig_s, orig_e))
        pos = idx + 1

    return results


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
    return [(s, e) for _, s, e in _find_normalized(key, unit_text, orig_lb=orig_lb, orig_ub=orig_ub)]


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

    # Gather M1 and M2 candidates: (uid, orig_start, orig_end, match_str, norm_pos).
    # norm_pos is the index in the unit's NFC+ws-collapsed string — used for deduplication.
    # Two matches at different norm_pos are distinct occurrences even when their source
    # spans coincide (e.g. two identical combining marks in one combining sequence).
    candidates: list[tuple[int, int, int, str, int]] = []
    for uid in range(lower_uid, upper_uid + 1):
        unit_text = units[uid].get("text", "")

        if uid == lower_uid:
            lb = max(consumed_end.get(uid, 0), unit_match_end.get(uid, 0))
        else:
            lb = unit_match_end.get(uid, 0)

        ub: int = prefix_ub if (uid == upper_uid and prefix_ub is not None) else len(unit_text)

        # Enforce global monotonic source order across units.
        if uid < global_uid:
            continue
        if uid == global_uid:
            lb = max(lb, global_end)

        for np, orig_s, orig_e in _find_normalized(norm_key, unit_text, orig_lb=lb, orig_ub=ub):
            candidates.append((uid, orig_s, orig_e, "exact", np))

        if m2_key is not None:
            for np, orig_s, orig_e in _find_normalized(m2_key, unit_text, orig_lb=lb, orig_ub=ub):
                if _m2_ok(unit_text, orig_e):
                    candidates.append((uid, orig_s, orig_e, f"tolerant:{m2_terminal_cp}", np))

    # Deduplicate by (uid, norm_pos): same normalized position = same occurrence,
    # regardless of whether M1 and M2 happen to share source spans.
    distinct: set[tuple[int, int]] = {(u, np) for u, _, _, _, np in candidates}

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

    uid_m, norm_pos_m = next(iter(distinct))
    winning = [(orig_s, orig_e, mt) for u, orig_s, orig_e, mt, np in candidates
               if u == uid_m and np == norm_pos_m]
    match_types = {mt for _, _, mt in winning}
    match_str = "exact" if "exact" in match_types else next(iter(match_types))
    # Prefer M1 orig_e (includes terminal char); fall back to first candidate's orig_e.
    orig_e_m = next((e for _, e, mt in winning if mt == "exact"), winning[0][1])

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

        chunk_raw = chunk.get("text", "")
        cyr_in_chunk = list(_CYR.finditer(chunk_raw))

        # Prefix contiguity check (6C9b): prefix must be immediately before its anchor.
        # Search prefix+anchor as one key; the match must end at the anchor's char_end.
        if cyr_in_chunk:
            prefix = chunk_raw[:cyr_in_chunk[0].start()]
            norm_prefix, _, _ = _build_offset_map(prefix)
            if norm_prefix:
                _, _first_uid, _, _first_cs, first_char_end = unit_stream[abs_pos]
                unit_text_p = units[_first_uid].get("text", "")
                p_matches = find_exact_in_unit(
                    prefix + cyr_in_chunk[0].group(), unit_text_p, orig_ub=first_char_end
                )
                if not p_matches or p_matches[-1][1] != first_char_end:
                    raise AnnotationError(
                        "chunk non-Cyrillic prefix not found contiguously before its "
                        "Cyrillic anchor; cannot establish alignment",
                        section=section,
                        chunk_id=chunk_id,
                    )

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
        # Fix 6C9a: search anchor+suffix as one contiguous key so a later occurrence
        # of the same suffix text (separated by other Cyrillic content) is never
        # mistaken for the adjacent one.
        _, uid_last, _, char_start_last, char_end_last = unit_stream[abs_pos - 1]
        last_cyr = cyr_in_chunk  # reuse — already computed above
        suffix = chunk_raw[last_cyr[-1].end():] if last_cyr else ""
        if suffix:
            unit_text = units[uid_last].get("text", "")
            norm_suffix, _, _ = _build_offset_map(suffix)
            if norm_suffix:
                anchor_plus_suffix = last_cyr[-1].group() + suffix
                matches = find_exact_in_unit(anchor_plus_suffix, unit_text, orig_lb=char_start_last)
                if not matches or matches[0][0] != char_start_last:
                    raise AnnotationError(
                        "chunk non-Cyrillic suffix not found contiguously after its "
                        "Cyrillic anchor; cannot establish consumed end",
                        section=section,
                        chunk_id=chunk_id,
                    )
                consumed_end[uid_last] = matches[0][1]
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
