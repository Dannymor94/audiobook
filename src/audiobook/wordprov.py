"""Word provenance: source-to-SU alignment, coordinates, fingerprints.

T15-7.3: WordOcc (35 fields), source_fp, manifest_fp, gold_identity,
U+0301 guard, TSV serialisation, and process_section_occs.
No synthesis, no model loading, no manifest writes.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, fields as dc_fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audiobook.unitmap import SectionMap
    from audiobook.sutrace import SUTrace

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
TOKENIZER_VERSION = "t15/1"
MANIFEST_FP_FIELDS: tuple[str, ...] = (
    "n", "id", "text", "pause_after_ms", "open_end", "leadin"
)
_CANONICAL_KW: dict = dict(sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _canonical_hash(obj) -> str:
    return _sha256(json.dumps(obj, **_CANONICAL_KW).encode("utf-8"))

def _fold(s: str) -> str:
    return s.lower().replace("ё", "е")

def _sha256_str(s: str) -> str:
    return _sha256(s.encode("utf-8"))


# ---------------------------------------------------------------------------
# WordOcc — 35 fields per ADR §6
# ---------------------------------------------------------------------------

@dataclass
class WordOcc:
    source_key: str           # 1
    section: str              # 2
    unit_id: str              # 3
    unit_token_index: int     # 4
    norm_start: int           # 5
    norm_end: int             # 6
    form_source: str          # 7
    chunk_n: int              # 8
    chunk_id: str             # 9
    chunk_word_index: int     # 10
    atom_index: int           # 11
    atom_char_start: int      # 12
    atom_char_end: int        # 13
    ana_start: int            # 14
    ana_end: int              # 15
    form_analysis: str        # 16
    su_chunk_id: str | None   # 17
    su_fragment: int | None   # 18
    su_token_index: int | None  # 19
    form_synth: str | None    # 20
    alignment_status: str     # 21
    f1_rule: str | None = None
    f1_phrase: bool = False
    f1_flag: str = "none"
    f2_approval: str = "none"
    f2_vowel: int | None = None
    f3_verified: bool = False
    f5_vowel: int | None = None
    f5_status: str = "none"
    f6_vowel: int | None = None
    f6_status: str = "not_run"
    expected_source: str = "none"
    expected_vowel: int | None = None
    status: str = "unresolved"
    reason: str = "ruaccent_not_run"


# ---------------------------------------------------------------------------
# TSV serialisation
# ---------------------------------------------------------------------------

_FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in dc_fields(WordOcc))
_INT_FIELDS = frozenset(
    "unit_token_index norm_start norm_end chunk_n chunk_word_index "
    "atom_index atom_char_start atom_char_end ana_start ana_end".split()
)
_NULLABLE_INT_FIELDS = frozenset(
    "su_fragment su_token_index f2_vowel f5_vowel f6_vowel expected_vowel".split()
)
_BOOL_FIELDS = frozenset("f1_phrase f3_verified".split())
_NULLABLE_STR_FIELDS = frozenset("f1_rule su_chunk_id form_synth".split())


def tsv_header() -> str:
    return "\t".join(_FIELD_NAMES)


_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)", re.ASCII)
_ENUM_FIELDS = {
    "alignment_status": frozenset("aligned prep_token_mismatch fragment_mismatch trace_unsupported trace_mismatch".split()),
    "f1_flag": frozenset(("none", "span_ambiguous")),
    "f2_approval": frozenset(("approved", "unknown", "none")),
    "f5_status": frozenset(("none",)),
    "f6_status": frozenset("resolved no_stress multi_stress invalid_mark tokenization_mismatch not_run".split()),
    "expected_source": frozenset("decision source_mark conflict ruaccent none".split()),
    "status": frozenset(("ok", "covered_by_override", "unresolved")),
}
_UNRESOLVED_REASONS = frozenset(
    "prep_token_mismatch fragment_mismatch trace_unsupported trace_mismatch "
    "override_span_ambiguous conflict no_stress multi_stress invalid_mark "
    "tokenization_mismatch ruaccent_not_run".split()
)
_INFO_REASONS = ("", "ruaccent_disagreement", "verified_disagreement",
                 "ruaccent_disagreement;verified_disagreement")


def _invalid_tsv():
    from audiobook.unitmap import AnnotationError
    raise AnnotationError("TSV_INVALID") from None


def _validate_cells(cells: list[str]) -> dict:
    """Shared complete wire grammar. Diagnostics never retain cell values."""
    from audiobook.unitmap import _section_violation
    if len(cells) != len(_FIELD_NAMES):
        _invalid_tsv()
    result = {}
    for name, raw in zip(_FIELD_NAMES, cells):
        if type(raw) is not str:
            _invalid_tsv()
        # UTF-8 scalar text; no separators, control characters or surrogates.
        if any(unicodedata.category(c) in ("Cc", "Cs", "Zl", "Zp") for c in raw):
            _invalid_tsv()
        nullable = name in _NULLABLE_INT_FIELDS or name in _NULLABLE_STR_FIELDS
        if not raw and not nullable and name != "reason":
            _invalid_tsv()
        if name in _BOOL_FIELDS:
            if raw not in ("0", "1"):
                _invalid_tsv()
            result[name] = raw == "1"
        elif name in _INT_FIELDS or name in _NULLABLE_INT_FIELDS:
            if raw == "" and nullable:
                result[name] = None
            else:
                if not _DECIMAL.fullmatch(raw):
                    _invalid_tsv()
                try:
                    result[name] = int(raw)
                except ValueError:
                    _invalid_tsv()
        elif name in _NULLABLE_STR_FIELDS:
            result[name] = raw or None
        else:
            if name in _ENUM_FIELDS and raw not in _ENUM_FIELDS[name]:
                _invalid_tsv()
            result[name] = raw
    if _section_violation(result["section"]) is not None:
        _invalid_tsv()
    if not _DECIMAL.fullmatch(result["unit_id"]):
        _invalid_tsv()
    if result["source_key"] != f'{result["section"]}|{result["unit_id"]}|{result["unit_token_index"]}':
        _invalid_tsv()
    status, reason = result["status"], result["reason"]
    if ((status == "unresolved" and reason not in _UNRESOLVED_REASONS)
            or (status == "ok" and reason not in _INFO_REASONS)
            or (status == "covered_by_override" and reason != "")):
        _invalid_tsv()
    return result


def to_tsv_row(occ: WordOcc) -> str:
    cells = []
    for name in _FIELD_NAMES:
        value = getattr(occ, name)
        if value is None:
            if name not in _NULLABLE_INT_FIELDS and name not in _NULLABLE_STR_FIELDS:
                _invalid_tsv()
            cells.append("")
        elif name in _BOOL_FIELDS:
            if type(value) is not bool:
                _invalid_tsv()
            cells.append("1" if value else "0")
        elif name in _INT_FIELDS or name in _NULLABLE_INT_FIELDS:
            if type(value) is not int or value < 0:
                _invalid_tsv()
            cells.append(str(value))
        else:
            if type(value) is not str:
                _invalid_tsv()
            if name in _NULLABLE_STR_FIELDS and value == "":
                _invalid_tsv()  # Empty wire strings mean null, never empty str.
            cells.append(value)
    _validate_cells(cells)
    return "\t".join(cells)


def from_tsv_row(cells: list[str]) -> WordOcc:
    return WordOcc(**_validate_cells(cells))


def serialize_tsv(occs: list[WordOcc]) -> str:
    """Canonical documents always end in exactly one LF, including header-only."""
    _validate_order(occs)
    return "\n".join([tsv_header()] + [to_tsv_row(o) for o in occs]) + "\n"


def _validate_order(occs: list[WordOcc]) -> None:
    previous = None
    for occ in occs:
        to_tsv_row(occ)
        key = (occ.section, occ.chunk_n, occ.chunk_word_index)
        if previous is not None and key <= previous:
            _invalid_tsv()
        previous = key


def parse_tsv(text: str) -> list[WordOcc]:
    """Accept only canonical LF-terminated documents; no ignored blank rows."""
    if type(text) is not str or not text.endswith("\n"):
        _invalid_tsv()
    lines = text[:-1].split("\n")
    if not lines or lines[0] != tsv_header():
        _invalid_tsv()
    occs = [from_tsv_row(line.split("\t")) for line in lines[1:]]
    _validate_order(occs)
    return occs


def serialize_occ(occ: WordOcc) -> str:
    """Alias for to_tsv_row (compat)."""
    return to_tsv_row(occ)


def parse_occ_row(text: str) -> dict:
    """Single row without a line terminator, using the same strict grammar."""
    if type(text) is not str:
        _invalid_tsv()
    return _validate_cells(text.split("\t"))


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------

def source_fp(
    sections_units: dict[str, list[dict]],
    excluded_sections: list[str] | None = None,
) -> str:
    """§5 source fingerprint.

    sections_units: {section: [{"unit_id": str, "kind": str, "text": str}, ...]}
    """
    if excluded_sections is None:
        excluded_sections = []
    sections_data = [
        {
            "section": sec,
            "units": [
                {
                    "unit_id": u.get("unit_id", str(uid)),
                    "kind": u.get("kind", u.get("type", "")),
                    "text_sha256": _sha256_str(u.get("text", "")),
                }
                for uid, u in enumerate(units)
            ],
        }
        for sec, units in sorted(sections_units.items())
        if sec not in excluded_sections
    ]
    obj = {
        "algo": "source/1",
        "tokenizer": TOKENIZER_VERSION,
        "excluded_sections": sorted(excluded_sections),
        "sections": sections_data,
    }
    return _canonical_hash(obj)


def manifest_fp(sections_rows: dict[str, list[dict]]) -> str:
    """§5 manifest fingerprint."""
    def _row(row: dict) -> dict:
        entry: dict = {}
        for field in MANIFEST_FP_FIELDS:
            # Membership is a real SU dependency: absent leadin means AUTO,
            # whereas explicit null disables the carrier. Keep it distinct.
            v = row[field] if field in row else {"absent": True}
            if field == "text" and field in row and v is not None:
                entry["text_sha256"] = _sha256_str(str(v))
            else:
                entry[field] = v
        return entry

    sections_data = [
        {"section": sec, "rows": [_row(r) for r in rows]}
        for sec, rows in sorted(sections_rows.items())
    ]
    obj = {"algo": "manifest/1", "fields": list(MANIFEST_FP_FIELDS), "sections": sections_data}
    return _canonical_hash(obj)


# ---------------------------------------------------------------------------
# Gold identity
# ---------------------------------------------------------------------------

def gold_identity(
    section: str,
    units: list[dict],
    unit_id: int,
    unit_token_index: int,
) -> dict:
    """Return §5 gold identity for a word occurrence."""
    unit = units[unit_id]
    form_source = list(_WORD.finditer(unit["text"]))[unit_token_index].group()

    def _u(idx: int) -> dict | None:
        if idx < 0 or idx >= len(units):
            return None
        u = units[idx]
        return {
            "unit_id": str(idx),
            "kind": u.get("type", u.get("kind", "")),
            "text_sha256": _sha256_str(u.get("text", "")),
        }

    return {
        "source_key": f"{section}|{unit_id}|{unit_token_index}",
        "form_source": form_source,
        "unit_kind": unit.get("type", unit.get("kind", "")),
        "unit_text_sha256": _sha256_str(unit.get("text", "")),
        "context_sha256": _canonical_hash([_u(unit_id - 1), _u(unit_id), _u(unit_id + 1)]),
    }


# ---------------------------------------------------------------------------
# U+0301 guard
# ---------------------------------------------------------------------------

class SourceMarkError(Exception):
    """Raised when a source unit contains U+0301 (combining accent mark)."""


def check_source_marks(units: list[dict], section: str = "") -> None:
    """Raise AnnotationError when any unit text contains U+0301."""
    from audiobook.unitmap import AnnotationError
    for i, unit in enumerate(units):
        if "́" in unit.get("text", ""):
            raise AnnotationError(
                "SOURCE_MARK_UNSUPPORTED",
                section=section,
                chunk_id="",
                detail=f"unit_id={i}",
            )


# ---------------------------------------------------------------------------
# Analysis text builder (L5)
# ---------------------------------------------------------------------------

def build_analysis_text(
    units: list[dict],
    form_analysis_map: dict[tuple[int, int, int], str],
) -> tuple[str, dict[tuple[int, int, int], tuple[int, int]]]:
    """Build L5 analysis string and offset map.

    Returns (analysis_text, {(uid, norm_s, norm_e): (ana_start, ana_end)}).
    """
    unit_strings: list[str] = []
    unit_word_positions: list[list[tuple[int, int, int, int]]] = []

    for uid, unit in enumerate(units):
        text: str = unit.get("text", "")
        parts: list[str] = []
        word_pos: list[tuple[int, int, int, int]] = []
        prev = 0
        for m in _WORD.finditer(text):
            parts.append(text[prev:m.start()])
            form = form_analysis_map.get((uid, m.start(), m.end()), m.group())
            ana_s_rel = sum(len(p) for p in parts)
            parts.append(form)
            ana_e_rel = ana_s_rel + len(form)
            word_pos.append((m.start(), m.end(), ana_s_rel, ana_e_rel))
            prev = m.end()
        parts.append(text[prev:])
        unit_strings.append("".join(parts))
        unit_word_positions.append(word_pos)

    analysis_text = "\n".join(unit_strings)

    offset_map: dict[tuple[int, int, int], tuple[int, int]] = {}
    pos = 0
    for uid, (unit_str, word_pos) in enumerate(zip(unit_strings, unit_word_positions)):
        for norm_s, norm_e, ana_s_rel, ana_e_rel in word_pos:
            offset_map[(uid, norm_s, norm_e)] = (pos + ana_s_rel, pos + ana_e_rel)
        pos += len(unit_str) + (1 if uid < len(unit_strings) - 1 else 0)

    return analysis_text, offset_map


# ---------------------------------------------------------------------------
# Full provenance pipeline
# ---------------------------------------------------------------------------

class RecordingManifestRow(dict):
    """Read-only row compatible with 6C11's dict structural checks.

    Reject undeclared dependencies at the actual read, including absent keys.
    Never include a manifest value in diagnostics.
    """

    def __init__(self, row, accessed=None):
        super().__init__(row)
        self.accessed = accessed if accessed is not None else set()

    def _record(self, key):
        from audiobook.unitmap import AnnotationError
        self.accessed.add(key)
        if key not in MANIFEST_FP_FIELDS:
            raise AnnotationError("MANIFEST_ACCESS_UNDECLARED")

    def __getitem__(self, key):
        self._record(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._record(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._record(key)
        return super().__contains__(key)

    def __iter__(self):
        for key in super().__iter__():
            self._record(key)
            yield key

    def keys(self):
        return tuple(iter(self))

    def items(self):
        return tuple((key, self[key]) for key in self)

    def values(self):
        return tuple(self[key] for key in self)

    def _readonly(self, *args, **kwargs):
        from audiobook.unitmap import AnnotationError
        raise AnnotationError("MANIFEST_READ_ONLY")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _readonly


def validate_manifest_accesses(rows, config, table, sentinel) -> frozenset[str]:
    """Guard actual SU readers without synthesis; analysis is guarded separately.

    Run production row_leadin, fragment and preparation callees under row and
    config guards. Existing WP-1 config-path enforcement remains in force.
    """
    from audiobook import leadin, synth
    from audiobook.sutrace import _DeepRecordingConfig, DECLARED_CONFIG_PATHS
    from audiobook.unitmap import AnnotationError

    accessed = set()
    cfg = _DeepRecordingConfig(config)
    for raw in rows:
        row = RecordingManifestRow(raw, accessed)
        phrase = synth.row_leadin(row)
        open_end = row.get("open_end", False)
        frags = synth.chunk_fragments(row["text"], cfg)
        row["n"], row["id"], row.get("pause_after_ms")
        if len(frags) == 1:
            synth.prepare_synth_text(row["text"], cfg, table, sentinel, phrase, open_end)
        else:
            for text, _, is_enum in frags:
                text = text.rstrip("?") if is_enum and text.endswith("?") else text
                synth.prepare_synth_text(text, cfg, table, sentinel, leadin.AUTO, False)
    if cfg._accessed - DECLARED_CONFIG_PATHS:
        raise AnnotationError("CONFIG_ACCESS_UNDECLARED")
    return frozenset(accessed)


def _final_pad_len(trace) -> int:
    if trace.status != "ok":
        return trace.pad_len
    from audiobook.stress_facts import trace_coordinates
    return trace_coordinates(trace)[1]


def process_section_occs(
    section: str,
    units: list[dict],
    chunks: list[dict],
    traces: list | None,
) -> tuple[list[WordOcc], str, dict]:
    """Align all Cyrillic words in a section to their SU positions.

    traces: flat list of SUTrace (matched to chunks by chunk_id), or None.
    Returns (occs, analysis_text, offset_map).
    """
    from audiobook.unitmap import map_section

    check_source_marks(units, section)
    chunks = [RecordingManifestRow(c) for c in chunks]

    if traces is None:
        traces = []

    # Keep engine invocation order and each fragment's local token index.
    chunk_traces: dict[str, list] = {}
    for tr in traces:
        chunk_traces.setdefault(tr.chunk_id, []).append(tr)

    chunk_trace_words: dict[str, list[tuple[str, str, int | None, int]]] = {}
    chunk_trace_status: dict[str, str] = {}
    for cid, contributing in chunk_traces.items():
        statuses = {tr.status for tr in contributing}
        fragments = [tr.fragment for tr in contributing]
        if "trace_mismatch" in statuses:
            chunk_trace_status[cid] = "trace_mismatch"
        elif statuses != {"ok"}:
            chunk_trace_status[cid] = "trace_unsupported"
        elif fragments != [None] and fragments != list(range(len(contributing))):
            chunk_trace_status[cid] = "fragment_mismatch"
        else:
            chunk_trace_status[cid] = "word_match"
        chunk_trace_words[cid] = [
            (_fold(m.group()), m.group(), tr.fragment, ti)
            for tr in contributing
            for ti, m in enumerate(_WORD.finditer(tr.prep_text[_final_pad_len(tr):]))
        ]

    # Build SectionMap
    chunk_n_map: dict[str, int] = {str(c.get("id", "")): int(c.get("n", 0)) for c in chunks}
    sm = map_section(units, chunks, section=section)

    # atom_idx → (chunk_id, chunk_n)
    atom_to_chunk: dict[int, tuple[str, int]] = {}
    for cs in sm.spans:
        n = chunk_n_map.get(cs.chunk_id, 0)
        for ai in range(cs.atom_start, cs.atom_end):
            atom_to_chunk[ai] = (cs.chunk_id, n)

    # Pre-count chunk words (for fragment_mismatch detection)
    chunk_word_total: dict[str, int] = {}
    for ai, atom in enumerate(sm.stream):
        cid, _ = atom_to_chunk.get(ai, ("", 0))
        if cid:
            count = sum(1 for _ in _WORD.finditer(atom.text))
            chunk_word_total[cid] = chunk_word_total.get(cid, 0) + count

    # Determine per-chunk alignment mode:
    # "trace_unsupported" | "fragment_mismatch" | "word_match"
    chunk_align_mode: dict[str, str] = {}
    for cid in chunk_word_total:
        mode = chunk_trace_status.get(cid, "trace_unsupported")
        if mode != "word_match":
            chunk_align_mode[cid] = mode
        elif chunk_word_total[cid] != len(chunk_trace_words.get(cid, [])):
            chunk_align_mode[cid] = "fragment_mismatch"
        else:
            chunk_align_mode[cid] = "word_match"

    # Build provenance records
    form_analysis_map: dict[tuple[int, int, int], str] = {}
    unit_word_counter: dict[int, int] = {}
    chunk_word_counter: dict[str, int] = {}

    # Records: list of tuples, each representing one word occurrence
    records: list[tuple] = []

    for ai, atom in enumerate(sm.stream):
        cid, chunk_n = atom_to_chunk.get(ai, ("", 0))
        uid = atom.unit_id

        for m in _WORD.finditer(atom.text):
            norm_start = atom.start + m.start()
            norm_end = atom.start + m.end()
            form_source = m.group()
            norm_key = (uid, norm_start, norm_end)

            unit_tok_idx = unit_word_counter.get(uid, 0)
            unit_word_counter[uid] = unit_tok_idx + 1

            cwi = chunk_word_counter.get(cid, 0)
            chunk_word_counter[cid] = cwi + 1

            mode = chunk_align_mode.get(cid, "trace_unsupported")
            if mode != "word_match":
                alignment_status = mode
                su_cid = None
                su_frag: int | None = None
                su_tok_idx: int | None = None
                form_synth: str | None = None
            else:  # word_match: compare 1:1 within chunk
                tw_list = chunk_trace_words.get(cid, [])
                if cwi < len(tw_list):
                    fold_tw, orig_tw, fragment, token_index = tw_list[cwi]
                    if _fold(form_source) == fold_tw:
                        alignment_status = "aligned"
                        su_cid = cid
                        su_frag = fragment
                        su_tok_idx = token_index
                        form_synth = orig_tw
                    else:
                        alignment_status = "prep_token_mismatch"
                        su_cid = None
                        su_frag = None
                        su_tok_idx = None
                        form_synth = None
                else:
                    alignment_status = "fragment_mismatch"
                    su_cid = None
                    su_frag = None
                    su_tok_idx = None
                    form_synth = None

            form_analysis = form_synth if form_synth is not None else form_source
            form_analysis_map[norm_key] = form_analysis

            records.append((
                uid, norm_start, norm_end, form_source,
                ai, m.start(), m.end(),
                cid, chunk_n, cwi, unit_tok_idx,
                su_cid, su_frag, su_tok_idx, form_synth,
                alignment_status, form_analysis,
            ))

    # Build analysis text
    analysis_text, offset_map = build_analysis_text(units, form_analysis_map)

    # Build final WordOcc list
    occs: list[WordOcc] = []
    for rec in records:
        (
            uid, norm_start, norm_end, form_source,
            ai, acs, ace,
            cid, chunk_n, cwi, unit_tok_idx,
            su_cid, su_frag, su_tok_idx, form_synth,
            alignment_status, form_analysis,
        ) = rec
        norm_key = (uid, norm_start, norm_end)
        ana_start, ana_end = offset_map.get(norm_key, (0, 0))
        occ = WordOcc(
            source_key=f"{section}|{uid}|{unit_tok_idx}",
            section=section,
            unit_id=str(uid),
            unit_token_index=unit_tok_idx,
            norm_start=norm_start,
            norm_end=norm_end,
            form_source=form_source,
            chunk_n=chunk_n,
            chunk_id=cid,
            chunk_word_index=cwi,
            atom_index=ai,
            atom_char_start=acs,
            atom_char_end=ace,
            ana_start=ana_start,
            ana_end=ana_end,
            form_analysis=form_analysis,
            su_chunk_id=su_cid,
            su_fragment=su_frag,
            su_token_index=su_tok_idx,
            form_synth=form_synth,
            alignment_status=alignment_status,
        )
        occs.append(occ)

    return occs, analysis_text, offset_map
