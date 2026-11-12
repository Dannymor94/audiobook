"""Word provenance: source-to-SU alignment, coordinates, fingerprints.

T15-7.3: WordOcc (35 fields), source_fp, manifest_fp, gold_identity,
U+0301 guard, TSV serialisation, and process_section_occs.
No synthesis, no model loading, no manifest writes.
"""
from __future__ import annotations

import hashlib
import json
import re
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

@dataclass  # NOT frozen — apply_facts uses dataclasses.replace()
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


def to_tsv_row(occ: WordOcc) -> str:
    cells: list[str] = []
    for name in _FIELD_NAMES:
        v = getattr(occ, name)
        if v is None:
            cells.append("")
        elif name in _BOOL_FIELDS:
            cells.append("1" if v else "0")
        else:
            cells.append(str(v))
    return "\t".join(cells)


def from_tsv_row(cells: list[str]) -> WordOcc:
    if len(cells) != len(_FIELD_NAMES):
        raise ValueError(f"Expected {len(_FIELD_NAMES)} columns, got {len(cells)}")
    kwargs: dict = {}
    for name, raw in zip(_FIELD_NAMES, cells):
        if name in _BOOL_FIELDS:
            kwargs[name] = raw == "1"
        elif name in _INT_FIELDS:
            kwargs[name] = int(raw)
        elif name in _NULLABLE_INT_FIELDS:
            kwargs[name] = int(raw) if raw != "" else None
        elif name in _NULLABLE_STR_FIELDS:
            kwargs[name] = raw if raw != "" else None
        else:
            kwargs[name] = raw
    return WordOcc(**kwargs)


def serialize_tsv(occs: list[WordOcc]) -> str:
    return "\n".join([tsv_header()] + [to_tsv_row(o) for o in occs])


def parse_tsv(text: str) -> list[WordOcc]:
    lines = text.splitlines()
    return [from_tsv_row(ln.split("\t")) for ln in lines[1:] if ln]


def serialize_occ(occ: WordOcc) -> str:
    """Alias for to_tsv_row (compat)."""
    return to_tsv_row(occ)


def parse_occ_row(text: str) -> dict:
    """TSV row string → dict (compat)."""
    cells = text.split("\t")
    if len(cells) < len(_FIELD_NAMES):
        raise ValueError(f"Too few columns: {len(cells)}")
    result: dict = {}
    for name, raw in zip(_FIELD_NAMES, cells[:len(_FIELD_NAMES)]):
        if name in _BOOL_FIELDS:
            result[name] = raw == "1"
        elif name in _INT_FIELDS:
            result[name] = int(raw)
        elif name in _NULLABLE_INT_FIELDS:
            result[name] = int(raw) if raw != "" else None
        elif name in _NULLABLE_STR_FIELDS:
            result[name] = raw if raw != "" else None
        else:
            result[name] = raw
    return result


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
            v = row.get(field)
            if field == "text" and v is not None:
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

    if traces is None:
        traces = []

    # Map chunk_id → trace
    chunk_to_trace: dict[str, object] = {}
    for tr in traces:
        cid = getattr(tr, "chunk_id", None)
        if cid is not None:
            chunk_to_trace[cid] = tr

    # Pre-build per-chunk trace word lists
    chunk_trace_words: dict[str, list[tuple[str, str]]] = {}
    for cid, tr in chunk_to_trace.items():
        post_pad = tr.prep_text[tr.pad_len:]  # type: ignore[union-attr]
        chunk_trace_words[cid] = [
            (_fold(m.group()), m.group()) for m in _WORD.finditer(post_pad)
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
        if cid not in chunk_to_trace:
            chunk_align_mode[cid] = "trace_unsupported"
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
        trace = chunk_to_trace.get(cid)

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
            if mode == "trace_unsupported":
                alignment_status = "trace_unsupported"
                su_cid = None
                su_frag: int | None = None
                su_tok_idx: int | None = None
                form_synth: str | None = None
            elif mode == "fragment_mismatch":
                alignment_status = "fragment_mismatch"
                su_cid = None
                su_frag = None
                su_tok_idx = None
                form_synth = None
            else:  # word_match: compare 1:1 within chunk
                tw_list = chunk_trace_words.get(cid, [])
                if cwi < len(tw_list):
                    fold_tw, orig_tw = tw_list[cwi]
                    if _fold(form_source) == fold_tw:
                        alignment_status = "aligned"
                        su_cid = cid
                        su_frag = getattr(trace, "fragment", None) if trace else None
                        su_tok_idx = cwi
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
