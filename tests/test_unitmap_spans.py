"""Tests for Atom, ChunkSpan, AnnotationError and pre-mapping gates — T15-6C11-1b."""
import unicodedata
import pytest

from audiobook.unitmap import Atom, ChunkSpan, AnnotationError, atoms, validate_gates, check_gates


# ── Atom ──────────────────────────────────────────────────────────────────────

def test_atom_fields():
    a = Atom("слово", 2, 0, 5)
    assert a.text == "слово"
    assert a.unit_id == 2
    assert a.start == 0
    assert a.end == 5


def test_atom_frozen():
    a = Atom("слово", 0, 0, 5)
    with pytest.raises((AttributeError, TypeError)):
        a.text = "другое"  # type: ignore[misc]


def test_atoms_basic():
    result = atoms("hello world", 3)
    assert result == [Atom("hello", 3, 0, 5), Atom("world", 3, 6, 11)]


def test_atoms_empty_string():
    assert atoms("", 0) == []


def test_atoms_whitespace_only():
    assert atoms("   \t\n  ", 0) == []


def test_atoms_preserves_unit_id():
    result = atoms("ab cd", 7)
    assert all(a.unit_id == 7 for a in result)


def test_atoms_offsets():
    result = atoms("x  y", 0)
    assert result[0].start == 0 and result[0].end == 1
    assert result[1].start == 3 and result[1].end == 4


# ── ChunkSpan ─────────────────────────────────────────────────────────────────

def _make_chunkspan(**kw) -> ChunkSpan:
    defaults = dict(
        chunk_id="0001",
        atom_start=0,
        atom_end=2,
        spans=((0, 5), (6, 11)),
        unit_ids=frozenset({0}),
        kind="text",
        end_modes=None,
    )
    defaults.update(kw)
    return ChunkSpan(**defaults)


def test_chunkspan_exact_fields():
    cs = _make_chunkspan()
    assert cs.chunk_id == "0001"
    assert cs.atom_start == 0
    assert cs.atom_end == 2
    assert cs.spans == ((0, 5), (6, 11))
    assert cs.unit_ids == frozenset({0})
    assert cs.kind == "text"
    assert cs.end_modes is None


def test_chunkspan_no_extra_fields():
    # contractual field names only — n, text, unit_id must NOT exist
    cs = _make_chunkspan()
    assert not hasattr(cs, "n")
    assert not hasattr(cs, "text")
    assert not hasattr(cs, "unit_id")


def test_chunkspan_frozen():
    cs = _make_chunkspan()
    with pytest.raises((AttributeError, TypeError)):
        cs.atom_start = 1  # type: ignore[misc]


def test_chunkspan_spans_structural():
    # spans is a tuple of (int, int) pairs
    spans = ((0, 3), (4, 7), (8, 12))
    cs = _make_chunkspan(atom_start=0, atom_end=3, spans=spans)
    assert isinstance(cs.spans, tuple)
    assert all(isinstance(s, tuple) and len(s) == 2 for s in cs.spans)
    assert cs.atom_end - cs.atom_start == len(cs.spans)


def test_chunkspan_unit_ids_frozenset():
    cs = _make_chunkspan(unit_ids=frozenset({0, 1}))
    assert isinstance(cs.unit_ids, frozenset)
    assert 0 in cs.unit_ids and 1 in cs.unit_ids


def test_chunkspan_end_modes_frozenset():
    cs = _make_chunkspan(end_modes=frozenset({"open_end"}))
    assert isinstance(cs.end_modes, frozenset)
    assert "open_end" in cs.end_modes


def test_chunkspan_zero_atom_range():
    # atom_end == atom_start → zero-atom chunk; spans must be empty tuple
    cs = _make_chunkspan(atom_start=3, atom_end=3, spans=())
    assert cs.atom_end == cs.atom_start
    assert cs.spans == ()


def test_chunkspan_heading_kind():
    cs = _make_chunkspan(kind="heading")
    assert cs.kind == "heading"


def test_chunkspan_hashable():
    # frozen dataclass with hashable fields must be hashable
    cs = _make_chunkspan()
    assert hash(cs) is not None
    s = {cs}
    assert cs in s


# ── AnnotationError ───────────────────────────────────────────────────────────

def test_annotation_error_code():
    e = AnnotationError("NOT_NFC", section="ch01", chunk_id="0001")
    assert e.code == "NOT_NFC"
    assert e.section == "ch01"
    assert e.chunk_id == "0001"
    assert e.detail == ""


def test_annotation_error_reason_alias():
    # backward compat: .reason == .code
    e = AnnotationError("NOT_NFC")
    assert e.reason == e.code


def test_annotation_error_detail():
    e = AnnotationError("MANIFEST_ORDER", section="ch01", chunk_id="0003", detail="n=3 expected=2")
    assert e.detail == "n=3 expected=2"


def test_annotation_error_mismatch_idx_preserved():
    # existing callers pass mismatch_idx
    e = AnnotationError("token mismatch (I1)", section="ch01", chunk_id="0002", mismatch_idx=5)
    assert e.mismatch_idx == 5
    assert "tok=5" in str(e)


def test_annotation_error_message_no_manuscript():
    # error message must not embed raw text — just code and context
    e = AnnotationError("NOT_NFC", section="ch02", chunk_id="0010")
    assert "NOT_NFC" in str(e)
    assert "ch02" in str(e)
    assert "0010" in str(e)


# ── Gate #2: NFC violations ───────────────────────────────────────────────────

def test_gate_nfc_unit_violation():
    # "ё" (U+0451) decomposes to "е" + combining diaeresis in NFD
    nfd = unicodedata.normalize("NFD", "ё")
    assert unicodedata.normalize("NFC", nfd) != nfd  # sanity: actually non-NFC
    units = [{"text": nfd}]
    chunks = [{"id": "0001", "n": 1, "text": "x"}]
    errors = validate_gates(chunks, units, section="ch01")
    assert any(e.code == "NOT_NFC" for e in errors)


def test_gate_nfc_unit_pass():
    units = [{"text": "нормальный текст"}]
    chunks = [{"id": "0001", "n": 1, "text": "нормальный"}]
    nfc_errors = [e for e in validate_gates(chunks, units) if e.code == "NOT_NFC"]
    assert nfc_errors == []


def test_gate_nfc_chunk_violation():
    # "ёж" contains "ё" which decomposes in NFD
    nfd = unicodedata.normalize("NFD", "ёж")
    assert unicodedata.normalize("NFC", nfd) != nfd  # sanity
    units = [{"text": "ёж"}]
    chunks = [{"id": "0001", "n": 1, "text": nfd}]
    errors = validate_gates(chunks, units)
    nfc_errors = [e for e in errors if e.code == "NOT_NFC"]
    assert nfc_errors  # at least one for the chunk


def test_gate_nfc_chunk_no_empty_chunk_when_nfc_bad():
    # non-NFC chunk: NOT_NFC fires, EMPTY_CHUNK must not also fire (short-circuit)
    nfd = unicodedata.normalize("NFD", "ё")  # non-NFC, non-empty
    chunks = [{"id": "0001", "n": 1, "text": nfd}]
    errors = validate_gates(chunks, [])
    codes = [e.code for e in errors]
    assert "NOT_NFC" in codes
    nfc_hits = [e for e in errors if e.code == "NOT_NFC" and e.chunk_id == "0001"]
    empty_hits = [e for e in errors if e.code == "EMPTY_CHUNK" and e.chunk_id == "0001"]
    assert nfc_hits
    assert not empty_hits


# ── Gate #12: inner-paragraph newline ────────────────────────────────────────

def test_gate_inner_para_double_newline():
    units = [{"text": "первый\n\nвторой"}]
    chunks = [{"id": "0001", "n": 1, "text": "первый"}]
    errors = validate_gates(chunks, units)
    assert any(e.code == "UNIT_INNER_PARA" for e in errors)


def test_gate_inner_para_single_newline_ok():
    units = [{"text": "первая строка\nвторая строка"}]
    chunks = [{"id": "0001", "n": 1, "text": "первая"}]
    inner_errors = [e for e in validate_gates(chunks, units) if e.code == "UNIT_INNER_PARA"]
    assert inner_errors == []


def test_gate_inner_para_newline_with_spaces():
    units = [{"text": "первый\n   \nвторой"}]
    chunks = [{"id": "0001", "n": 1, "text": "первый"}]
    errors = validate_gates(chunks, units)
    assert any(e.code == "UNIT_INNER_PARA" for e in errors)


def test_gate_inner_para_newline_with_tabs():
    units = [{"text": "а\n\t\nб"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, units)
    assert any(e.code == "UNIT_INNER_PARA" for e in errors)


def test_gate_empty_unit_allowed():
    # empty unit text: no UNIT_INNER_PARA, no NOT_NFC
    units = [{"text": ""}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    errors = [e for e in validate_gates(chunks, units) if e.code in ("UNIT_INNER_PARA", "NOT_NFC")]
    assert errors == []


def test_gate_single_newline_multiple_units():
    units = [{"text": "а\nб"}, {"text": "в\nг"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    inner_errors = [e for e in validate_gates(chunks, units) if e.code == "UNIT_INNER_PARA"]
    assert inner_errors == []


# ── Gate #14: manifest ordering ───────────────────────────────────────────────

def test_gate_manifest_order_ok():
    chunks = [
        {"id": "0001", "n": 1, "text": "а"},
        {"id": "0002", "n": 2, "text": "б"},
        {"id": "0003", "n": 3, "text": "в"},
    ]
    order_errors = [e for e in validate_gates(chunks, []) if e.code == "MANIFEST_ORDER"]
    assert order_errors == []


def test_gate_manifest_order_n_gap():
    chunks = [{"id": "0001", "n": 1, "text": "а"}, {"id": "0003", "n": 3, "text": "б"}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_n_starts_at_zero():
    chunks = [{"id": "0000", "n": 0, "text": "а"}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_n_starts_at_two():
    chunks = [{"id": "0002", "n": 2, "text": "а"}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_duplicate_id():
    chunks = [
        {"id": "0001", "n": 1, "text": "а"},
        {"id": "0001", "n": 2, "text": "б"},
    ]
    errors = validate_gates(chunks, [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_id_format_mismatch():
    # n=1 but id="1" instead of "0001"
    chunks = [{"id": "1", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_id_format_too_long():
    # n=1 but id="00001" (5 digits)
    chunks = [{"id": "00001", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


# ── Gate #25: empty chunk ─────────────────────────────────────────────────────

def test_gate_empty_chunk_whitespace_only():
    chunks = [{"id": "0001", "n": 1, "text": "   "}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "EMPTY_CHUNK" for e in errors)


def test_gate_empty_chunk_empty_string():
    chunks = [{"id": "0001", "n": 1, "text": ""}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "EMPTY_CHUNK" for e in errors)


def test_gate_empty_chunk_tabs_newlines():
    chunks = [{"id": "0001", "n": 1, "text": "\t\n  \r\n"}]
    errors = validate_gates(chunks, [])
    assert any(e.code == "EMPTY_CHUNK" for e in errors)


def test_gate_empty_chunk_ok_single_char():
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    empty_errors = [e for e in validate_gates(chunks, []) if e.code == "EMPTY_CHUNK"]
    assert empty_errors == []


def test_gate_empty_chunk_ok_punctuation_only():
    # punctuation is non-whitespace → not empty
    chunks = [{"id": "0001", "n": 1, "text": "..."}]
    empty_errors = [e for e in validate_gates(chunks, []) if e.code == "EMPTY_CHUNK"]
    assert empty_errors == []


# ── check_gates: fail-closed raising path ────────────────────────────────────

def test_check_gates_raises_on_nfc_violation():
    nfd = unicodedata.normalize("NFD", "ё")
    units = [{"text": nfd}]
    chunks = [{"id": "0001", "n": 1, "text": "x"}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, units, section="ch01")
    assert exc.value.code == "NOT_NFC"


def test_check_gates_raises_on_inner_para():
    units = [{"text": "а\n\nб"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, units)
    assert exc.value.code == "UNIT_INNER_PARA"


def test_check_gates_raises_on_manifest_order():
    chunks = [{"id": "0002", "n": 2, "text": "а"}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, [])
    assert exc.value.code == "MANIFEST_ORDER"


def test_check_gates_raises_on_empty_chunk():
    chunks = [{"id": "0001", "n": 1, "text": "   "}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, [])
    assert exc.value.code == "EMPTY_CHUNK"


def test_check_gates_passes_on_valid_input():
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    check_gates(chunks, units)  # must not raise


def test_check_gates_raises_annotation_error_subclass():
    # check_gates must raise AnnotationError specifically (not generic Exception)
    chunks = [{"id": "0001", "n": 1, "text": ""}]
    with pytest.raises(AnnotationError):
        check_gates(chunks, [])
