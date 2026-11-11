"""Tests for Atom, ChunkSpan, AnnotationError and pre-mapping gates — T15-6C11-1."""
import unicodedata
import pytest

from audiobook.unitmap import Atom, ChunkSpan, AnnotationError, atoms, validate_gates


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

def test_chunkspan_fields():
    cs = ChunkSpan(chunk_id="0001", n=1, text="текст")
    assert cs.chunk_id == "0001"
    assert cs.n == 1
    assert cs.text == "текст"
    assert cs.kind is None
    assert cs.unit_id is None


def test_chunkspan_frozen():
    cs = ChunkSpan(chunk_id="0001", n=1, text="текст")
    with pytest.raises((AttributeError, TypeError)):
        cs.n = 2  # type: ignore[misc]


def test_chunkspan_with_optional_fields():
    cs = ChunkSpan(chunk_id="0002", n=2, text="слово", kind="heading", unit_id=0)
    assert cs.kind == "heading"
    assert cs.unit_id == 0


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
