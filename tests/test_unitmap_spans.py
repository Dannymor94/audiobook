"""Tests for Atom, ChunkSpan, AnnotationError and pre-mapping gates — T15-6C11-1b."""
import unicodedata
import pytest

from audiobook.unitmap import (
    Atom, ChunkSpan, SectionMap, AnnotationError,
    atoms, source_atoms, validate_gates, check_gates,
    map_section, map_chunks, chunk_atoms,
    validate_section, _section_violation, _validate_chunk_span,
)


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
    e = AnnotationError("NOT_NFC", section="01_test", chunk_id="0001")
    assert e.code == "NOT_NFC"
    assert e.section == "01_test"
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
    e = AnnotationError("NOT_NFC", section="02_test", chunk_id="0010")
    assert "NOT_NFC" in str(e)
    assert "02_test" in str(e)
    assert "0010" in str(e)


# ── Gate #2: NFC violations ───────────────────────────────────────────────────

def test_gate_nfc_unit_violation():
    # "ё" (U+0451) decomposes to "е" + combining diaeresis in NFD
    nfd = unicodedata.normalize("NFD", "ё")
    assert unicodedata.normalize("NFC", nfd) != nfd  # sanity: actually non-NFC
    units = [{"text": nfd}]
    chunks = [{"id": "0001", "n": 1, "text": "x"}]
    errors = validate_gates(chunks, units, section="01_test")
    assert any(e.code == "NOT_NFC" for e in errors)


def test_gate_nfc_unit_pass():
    units = [{"text": "нормальный текст"}]
    chunks = [{"id": "0001", "n": 1, "text": "нормальный"}]
    nfc_errors = [e for e in validate_gates(chunks, units, section="01_test") if e.code == "NOT_NFC"]
    assert nfc_errors == []


def test_gate_nfc_chunk_violation():
    # "ёж" contains "ё" which decomposes in NFD
    nfd = unicodedata.normalize("NFD", "ёж")
    assert unicodedata.normalize("NFC", nfd) != nfd  # sanity
    units = [{"text": "ёж"}]
    chunks = [{"id": "0001", "n": 1, "text": nfd}]
    errors = validate_gates(chunks, units, section="01_test")
    nfc_errors = [e for e in errors if e.code == "NOT_NFC"]
    assert nfc_errors  # at least one for the chunk


def test_gate_nfc_chunk_no_empty_chunk_when_nfc_bad():
    # non-NFC chunk: NOT_NFC fires, EMPTY_CHUNK must not also fire (short-circuit)
    nfd = unicodedata.normalize("NFD", "ё")  # non-NFC, non-empty
    chunks = [{"id": "0001", "n": 1, "text": nfd}]
    errors = validate_gates(chunks, [], section="01_test")
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
    errors = validate_gates(chunks, units, section="01_test")
    assert any(e.code == "UNIT_INNER_PARA" for e in errors)


def test_gate_inner_para_single_newline_ok():
    units = [{"text": "первая строка\nвторая строка"}]
    chunks = [{"id": "0001", "n": 1, "text": "первая"}]
    inner_errors = [e for e in validate_gates(chunks, units, section="01_test") if e.code == "UNIT_INNER_PARA"]
    assert inner_errors == []


def test_gate_inner_para_newline_with_spaces():
    units = [{"text": "первый\n   \nвторой"}]
    chunks = [{"id": "0001", "n": 1, "text": "первый"}]
    errors = validate_gates(chunks, units, section="01_test")
    assert any(e.code == "UNIT_INNER_PARA" for e in errors)


def test_gate_inner_para_newline_with_tabs():
    units = [{"text": "а\n\t\nб"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, units, section="01_test")
    assert any(e.code == "UNIT_INNER_PARA" for e in errors)


def test_gate_empty_unit_allowed():
    # empty unit text: no UNIT_INNER_PARA, no NOT_NFC
    units = [{"text": ""}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    errors = [e for e in validate_gates(chunks, units, section="01_test") if e.code in ("UNIT_INNER_PARA", "NOT_NFC")]
    assert errors == []


def test_gate_single_newline_multiple_units():
    units = [{"text": "а\nб"}, {"text": "в\nг"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    inner_errors = [e for e in validate_gates(chunks, units, section="01_test") if e.code == "UNIT_INNER_PARA"]
    assert inner_errors == []


# ── Gate #14: manifest ordering ───────────────────────────────────────────────

def test_gate_manifest_order_ok():
    chunks = [
        {"id": "0001", "n": 1, "text": "а"},
        {"id": "0002", "n": 2, "text": "б"},
        {"id": "0003", "n": 3, "text": "в"},
    ]
    order_errors = [e for e in validate_gates(chunks, [], section="01_test") if e.code == "MANIFEST_ORDER"]
    assert order_errors == []


def test_gate_manifest_order_n_gap():
    chunks = [{"id": "0001", "n": 1, "text": "а"}, {"id": "0003", "n": 3, "text": "б"}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_n_starts_at_zero():
    chunks = [{"id": "0000", "n": 0, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_n_starts_at_two():
    chunks = [{"id": "0002", "n": 2, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_duplicate_id():
    chunks = [
        {"id": "0001", "n": 1, "text": "а"},
        {"id": "0001", "n": 2, "text": "б"},
    ]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_id_format_mismatch():
    # n=1 but id="1" instead of "0001"
    chunks = [{"id": "1", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_gate_manifest_order_id_format_too_long():
    # n=1 but id="00001" (5 digits)
    chunks = [{"id": "00001", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


# ── Gate #25: empty chunk ─────────────────────────────────────────────────────

def test_gate_empty_chunk_whitespace_only():
    chunks = [{"id": "0001", "n": 1, "text": "   "}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "EMPTY_CHUNK" for e in errors)


def test_gate_empty_chunk_empty_string():
    chunks = [{"id": "0001", "n": 1, "text": ""}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "EMPTY_CHUNK" for e in errors)


def test_gate_empty_chunk_tabs_newlines():
    chunks = [{"id": "0001", "n": 1, "text": "\t\n  \r\n"}]
    errors = validate_gates(chunks, [], section="01_test")
    assert any(e.code == "EMPTY_CHUNK" for e in errors)


def test_gate_empty_chunk_ok_single_char():
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    empty_errors = [e for e in validate_gates(chunks, [], section="01_test") if e.code == "EMPTY_CHUNK"]
    assert empty_errors == []


def test_gate_empty_chunk_ok_punctuation_only():
    # punctuation is non-whitespace → not empty
    chunks = [{"id": "0001", "n": 1, "text": "..."}]
    empty_errors = [e for e in validate_gates(chunks, [], section="01_test") if e.code == "EMPTY_CHUNK"]
    assert empty_errors == []


# ── check_gates: fail-closed raising path ────────────────────────────────────

def test_check_gates_raises_on_nfc_violation():
    nfd = unicodedata.normalize("NFD", "ё")
    units = [{"text": nfd}]
    chunks = [{"id": "0001", "n": 1, "text": "x"}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, units, section="01_test")
    assert exc.value.code == "NOT_NFC"


def test_check_gates_raises_on_inner_para():
    units = [{"text": "а\n\nб"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, units, section="01_test")
    assert exc.value.code == "UNIT_INNER_PARA"


def test_check_gates_raises_on_manifest_order():
    chunks = [{"id": "0002", "n": 2, "text": "а"}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, [], section="01_test")
    assert exc.value.code == "MANIFEST_ORDER"


def test_check_gates_raises_on_empty_chunk():
    chunks = [{"id": "0001", "n": 1, "text": "   "}]
    with pytest.raises(AnnotationError) as exc:
        check_gates(chunks, [], section="01_test")
    assert exc.value.code == "EMPTY_CHUNK"


def test_check_gates_passes_on_valid_input():
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    check_gates(chunks, units, section="01_test")  # must not raise


def test_check_gates_raises_annotation_error_subclass():
    # check_gates must raise AnnotationError specifically (not generic Exception)
    chunks = [{"id": "0001", "n": 1, "text": ""}]
    with pytest.raises(AnnotationError):
        check_gates(chunks, [], section="01_test")


# ── map_chunks helpers ────────────────────────────────────────────────────────

# (map_chunks already imported at top)


def _mk_chunks(*texts: str) -> list[dict]:
    return [{"text": t, "id": f"{i+1:04d}", "n": i+1} for i, t in enumerate(texts)]


def _mk_units(*pairs: tuple[str, str]) -> list[dict]:
    return [{"type": tp, "text": tx} for tp, tx in pairs]


def _para(text: str) -> tuple[str, str]:
    return ("paragraph", text)


def _head(text: str) -> tuple[str, str]:
    return ("heading", text)


# ── #1: basic success ─────────────────────────────────────────────────────────

def test_map_basic_single_chunk():
    units = _mk_units(_para("слово раз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks, section="01_test")
    assert len(spans) == 1
    cs = spans[0]
    assert cs.chunk_id == "0001"
    assert cs.atom_start == 0
    assert cs.atom_end == 2
    assert cs.unit_ids == frozenset({0})
    assert cs.kind == "text"
    assert cs.end_modes is None


def test_map_multiple_chunks_same_unit():
    units = _mk_units(_para("а б в г"))
    chunks = _mk_chunks("а б", "в г")
    spans = map_chunks(units, chunks, section="01_test")
    assert [cs.atom_start for cs in spans] == [0, 2]
    assert [cs.atom_end for cs in spans] == [2, 4]


def test_map_chunks_across_units():
    units = _mk_units(_para("а б"), _para("в г"))
    chunks = _mk_chunks("а б", "в г")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].unit_ids == frozenset({0})
    assert spans[1].unit_ids == frozenset({1})


# ── #3: extra chunk / stream exhausted ───────────────────────────────────────

def test_map_stream_exhausted_extra_chunk():
    units = _mk_units(_para("слово"))
    chunks = _mk_chunks("слово", "лишнее")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "STREAM_EXHAUSTED"


def test_map_stream_exhausted_empty_source():
    units = _mk_units(_para(""))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "STREAM_EXHAUSTED"


# ── #4: trailing atoms ────────────────────────────────────────────────────────

def test_map_trailing_source_atoms():
    units = _mk_units(_para("слово раз"))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "TRAILING_SOURCE"


def test_map_trailing_source_multiple_units():
    units = _mk_units(_para("а б"), _para("в"))
    chunks = _mk_chunks("а б")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "TRAILING_SOURCE"


# ── #5–7: atom mismatch (case, ё, punctuation) ───────────────────────────────

def test_map_atom_mismatch_case():
    units = _mk_units(_para("Слово"))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_uppercase():
    units = _mk_units(_para("слово"))
    chunks = _mk_chunks("СЛОВО")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_yo_e():
    units = _mk_units(_para("ёлка"))
    chunks = _mk_chunks("елка")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_e_yo():
    units = _mk_units(_para("елка"))
    chunks = _mk_chunks("ёлка")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_trailing_punct():
    units = _mk_units(_para("слово."))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_added_punct():
    units = _mk_units(_para("слово"))
    chunks = _mk_chunks("слово.")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_different_word():
    units = _mk_units(_para("кот"))
    chunks = _mk_chunks("кит")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


# ── #8: NBSP and double spaces succeed ───────────────────────────────────────

def test_map_nbsp_in_source():
    # NBSP treated as whitespace by \S+: atoms still split correctly
    units = _mk_units(_para("слово\xa0раз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].atom_end - spans[0].atom_start == 2


def test_map_double_space_in_source():
    units = _mk_units(_para("слово  раз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].atom_end - spans[0].atom_start == 2


def test_map_double_space_in_chunk():
    units = _mk_units(_para("слово раз"))
    chunks = _mk_chunks("слово  раз")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].atom_end - spans[0].atom_start == 2


# ── #9: single newlines succeed ──────────────────────────────────────────────

def test_map_newline_in_source():
    units = _mk_units(_para("слово\nраз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].atom_end - spans[0].atom_start == 2


def test_map_newline_between_chunks():
    units = _mk_units(_para("а\nб"))
    chunks = _mk_chunks("а", "б")
    spans = map_chunks(units, chunks, section="01_test")
    assert len(spans) == 2


# ── #10: repeated identical atoms ────────────────────────────────────────────

def test_map_repeated_atoms_sequential():
    units = _mk_units(_para("abc abc abc"))
    chunks = _mk_chunks("abc", "abc", "abc")
    spans = map_chunks(units, chunks, section="01_test")
    assert [cs.atom_start for cs in spans] == [0, 1, 2]
    assert [cs.atom_end for cs in spans] == [1, 2, 3]
    # each span points to a different source position
    assert spans[0].spans[0] != spans[1].spans[0]
    assert spans[1].spans[0] != spans[2].spans[0]


def test_map_reused_atom_stops():
    # architect test #1: chunk 2 "abc Конец" tries to claim "abc" already consumed.
    # source[2]="Конец" ≠ "abc" → ATOM_MISMATCH (mismatch takes precedence over exhaustion)
    units = _mk_units(_para("Начало abc Конец"))
    chunks = _mk_chunks("Начало abc", "abc Конец")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_mismatch_before_exhaustion():
    # source has atoms at the requested position but they differ → ATOM_MISMATCH, not STREAM_EXHAUSTED
    units = _mk_units(_para("кот пёс"))
    chunks = _mk_chunks("кот рыба")  # "рыба" ≠ "пёс" at position 1
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_genuine_exhaustion():
    # source runs dry mid-chunk (no atom at all at that position) → STREAM_EXHAUSTED
    units = _mk_units(_para("кот"))  # 1 atom
    chunks = _mk_chunks("кот пёс")   # 2 atoms needed
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "STREAM_EXHAUSTED"


# ── #11: cross-kind chunk ────────────────────────────────────────────────────

def test_map_kind_ambiguous():
    units = _mk_units(_head("Глава"), _para("текст"))
    chunks = _mk_chunks("Глава текст")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code == "KIND_AMBIGUOUS"


def test_map_same_kind_two_units_ok():
    units = _mk_units(_para("а"), _para("б"))
    chunks = _mk_chunks("а б")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].unit_ids == frozenset({0, 1})
    assert spans[0].kind == "text"


# ── #15: zero-Cyrillic chunk as separate manifest chunk ──────────────────────

def test_map_zero_cyrillic_chunk_punct():
    # "—" has no Cyrillic but one atom; must map through cursor correctly
    units = _mk_units(_para("—"))
    chunks = _mk_chunks("—")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].spans == ((0, 1),)
    assert spans[0].kind == "text"


def test_map_zero_cyrillic_between_cyr_chunks():
    units = _mk_units(_para("слово — конец"))
    chunks = _mk_chunks("слово", "—", "конец")
    spans = map_chunks(units, chunks, section="01_test")
    assert len(spans) == 3
    assert spans[1].spans == ((6, 7),)


# ── #16: zero-Cyrillic chunk as unit tail ────────────────────────────────────

def test_map_zero_cyrillic_tail_of_unit():
    units = _mk_units(_para("слово..."))
    chunks = _mk_chunks("слово...")
    spans = map_chunks(units, chunks, section="01_test")
    # "слово..." is one atom
    assert len(spans[0].spans) == 1
    assert spans[0].spans[0] == (0, 8)


def test_map_zero_cyrillic_separate_tail_atom():
    units = _mk_units(_para("слово ..."))
    chunks = _mk_chunks("слово", "...")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].spans == ((0, 5),)
    assert spans[1].spans == ((6, 9),)


# ── #17: reconstruction from spans reproduces atom text ──────────────────────

def test_map_reconstruction_from_spans():
    units = _mk_units(_para("первый второй третий"))
    chunks = _mk_chunks("первый второй", "третий")
    spans = map_chunks(units, chunks, section="01_test")
    unit_texts = [u["text"] for u in units]

    for cs in spans:
        for uid in cs.unit_ids:
            src_text = unit_texts[uid]
        reconstructed = [src_text[s:e] for s, e in cs.spans]
        chunk_atom_texts = [a.text for a in atoms(chunks[int(cs.chunk_id) - 1]["text"], 0)]
        assert reconstructed == chunk_atom_texts


def test_map_reconstruction_multi_unit():
    units = _mk_units(_para("первый"), _para("второй"))
    chunks = _mk_chunks("первый", "второй")
    spans = map_chunks(units, chunks, section="01_test")

    for cs in spans:
        unit_id = next(iter(cs.unit_ids))
        src_text = units[unit_id]["text"]
        reconstructed = [src_text[s:e] for s, e in cs.spans]
        chunk_atom_texts = [a.text for a in atoms(chunks[int(cs.chunk_id) - 1]["text"], 0)]
        assert reconstructed == chunk_atom_texts


# ── #18: skipped atoms / gaps ────────────────────────────────────────────────

def test_map_skipped_atom_mismatch():
    # source: "а б в"; chunk skips "б" → "а в" → "в" at cursor pos 1 hits "б" → ATOM_MISMATCH
    units = _mk_units(_para("а б в"))
    chunks = _mk_chunks("а в")  # would need "а" then "в" but source[1]="б"
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks, section="01_test")
    assert exc.value.code in ("ATOM_MISMATCH", "TRAILING_SOURCE")


def test_map_heading_kind():
    units = _mk_units(_head("Введение"))
    chunks = _mk_chunks("Введение")
    spans = map_chunks(units, chunks, section="01_test")
    assert spans[0].kind == "heading"


# ── 6C11-3b: unvalidated manifest ID must not appear in diagnostics ───────────

_SECRET = "SYNTHETIC_SECRET"
_CYR_MARKER = "КИРИЛЛИЦА_Latin"


def _no_disclosure(exc: AnnotationError, marker: str) -> None:
    """Assert that neither the exception message nor chunk_id disclose marker."""
    assert marker not in str(exc)
    assert marker not in exc.chunk_id


def test_3b_invalid_id_secret_not_in_manifest_order():
    """MANIFEST_ORDER error must not expose the raw invalid ID."""
    chunks = [{"id": _SECRET, "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs, "expected MANIFEST_ORDER error"
    _no_disclosure(order_errs[0], _SECRET)


def test_3b_invalid_id_cyrillic_latin_not_disclosed():
    """Cyrillic+Latin marker in ID must not appear in diagnostics."""
    chunks = [{"id": _CYR_MARKER, "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    _no_disclosure(order_errs[0], _CYR_MARKER)


def test_3b_wrong_format_id_not_disclosed():
    """Wrong-format ID (single digit) must not appear in diagnostics."""
    chunks = [{"id": "1", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    assert "1" not in order_errs[0].chunk_id or order_errs[0].chunk_id.startswith("@")


def test_3b_duplicate_id_not_disclosed():
    """Duplicate ID must not appear in the second MANIFEST_ORDER error."""
    marker = "0001"  # valid format but duplicated
    chunks = [
        {"id": "0001", "n": 1, "text": "а"},
        {"id": "0001", "n": 2, "text": "б"},
    ]
    errors = validate_gates(chunks, [], section="01_test")
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    # Second error (the duplicate) must not carry the raw ID
    dup_err = order_errs[-1]
    assert dup_err.chunk_id != marker or dup_err.chunk_id.startswith("@")


def test_3b_unexpected_id_type_not_disclosed():
    """Non-string ID value must not appear in diagnostics."""
    secret_val = 99999
    chunks = [{"id": secret_val, "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [], section="01_test")
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    assert str(secret_val) not in order_errs[0].chunk_id or order_errs[0].chunk_id.startswith("@")


def test_3b_invalid_id_not_in_nfc_error():
    """NOT_NFC error for chunk with invalid ID must not expose the raw ID."""
    nfd_text = unicodedata.normalize("NFD", "ё")  # non-NFC
    chunks = [{"id": _SECRET, "n": 1, "text": nfd_text}]
    errors = validate_gates(chunks, [], section="01_test")
    nfc_errs = [e for e in errors if e.code == "NOT_NFC" and e.chunk_id != "0"]
    # May or may not raise NOT_NFC (MANIFEST_ORDER may mask it), but if it does, no disclosure
    for e in nfc_errs:
        _no_disclosure(e, _SECRET)


def test_3b_invalid_id_not_in_empty_chunk_error():
    """EMPTY_CHUNK error for chunk with invalid ID must not expose the raw ID."""
    chunks = [{"id": _SECRET, "n": 1, "text": "   "}]
    errors = validate_gates(chunks, [], section="01_test")
    empty_errs = [e for e in errors if e.code == "EMPTY_CHUNK"]
    for e in empty_errs:
        _no_disclosure(e, _SECRET)


def test_3b_valid_ids_still_appear_in_diagnostics():
    """Valid IDs (passed MANIFEST_ORDER) must still appear in permitted diagnostics."""
    nfd_text = unicodedata.normalize("NFD", "ё")
    chunks = [{"id": "0001", "n": 1, "text": nfd_text}]
    errors = validate_gates(chunks, [], section="01_test")
    nfc_errs = [e for e in errors if e.code == "NOT_NFC" and e.chunk_id]
    assert any(e.chunk_id == "0001" for e in nfc_errs), (
        "valid ID must appear in NOT_NFC diagnostics"
    )


# ── 6C11-3c: strict input schema validation ───────────────────────────────────

def _raises_annotation(fn):
    """Assert fn raises AnnotationError, not TypeError/AttributeError/etc."""
    try:
        fn()
        raise AssertionError("expected AnnotationError, got no exception")
    except AnnotationError:
        pass  # correct
    except (TypeError, AttributeError, IndexError, KeyError, ValueError) as e:
        raise AssertionError(f"unexpected {type(e).__name__}: {e}") from e


# --- Sol P2 reproduction: map_chunks with malformed chunk records ---

def test_3c_sol_chunk_text_none():
    """Reproduction: chunk text=None must raise AnnotationError, not TypeError."""
    _raises_annotation(lambda: map_chunks(
        [{"text": "a"}],
        [{"id": "0001", "n": 1, "text": None}],
    ))


def test_3c_sol_chunk_record_none():
    """Reproduction: chunk=None in list must raise AnnotationError, not AttributeError."""
    _raises_annotation(lambda: map_chunks(
        [{"text": "a"}],
        [None],
    ))


# --- Chunk structural errors ---

def test_3c_chunk_none_raises_manifest_order():
    errors = validate_gates([None], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_int_raises_manifest_order():
    errors = validate_gates([42], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_list_raises_manifest_order():
    errors = validate_gates([["id", "0001"]], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_text_none_raises_manifest_order():
    errors = validate_gates([{"id": "0001", "n": 1, "text": None}], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_text_int_raises_manifest_order():
    errors = validate_gates([{"id": "0001", "n": 1, "text": 123}], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_text_missing_raises_manifest_order():
    errors = validate_gates([{"id": "0001", "n": 1}], [], section="01_test")
    # text defaults to None → structural error
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


# --- n type validation: reject bool and float ---

def test_3c_n_true_rejected():
    """n=True must not be accepted as n=1."""
    errors = validate_gates([{"id": "0001", "n": True, "text": "а"}], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_false_rejected():
    """n=False must not be accepted."""
    errors = validate_gates([{"id": "0001", "n": False, "text": "а"}], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_float_rejected():
    """n=1.0 must not be accepted as n=1."""
    errors = validate_gates([{"id": "0001", "n": 1.0, "text": "а"}], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_none_rejected():
    errors = validate_gates([{"id": "0001", "n": None, "text": "а"}], [], section="01_test")
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_valid_int_accepted():
    """Valid int n=1 must pass."""
    errors = validate_gates([{"id": "0001", "n": 1, "text": "а"}], [], section="01_test")
    assert not any(e.code == "MANIFEST_ORDER" for e in errors)


# --- Unit structural errors ---

def test_3c_unit_none_raises_not_nfc():
    errors = validate_gates([], [None], section="01_test")
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_int_raises_not_nfc():
    errors = validate_gates([], [42], section="01_test")
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_text_none_raises_not_nfc():
    errors = validate_gates([], [{"text": None}], section="01_test")
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_text_int_raises_not_nfc():
    errors = validate_gates([], [{"text": 0}], section="01_test")
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_text_missing_raises_not_nfc():
    errors = validate_gates([], [{}], section="01_test")
    assert any(e.code == "NOT_NFC" for e in errors)


# --- No raw secret in structural errors ---

def test_3c_chunk_none_no_disclosure():
    """None chunk must not disclose repr(None) in diagnostics."""
    errors = validate_gates([None], [], section="01_test")
    for e in errors:
        assert "None" not in e.chunk_id


def test_3c_chunk_text_none_no_disclosure():
    errors = validate_gates([{"id": "0001", "n": 1, "text": None}], [], section="01_test")
    for e in errors:
        assert "None" not in str(e) or e.chunk_id in ("", "0001")


# --- Valid metadata preserved (extra fields must pass through) ---

def test_3c_valid_chunk_with_extra_metadata():
    """Extra fields on valid chunks must not cause errors."""
    chunks = [{"id": "0001", "n": 1, "text": "а", "meta": "ok", "extra": 42}]
    units = [{"text": "а", "type": "text"}]
    errors = validate_gates(chunks, units, section="01_test")
    assert errors == []


def test_3c_valid_unit_with_extra_metadata():
    units = [{"text": "а", "type": "heading", "speaker": "narrator"}]
    errors = validate_gates([], units, section="01_test")
    assert not any(e.code in ("NOT_NFC", "UNIT_INNER_PARA") for e in errors)


# ── 6C11-3d: CRLF and Unicode whitespace blank-line detection ─────────────────

def _inner_para_errors(unit_text: str) -> list[AnnotationError]:
    units = [{"text": unit_text}]
    return [e for e in validate_gates([], units, section="01_test") if e.code == "UNIT_INNER_PARA"]


def test_3d_sol_crlf_blank_line():
    """Reproduction: a\r\n\r\nb must trigger UNIT_INNER_PARA."""
    assert _inner_para_errors("a\r\n\r\nb")


def test_3d_sol_nbsp_blank_line():
    """Reproduction: a\n \nb must trigger UNIT_INNER_PARA."""
    assert _inner_para_errors("a\n \nb")


def test_3d_lf_ascii_space_blank():
    """Blank line with ASCII space triggers UNIT_INNER_PARA."""
    assert _inner_para_errors("a\n \nb")


def test_3d_lf_ascii_tab_blank():
    """Blank line with ASCII tab triggers UNIT_INNER_PARA."""
    assert _inner_para_errors("a\n\t\nb")


def test_3d_lf_mixed_space_tab_blank():
    """Blank line with mixed spaces and tabs triggers UNIT_INNER_PARA."""
    assert _inner_para_errors("a\n \t  \nb")


def test_3d_crlf_with_spaces_blank():
    """CRLF with spaces on blank line triggers UNIT_INNER_PARA."""
    assert _inner_para_errors("a\r\n   \r\nb")


def test_3d_unicode_thin_space_blank():
    """Thin space (U+2009) on blank line triggers UNIT_INNER_PARA."""
    assert _inner_para_errors("a\n \nb")


def test_3d_single_lf_no_trigger():
    """Single LF between nonempty lines must NOT trigger UNIT_INNER_PARA."""
    assert not _inner_para_errors("первая\nвторая")


def test_3d_single_crlf_no_trigger():
    """Single CRLF between nonempty lines must NOT trigger UNIT_INNER_PARA."""
    assert not _inner_para_errors("первая\r\nвторая")


def test_3d_multiple_nonempty_lines_no_trigger():
    """Several nonempty lines separated by single LF/CRLF must PASS."""
    assert not _inner_para_errors("а\nб\nв")
    assert not _inner_para_errors("а\r\nб\r\nв")


# ── 6C11-3e: SectionMap and atom provenance ──────────────────────────────────

def _mk_sm(unit_texts, chunk_texts, *, section="01_test"):
    """Helper: build SectionMap from plain text lists."""
    units = [{"text": t} for t in unit_texts]
    chunks = [{"id": f"{i+1:04d}", "n": i + 1, "text": t}
              for i, t in enumerate(chunk_texts)]
    return map_section(units, chunks, section=section)


# ── #27: Sol ambiguity — same atoms, different provenance by unit split ───────

def test_27_provenance_units_A():
    """units_A: 'a' in unit 0, 'b c' in unit 1."""
    units_A = [{"text": "a"}, {"text": "  b c"}]
    chunks = [{"id": "0001", "n": 1, "text": "a b c"}]
    sm = map_section(units_A, chunks, section="01_test")
    ca = chunk_atoms(sm, "0001")
    assert len(ca) == 3
    # Explicit provenance: 'a' from unit 0, 'b' and 'c' from unit 1
    assert ca[0] == Atom("a", 0, 0, 1)
    assert ca[1] == Atom("b", 1, 2, 3)
    assert ca[2] == Atom("c", 1, 4, 5)


def test_27_provenance_units_B():
    """units_B: 'a b' in unit 0, 'c' in unit 1."""
    units_B = [{"text": "a b"}, {"text": "    c"}]
    chunks = [{"id": "0001", "n": 1, "text": "a b c"}]
    sm = map_section(units_B, chunks, section="01_test")
    ca = chunk_atoms(sm, "0001")
    assert len(ca) == 3
    # 'a' and 'b' from unit 0, 'c' from unit 1
    assert ca[0] == Atom("a", 0, 0, 1)
    assert ca[1] == Atom("b", 0, 2, 3)
    assert ca[2] == Atom("c", 1, 4, 5)


def test_27_different_distributions_different_provenance():
    """Same chunk text 'a b c' but different unit distributions → different provenance."""
    units_A = [{"text": "a"}, {"text": "  b c"}]
    units_B = [{"text": "a b"}, {"text": "    c"}]
    chunks = [{"id": "0001", "n": 1, "text": "a b c"}]
    sm_A = map_section(units_A, chunks, section="01_test")
    sm_B = map_section(units_B, chunks, section="01_test")
    ca_A = chunk_atoms(sm_A, "0001")
    ca_B = chunk_atoms(sm_B, "0001")
    # Different unit_id sequences
    assert [a.unit_id for a in ca_A] != [a.unit_id for a in ca_B]
    # Different (unit_id, start, end) triples
    provA = [(a.unit_id, a.start, a.end) for a in ca_A]
    provB = [(a.unit_id, a.start, a.end) for a in ca_B]
    assert provA != provB


def test_27_same_input_same_provenance():
    """Same input always produces the same atom provenance (determinism)."""
    units_A = [{"text": "a"}, {"text": "  b c"}]
    chunks = [{"id": "0001", "n": 1, "text": "a b c"}]
    sm1 = map_section(units_A, chunks, section="01_test")
    sm2 = map_section(units_A, chunks, section="01_test")
    assert chunk_atoms(sm1, "0001") == chunk_atoms(sm2, "0001")


# ── #28: independent maps retain atom texts; signature check; UNKNOWN_CHUNK ──

def test_28_independent_maps_retain_texts():
    """Independent SectionMaps for 'abc' and 'xyz' retain respective atom texts."""
    sm_abc = _mk_sm(["abc def"], ["abc", "def"])
    sm_xyz = _mk_sm(["xyz uvw"], ["xyz", "uvw"])
    assert chunk_atoms(sm_abc, "0001")[0].text == "abc"
    assert chunk_atoms(sm_xyz, "0001")[0].text == "xyz"
    # Streams are independent — no cross-contamination
    assert sm_abc.stream[0].text == "abc"
    assert sm_xyz.stream[0].text == "xyz"


def test_28_chunk_atoms_signature():
    """chunk_atoms() must accept exactly (section_map, chunk_id)."""
    import inspect
    sig = inspect.signature(chunk_atoms)
    params = list(sig.parameters.keys())
    assert params == ["section_map", "chunk_id"], f"unexpected params: {params}"


def test_28_unknown_chunk_id_raises():
    """Unknown chunk_id → AnnotationError('UNKNOWN_CHUNK')."""
    sm = _mk_sm(["слово"], ["слово"])
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, "9999")
    assert exc.value.code == "UNKNOWN_CHUNK"


# ── #29: manually specified provenance literals; fuzz boundary check ──────────

def test_29_provenance_three_chunks():
    """Expected provenance literals for 3 chunks in one unit."""
    sm = _mk_sm(["а б в"], ["а б", "в"])
    ca1 = chunk_atoms(sm, "0001")
    ca2 = chunk_atoms(sm, "0002")
    assert ca1 == (Atom("а", 0, 0, 1), Atom("б", 0, 2, 3))
    assert ca2 == (Atom("в", 0, 4, 5),)


def test_29_provenance_multi_unit():
    """Expected provenance literals spanning two units."""
    sm = _mk_sm(["первый", "второй"], ["первый", "второй"])
    assert chunk_atoms(sm, "0001") == (Atom("первый", 0, 0, 6),)
    assert chunk_atoms(sm, "0002") == (Atom("второй", 1, 0, 6),)


def test_29_fuzz_atom_text_matches_unit_source():
    """Fuzz: every atom from chunk_atoms() matches its source unit text exactly."""
    units = [{"text": "один два три"}, {"text": "четыре пять"}]
    chunks = [
        {"id": "0001", "n": 1, "text": "один два"},
        {"id": "0002", "n": 2, "text": "три четыре"},
        {"id": "0003", "n": 3, "text": "пять"},
    ]
    sm = map_section(units, chunks, section="01_test")
    for cid in ("0001", "0002", "0003"):
        for atom in chunk_atoms(sm, cid):
            unit_text = units[atom.unit_id]["text"]
            # Text slice must match exactly (no unitmap tokenizer used as reference)
            assert unit_text[atom.start:atom.end] == atom.text
            # Whitespace boundary: position before start must be whitespace or start of text
            assert atom.start == 0 or unit_text[atom.start - 1].isspace()
            # Whitespace boundary: position at end must be whitespace or end of text
            assert atom.end == len(unit_text) or unit_text[atom.end].isspace()


def test_29_provenance_with_punctuation_atom():
    """Non-Cyrillic atom (em-dash) has correct provenance."""
    sm = _mk_sm(["слово — конец"], ["слово", "—", "конец"])
    assert chunk_atoms(sm, "0002") == (Atom("—", 0, 6, 7),)


# ── #30: AST guard — SectionMap construction restrictions ────────────────────

def test_30_ast_no_sectionmap_construction_outside_unitmap():
    """No runtime SectionMap() construction outside unitmap.py."""
    import ast
    import pathlib

    repo_root = pathlib.Path(__file__).parent.parent
    unitmap_path = repo_root / "src" / "audiobook" / "unitmap.py"

    violations = []
    all_py = (
        list((repo_root / "src").rglob("*.py"))
        + list((repo_root / "tests").rglob("*.py"))
    )

    for path in all_py:
        if path == unitmap_path:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "SectionMap":
                rel = path.relative_to(repo_root)
                violations.append(
                    f"{rel}:{node.lineno}: rule 1 — SectionMap() constructed outside unitmap.py"
                )

    assert not violations, "AST guard violations:\n" + "\n".join(violations)


def test_30_ast_no_dataclasses_replace_in_unitmap_importers():
    """No dataclasses.replace() calls in files that import from unitmap."""
    import ast
    import pathlib

    repo_root = pathlib.Path(__file__).parent.parent
    unitmap_path = repo_root / "src" / "audiobook" / "unitmap.py"
    all_py = (
        list((repo_root / "src").rglob("*.py"))
        + list((repo_root / "tests").rglob("*.py"))
    )

    violations = []
    for path in all_py:
        if path == unitmap_path:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        imports_unitmap = any(
            isinstance(n, ast.ImportFrom)
            and n.module is not None
            and "unitmap" in n.module
            for n in ast.walk(tree)
        )
        if not imports_unitmap:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # dataclasses.replace(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "replace"
                and isinstance(func.value, ast.Name)
                and func.value.id == "dataclasses"
            ):
                rel = path.relative_to(repo_root)
                violations.append(
                    f"{rel}:{node.lineno}: rule 3 — dataclasses.replace() in unitmap importer"
                )

    assert not violations, "AST guard violations:\n" + "\n".join(violations)


def test_30_ast_chunk_atoms_no_tokenization():
    """chunk_atoms() must not contain tokenization or regex calls."""
    import ast
    import pathlib

    unitmap_path = (
        pathlib.Path(__file__).parent.parent / "src" / "audiobook" / "unitmap.py"
    )
    source = unitmap_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    fn_node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "chunk_atoms"),
        None,
    )
    assert fn_node is not None, "chunk_atoms() not found in unitmap.py"

    forbidden_calls = {"atoms", "_tokens", "_CYR", "re", "finditer", "findall", "search"}
    violations = []
    for node in ast.walk(fn_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in forbidden_calls:
            violations.append(f"line {node.lineno}: forbidden call .{name}() in chunk_atoms()")

    assert not violations, "\n".join(violations)


# ── #31: map_chunks(, section="01_test") == list(map_section(..., section="01_test").spans) ────────────────────────

def test_31_map_chunks_equals_map_section_spans():
    """map_chunks(, section="01_test") elements and order equal map_section(..., section="01_test").spans."""
    units = [{"text": "а б в г"}, {"text": "д е"}]
    chunks = [
        {"id": "0001", "n": 1, "text": "а б"},
        {"id": "0002", "n": 2, "text": "в г"},
        {"id": "0003", "n": 3, "text": "д е"},
    ]
    result_map_chunks = map_chunks(units, chunks, section="01_test")
    sm = map_section(units, chunks, section="01_test")
    assert result_map_chunks == list(sm.spans)


def test_31_map_chunks_equals_map_section_single():
    """Single-chunk case: map_chunks == list(map_section.spans)."""
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    assert map_chunks(units, chunks, section="01_test") == list(map_section(units, chunks, section="01_test").spans)


# ── SectionMap structure and chunk_atoms basics ───────────────────────────────

def test_sectionmap_is_frozen():
    sm = _mk_sm(["а"], ["а"])
    with pytest.raises((AttributeError, TypeError)):
        sm.section = "other"  # type: ignore[misc]


def test_sectionmap_section_field():
    sm = _mk_sm(["а"], ["а"], section="03_test")
    assert sm.section == "03_test"


def test_sectionmap_stream_contains_all_atoms():
    sm = _mk_sm(["а б"], ["а", "б"])
    assert len(sm.stream) == 2
    assert sm.stream[0].text == "а"
    assert sm.stream[1].text == "б"


def test_sectionmap_spans_count_matches_chunks():
    sm = _mk_sm(["а б в"], ["а", "б", "в"])
    assert len(sm.spans) == 3


def test_source_atoms_single_implementation():
    """source_atoms() returns all atoms in unit order."""
    units = [{"text": "а б"}, {"text": "в"}]
    sa = source_atoms(units)
    assert len(sa) == 3
    assert sa[0] == Atom("а", 0, 0, 1)
    assert sa[1] == Atom("б", 0, 2, 3)
    assert sa[2] == Atom("в", 1, 0, 1)


def test_source_atoms_matches_map_section_stream():
    """source_atoms() matches the stream stored in SectionMap."""
    units = [{"text": "один два"}, {"text": "три"}]
    chunks = [{"id": "0001", "n": 1, "text": "один два три"}]
    sm = map_section(units, chunks, section="01_test")
    assert sm.stream == source_atoms(units)


# ── #32: UNKNOWN_CHUNK diagnostic privacy; section validation (BLOCKED) ───────

def _mk_sm_one(unit_text: str, chunk_text: str, section: str = "01_test") -> "SectionMap":
    units = [{"text": unit_text}]
    chunks = [{"id": "0001", "n": 1, "text": chunk_text}]
    return map_section(units, chunks, section=section)


def test_32_unknown_chunk_no_disclosure():
    """Sol P1 repro: UNKNOWN_CHUNK must not contain the caller-supplied unknown ID."""
    sm = _mk_sm_one("а", "а")
    secret = "SYNTHETIC_SECRET"
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, secret)
    assert exc.value.code == "UNKNOWN_CHUNK"
    assert secret not in str(exc.value)
    assert secret not in exc.value.chunk_id
    assert secret not in exc.value.detail


def test_32_unknown_chunk_latin_cyrillic_markers():
    """Unknown ID with Latin and Cyrillic secret markers must not appear in diagnostics."""
    sm = _mk_sm_one("слово", "слово")
    secret = "СЕКРЕТ_secret_42"
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, secret)
    assert exc.value.code == "UNKNOWN_CHUNK"
    assert secret not in str(exc.value)
    assert secret not in exc.value.chunk_id


def test_32_unknown_chunk_check_attrs():
    """AnnotationError attributes must not carry the unknown chunk ID."""
    sm = _mk_sm_one("б", "б")
    unknown = "UNKNOWN_ID_DO_NOT_LEAK"
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, unknown)
    err = exc.value
    assert err.chunk_id == ""
    assert err.detail == ""
    assert unknown not in str(err)


def test_32_unknown_chunk_non_str_id_no_disclosure():
    """Non-str chunk_id: comparison fails silently, UNKNOWN_CHUNK raised without disclosure."""
    sm = _mk_sm_one("в", "в")
    non_str_id = object()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, non_str_id)  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"
    assert exc.value.chunk_id == ""


def test_32_unknown_chunk_known_id_still_works():
    """chunk_atoms() must still return the correct slice for known chunk IDs."""
    sm = _mk_sm_one("раз два", "раз два")
    result = chunk_atoms(sm, "0001")
    assert len(result) == 2
    assert result[0].text == "раз"
    assert result[1].text == "два"


def test_32_section_dict_rejected():
    """Non-string section (dict) raises AnnotationError('INVALID_SECTION')."""
    units = [{"text": "а"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section={"key": "value"})  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_SECTION"


def test_32_section_none_rejected():
    """Non-string section (None) raises AnnotationError('INVALID_SECTION')."""
    units = [{"text": "а"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section=None)  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_SECTION"


# ── #33: INVALID_SECTION diagnostic privacy ───────────────────────────────────

class _Explosive:
    """An object whose __str__, __repr__, __eq__, and __hash__ all raise.

    Used to verify no untrusted dunder is called on invalid section values.
    """
    def __str__(self):
        raise RuntimeError("__str__ invoked on untrusted value")

    def __repr__(self):
        raise RuntimeError("__repr__ invoked on untrusted value")

    def __eq__(self, other):
        raise RuntimeError("__eq__ invoked on untrusted value")

    def __hash__(self):
        raise RuntimeError("__hash__ invoked on untrusted value")


def test_33_validate_section_empty_raises():
    """validate_section('') raises INVALID_SECTION with detail='empty'."""
    with pytest.raises(AnnotationError) as exc:
        validate_section("")
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert e.detail == "empty"
    assert e.section is None
    assert e.chunk_id is None


def test_33_validate_section_none_raises():
    """validate_section(None) raises INVALID_SECTION; detail='not_str'; section field is None."""
    none_val = None
    with pytest.raises(AnnotationError) as exc:
        validate_section(none_val)
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert e.detail == "not_str"
    assert e.section is None
    assert e.chunk_id is None


def test_33_validate_section_dict_raises():
    """validate_section with dict raises INVALID_SECTION; dict is not retained."""
    bad = {"key": "value"}
    with pytest.raises(AnnotationError) as exc:
        validate_section(bad)
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert e.detail == "not_str"
    assert e.section is not bad
    assert e.chunk_id is not bad


def test_33_explosive_object_no_dunder_calls():
    """Objects with raising __str__/__repr__/__eq__ must not trigger them in validate_section."""
    explosive = _Explosive()
    with pytest.raises(AnnotationError) as exc:
        validate_section(explosive)
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert e.detail == "not_str"
    assert e.section is not explosive
    assert e.chunk_id is not explosive


def test_33_explosive_object_via_map_section():
    """Explosive section object passed to map_section: no dunder invoked."""
    units = [{"text": "а"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    explosive = _Explosive()
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section=explosive)  # type: ignore[arg-type]
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert e.section is not explosive
    assert e.chunk_id is not explosive


def test_33_invalid_str_no_secret_in_diagnostic():
    """An invalid non-empty string must not appear in exception diagnostics."""
    secret = "SECRET_MARKER_MUST_NOT_APPEAR"
    bad_section = f"INVALID_{secret}_BAD!"
    with pytest.raises(AnnotationError) as exc:
        validate_section(bad_section)
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert secret not in str(e)
    assert secret not in repr(e)
    assert not any(secret in str(a) for a in e.args)
    for v in vars(e).values():
        if isinstance(v, str):
            assert secret not in v


def test_33_too_long_section_no_disclosure():
    """A too-long section string's content must not appear in diagnostics."""
    secret = "SECRETMARKER"
    bad = "01_" + secret + "_" + "x" * 60  # > 64 chars
    with pytest.raises(AnnotationError) as exc:
        validate_section(bad)
    e = exc.value
    assert e.detail == "too_long"
    assert secret not in str(e)
    assert secret not in repr(e)
    for v in vars(e).values():
        if isinstance(v, str):
            assert secret not in v


def test_33_exception_chaining_no_cause():
    """Inside active except block: __cause__ is None, __suppress_context__ is True."""
    try:
        raise RuntimeError("outer exception — must not leak")
    except RuntimeError:
        with pytest.raises(AnnotationError) as exc:
            validate_section({"bad": "section"})
    e = exc.value
    assert e.__cause__ is None
    assert e.__suppress_context__ is True
    # e.__context__ is the RuntimeError — that is acceptable; we do not require it to be None


def test_33_invalid_section_message_no_section_field():
    """str(AnnotationError) for INVALID_SECTION must not contain 'section=' or 'chunk='."""
    with pytest.raises(AnnotationError) as exc:
        validate_section("bad-format!")
    e = exc.value
    msg = str(e)
    assert "section=" not in msg
    assert "chunk=" not in msg
    assert "bad_format" in msg   # detail IS included — it is a safe constant


# ── #34: INVALID_SECTION precedence over malformed secondary inputs ────────────

def test_34_invalid_section_before_malformed_validate_gates():
    """validate_gates: section validated before inspecting units/chunks."""
    with pytest.raises(AnnotationError) as exc:
        validate_gates([{"BAD": True}], [{"BROKEN": True}], section={"bad": "dict"})
    assert exc.value.code == "INVALID_SECTION"


def test_34_invalid_section_before_malformed_check_gates():
    """check_gates: section validated before inspecting units/chunks."""
    with pytest.raises(AnnotationError) as exc:
        check_gates([{"BAD": True}], [{"BROKEN": True}], section=42)
    assert exc.value.code == "INVALID_SECTION"


def test_34_invalid_section_before_malformed_map_section():
    """map_section: section validated before cursor processing."""
    with pytest.raises(AnnotationError) as exc:
        map_section([{"BROKEN": True}], [{"BAD": True}], section=None)  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_SECTION"


def test_34_invalid_section_before_malformed_map_chunks():
    """map_chunks: section validated before cursor processing."""
    with pytest.raises(AnnotationError) as exc:
        map_chunks([{"BROKEN": True}], [{"BAD": True}], section="bad-format!")
    assert exc.value.code == "INVALID_SECTION"


def test_34_invalid_section_before_malformed_annotate_units():
    """annotate_units: section validated before any processing."""
    from audiobook.unitmap import annotate_units
    with pytest.raises(AnnotationError) as exc:
        annotate_units([{"BROKEN": True}], [{"BAD": True}], section={"x": 1})
    assert exc.value.code == "INVALID_SECTION"


# ── #35: 58 production section identifiers ────────────────────────────────────

_PRODUCTION_SECTIONS = [
    "00_section", "01_ty_ne_poloman", "02_soderzhanie", "03_otzyvy",
    "04_dlya_kogo_eta_kniga", "05_kak_chitat_etu_knigu",
    "06_kak_obrashchatsya_s_etoj_knigoj_chtoby_n",
    "07_vvedenie_tvoya_zhizn_eto_lift_kuda_ty_ed",
    "08_glava_1_zver_vnutri_nas_instinkty_eto_ne",
    "09_glava_2_roditelskie_golosa_ili_otkuda_be",
    "10_glava_3_maski_kotorye_my_nosim_shest_spo",
    "11_glava_4_bolevoe_telo_vulkan_kotoryj_drem",
    "12_glava_5_drevo_boli_karta_tvoikh_glubin",
    "13_glava_6_vnutrennij_rebenok_tot_kto_do_si",
    "14_glava_7_vnutrennij_podrostok_stroitel_ma",
    "15_glava_8_vnutrennij_vzroslyj_tot_kto_mozh",
    "16_glava_9_vnutrennij_mudrets_tikhij_golos_",
    "17_glava_10_nejrobiologiya_travmy_pochemu_t",
    "18_glava_11_pochemu_my_teryaem_sebya_dissot",
    "19_glava_12_pervyj_navyk_zamechat_volnu",
    "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu",
    "21_glava_14_pyat_klyuchej_kak_otkryt_zakryt",
    "22_glava_15_somaticheskaya_rabota_istseleni",
    "23_glava_16_rabota_s_bolevym_telom_kak_lish",
    "24_glava_17_vozvrashchenie_v_telo_istseleni",
    "25_glava_18_koleso_balansa_rentgen_tvoej_du",
    "26_glava_19_dnevnik_myslej_pojmat_podrostka",
    "27_glava_20_povedencheskij_eksperiment_prov",
    "28_glava_21_vstrecha_s_tenyu_pochemu_nas_be",
    "29_glava_22_zavisimosti_kak_my_pytaemsya_za",
    "30_glava_23_karta_istseleniya_poshagovaya_i",
    "31_glava_24_snyatie_maski_vstrecha_s_tem_kt",
    "32_glava_25_teoriya_privyazannosti_kak_nas_",
    "33_glava_26_vstrecha_dvukh_vselennykh_kak_n",
    "34_glava_27_kak_byt_s_maskoj_partnyora_stra",
    "35_glava_28_tri_istorii_istseleniya_alena_l",
    "36_glava_29_kak_ponyat_chto_vzroslyj_prosnu",
    "37_glava_30_prednaznachenie_kak_tvoj_dar_na",
    "38_glava_31_ekzistentsialnyj_sloj_chto_nelz",
    "39_glava_32_put_geroya_tvoya_zhizn_kak_mif",
    "40_glava_33_glubokaya_tekhnika_integratsii_",
    "41_glava_34_ezhednevnye_praktiki_i_ritualy_",
    "42_glava_35_glavnoe_chto_nuzhno_pomnit",
    "43_finalnaya_integratsiya",
    "44_vmesto_poslesloviya_pismo_tebe",
    "45_pismo_sebe_praktika",
    "46_ob_avtore",
    "47_bonusnye_materialy_k_knige_ty_ne_poloman",
    "48_prilozhenie_1_karta_geroya_bystraya_samo",
    "49_prilozhenie_2_polnaya_karta_emotsij_chuv",
    "50_prilozhenie_3_kratkaya_karta_masok",
    "51_kak_tantsuyut_maski_polnaya_kartina",
    "52_lichnost_za_2_minuty",
    "53_glossarij",
    "54_blagodarnosti",
    "55_spisok_literatury_i_istochnikov",
    "56_chem_eta_sistema_otlichaetsya",
    "57_kniga_prodolzhaetsya",
]


@pytest.mark.parametrize("section_id", _PRODUCTION_SECTIONS)
def test_35_production_section_id_valid(section_id):
    """All 58 production section identifiers pass _section_violation (return None)."""
    assert _section_violation(section_id) is None


# ── #36: validate_section public API — valid and invalid inputs ───────────────

@pytest.mark.parametrize("valid", [
    "01_test",
    "00_section",
    "57_kniga_prodolzhaetsya",
    "16_glava_9_vnutrennij_mudrets_tikhij_golos_",  # trailing underscore (historical)
    "32_glava_25_teoriya_privyazannosti_kak_nas_",
    "99_z",
    "01_a0",
    "01_" + "a" * 61,  # len == 64, within limit
])
def test_36_validate_section_valid(valid):
    """validate_section does not raise for valid section identifiers."""
    validate_section(valid)  # must not raise


@pytest.mark.parametrize("invalid,expected_violation", [
    ("", "empty"),
    (None, "not_str"),
    (42, "not_str"),
    ({}, "not_str"),
    ([], "not_str"),
    ("bad section!", "bad_format"),    # space and !
    ("no_digit_prefix", "bad_format"), # no NN_ prefix
    ("1_one_digit", "bad_format"),     # only 1 digit
    ("AB_uppercase", "bad_format"),    # uppercase
    ("01_has__double", "bad_format"),  # consecutive underscores
    ("01_" + "a" * 62, "too_long"),   # len == 65
])
def test_36_validate_section_invalid(invalid, expected_violation):
    """validate_section raises INVALID_SECTION with the correct violation code."""
    with pytest.raises(AnnotationError) as exc:
        validate_section(invalid)
    assert exc.value.code == "INVALID_SECTION"
    assert exc.value.detail == expected_violation


# ── #37: INVALID_SECTION exception structure ──────────────────────────────────

def test_37_invalid_section_error_attributes():
    """INVALID_SECTION: code, section=None, chunk_id=None, detail is violation code."""
    with pytest.raises(AnnotationError) as exc:
        validate_section("bad!")
    e = exc.value
    assert e.code == "INVALID_SECTION"
    assert e.reason == "INVALID_SECTION"
    assert e.section is None
    assert e.chunk_id is None
    assert e.mismatch_idx == -1
    assert e.detail in ("not_str", "empty", "too_long", "bad_format")


def test_37_invalid_section_args_no_untrusted():
    """e.args[0] for INVALID_SECTION must be a plain string with no untrusted data."""
    secret = "ARGTEST_SECRET"
    with pytest.raises(AnnotationError) as exc:
        validate_section(f"bad_{secret}!")  # bad_format; secret not stored
    e = exc.value
    assert len(e.args) == 1
    assert isinstance(e.args[0], str)
    assert secret not in e.args[0]
    assert "INVALID_SECTION" in e.args[0]


def test_37_invalid_section_vars_safe():
    """vars(e) for INVALID_SECTION must not contain the invalid value."""
    bad_val = object()
    with pytest.raises(AnnotationError) as exc:
        validate_section(bad_val)
    e = exc.value
    for field_val in vars(e).values():
        assert field_val is not bad_val


def test_37_valid_section_stored_in_subsequent_errors():
    """After validate_section passes, section is stored in subsequent AnnotationError."""
    units = [{"text": "а"}]
    chunks = [{"id": "0001", "n": 1, "text": "MISMATCH"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section="01_test")
    assert exc.value.section == "01_test"


# ── #38: AnnotationError constructor boundary sanitization (T15-6C11-3f1b) ───

import inspect
import logging


def test_38_constructor_signature_matches_baseline():
    """AnnotationError.__init__ signature must match the 06f3ffd baseline exactly."""
    sig = inspect.signature(AnnotationError.__init__)
    params = sig.parameters
    assert list(params.keys()) == ["self", "code", "section", "chunk_id", "detail", "mismatch_idx"]
    assert str(params["section"].annotation) == "str"
    assert str(params["chunk_id"].annotation) == "str"
    assert params["section"].default == ""
    assert params["chunk_id"].default == ""
    assert params["detail"].default == ""
    assert params["mismatch_idx"].default == -1


def test_38_dict_section_not_retained():
    """Direct AnnotationError construction with a dict section must not retain it."""
    secret = {"SYNTHETIC_SECRET": 1}
    e = AnnotationError("TEST", section=secret)  # type: ignore[arg-type]
    assert e.section is not secret
    assert e.section is None
    # Must not appear in any string representation
    assert "SYNTHETIC_SECRET" not in str(e)
    assert "SYNTHETIC_SECRET" not in repr(e)
    assert all("SYNTHETIC_SECRET" not in str(a) for a in e.args)


def test_38_hostile_section_no_dunder_calls():
    """Hostile section object whose dunders raise must not cause AnnotationError to crash."""
    class _Hostile:
        def __bool__(self): raise RuntimeError("__bool__ invoked")
        def __str__(self): raise RuntimeError("__str__ invoked")
        def __repr__(self): raise RuntimeError("__repr__ invoked")
        def __eq__(self, other): raise RuntimeError("__eq__ invoked")
        def __hash__(self): raise RuntimeError("__hash__ invoked")

    obj = _Hostile()
    # Must not raise during construction
    e = AnnotationError("TEST", section=obj)  # type: ignore[arg-type]
    assert e.section is None


def test_38_invalid_section_not_retained_by_identity():
    """Invalid section object must not be reachable via any exception attribute."""
    bad = object()
    e = AnnotationError("SOME_CODE", section=bad)  # type: ignore[arg-type]
    for v in vars(e).values():
        assert v is not bad
    for a in e.args:
        assert a is not bad


def test_38_invalid_section_no_leak_in_str_repr_args():
    """str/repr/args for constructor with dict section must not expose the dict."""
    secret_key = "CONSTRUCTOR_BOUNDARY_SECRET"
    e = AnnotationError("LEAK_CHECK", section={secret_key: 99})  # type: ignore[arg-type]
    combined = str(e) + repr(e) + " ".join(str(a) for a in e.args)
    assert secret_key not in combined


def test_38_invalid_section_no_leak_in_logging(caplog):
    """Logging an AnnotationError with an invalid section must not expose the value."""
    secret_key = "LOG_LEAK_SECRET"
    e = AnnotationError("LOG_CHECK", section={secret_key: 1})  # type: ignore[arg-type]
    with caplog.at_level(logging.ERROR):
        logging.error("caught: %s", e)
    assert secret_key not in caplog.text


def test_38_valid_section_retained_by_constructor():
    """Valid section string must be stored unchanged when passed directly."""
    e = AnnotationError("SOME_CODE", section="01_test", chunk_id="0001")
    assert e.section == "01_test"
    assert e.chunk_id == "0001"


def test_38_chunk_id_dict_not_retained():
    """Non-string chunk_id must not be retained."""
    bad = {"chunk": "secret"}
    e = AnnotationError("SOME_CODE", chunk_id=bad)  # type: ignore[arg-type]
    assert e.chunk_id is not bad
    assert e.chunk_id is None


# ── #39: chunk_atoms() hostile/spoofed chunk_id boundary (T15-6C11-3f1c) ─────

def _single_chunk_sm() -> "SectionMap":
    """Return a minimal SectionMap with one known chunk '0001'."""
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    return map_section(units, chunks, section="01_test")


def test_39_hostile_eq_raises_unknown_chunk():
    """Hostile __eq__ must trigger UNKNOWN_CHUNK, not propagate the exception."""
    class _Hostile:
        def __eq__(self, other): raise RuntimeError("SYNTHETIC_SECRET")
        def __str__(self): raise RuntimeError("__str__")
        def __repr__(self): raise RuntimeError("__repr__")
        def __bool__(self): raise RuntimeError("__bool__")
        def __hash__(self): return 0

    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, _Hostile())  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"


def test_39_spoof_eq_raises_unknown_chunk():
    """Spoofed __eq__ returning True must still raise UNKNOWN_CHUNK."""
    class _Spoof:
        def __eq__(self, other): return True
        def __hash__(self): return 0

    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, _Spoof())  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"


def test_39_none_raises_unknown_chunk():
    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, None)  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"


def test_39_int_raises_unknown_chunk():
    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, 1)  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"


def test_39_bool_raises_unknown_chunk():
    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, True)  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"


def test_39_bytes_raises_unknown_chunk():
    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, b"0001")  # type: ignore[arg-type]
    assert exc.value.code == "UNKNOWN_CHUNK"


def test_39_malformed_string_raises_unknown_chunk():
    """Unknown string ID raises UNKNOWN_CHUNK without disclosing the value."""
    secret = "MALFORMED_SECRET_ID"
    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, secret)
    e = exc.value
    assert e.code == "UNKNOWN_CHUNK"
    assert secret not in str(e)
    assert secret not in repr(e)
    assert all(secret not in str(a) for a in e.args)
    assert e.chunk_id != secret


def test_39_no_secret_in_exception_attrs():
    """Non-string chunk_id secret must not appear in any exception attribute."""
    secret_key = "CHUNK_BOUNDARY_SECRET"
    sm = _single_chunk_sm()
    with pytest.raises(AnnotationError) as exc:
        chunk_atoms(sm, {secret_key: 1})  # type: ignore[arg-type]
    e = exc.value
    combined = str(e) + repr(e) + " ".join(str(a) for a in e.args)
    assert secret_key not in combined
    for v in vars(e).values():
        assert secret_key not in str(v)


def test_39_valid_id_returns_atoms():
    """Known valid chunk_id returns exactly the stored atom slice."""
    sm = _single_chunk_sm()
    result = chunk_atoms(sm, "0001")
    assert len(result) == 1
    assert result[0].text == "слово"


# ── #40: chunk_atoms() suppresses exception context for unknown string IDs ────

import traceback


def test_40_unknown_string_id_suppresses_context():
    """Unknown string ID inside active except block must not leak the secret."""
    secret = "SYNTHETIC_SECRET_UNKNOWN_ID"
    sm = _single_chunk_sm()

    try:
        raise ValueError(secret)
    except ValueError:
        with pytest.raises(AnnotationError) as exc:
            chunk_atoms(sm, secret)

    e = exc.value
    assert e.code == "UNKNOWN_CHUNK"
    assert e.__cause__ is None
    assert e.__suppress_context__ is True

    tb_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    assert secret not in tb_text

    assert e.chunk_id != secret
    assert all(secret not in str(a) for a in e.args)
    assert secret not in str(e)


def test_40_unknown_string_no_logging_leak(caplog):
    """Logging an UNKNOWN_CHUNK from inside an except block must not expose secret."""
    import logging as _logging
    secret = "LOG_CONTEXT_LEAK_SECRET"
    sm = _single_chunk_sm()

    try:
        raise ValueError(secret)
    except ValueError:
        try:
            chunk_atoms(sm, secret)
        except AnnotationError as e:
            with caplog.at_level(_logging.ERROR):
                _logging.error("caught: %s", e)

    assert secret not in caplog.text


def test_40_known_id_still_works_after_fix():
    """Valid chunk_id still returns exact atom slice after context-suppression fix."""
    sm = _single_chunk_sm()
    result = chunk_atoms(sm, "0001")
    assert len(result) == 1
    assert result[0].text == "слово"


# ── #41: _validate_chunk_span integrity checks (T15-6C11-3g) ─────────────────

import audiobook.unitmap as _unitmap
from unittest.mock import patch


def _base_sm_and_meta():
    """Return (sm, stream, unit_kinds) for a 2-unit, 2-chunk section."""
    units = [{"text": "слово раз"}, {"text": "слово два"}]
    chunks = [
        {"id": "0001", "n": 1, "text": "слово раз"},
        {"id": "0002", "n": 2, "text": "слово два"},
    ]
    sm = map_section(units, chunks, section="01_test")
    unit_kinds = ["text", "text"]
    return sm, sm.stream, unit_kinds


# ── Sol P2 mandatory reproductions ───────────────────────────────────────────

def test_41_sol_injection_atom_end_plus_one():
    """Sol P2: atom_end + 1 raises SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(
        chunk_id=cs.chunk_id,
        atom_start=cs.atom_start,
        atom_end=cs.atom_end + 1,  # out-of-bounds / overlap
        spans=cs.spans,
        unit_ids=cs.unit_ids,
        kind=cs.kind,
        end_modes=None,
    )
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_sol_injection_empty_spans():
    """Sol P2: spans=() raises SPAN_STREAM_MISMATCH (not silently accepted)."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(
        chunk_id=cs.chunk_id,
        atom_start=cs.atom_start,
        atom_end=cs.atom_end,
        spans=(),  # missing source intervals
        unit_ids=cs.unit_ids,
        kind=cs.kind,
        end_modes=None,
    )
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_sol_injection_extra_span():
    """Sol P2: extra span raises SPAN_STREAM_MISMATCH (not IndexError)."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    extra = cs.spans + ((0, 0),)
    bad = ChunkSpan(
        chunk_id=cs.chunk_id,
        atom_start=cs.atom_start,
        atom_end=cs.atom_end,
        spans=extra,  # extra interval
        unit_ids=cs.unit_ids,
        kind=cs.kind,
        end_modes=None,
    )
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


# ── Additional injections ─────────────────────────────────────────────────────

def test_41_bad_atom_start_raises():
    """atom_start < 0 raises SPAN_STREAM_MISMATCH: does not match expected_start=0."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, -1, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_reversed_range_raises():
    """Reversed atom_start/atom_end raises SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, cs.atom_end, cs.atom_start, cs.spans, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_gap_between_chunks_raises():
    """atom_start != expected_start raises SPAN_STREAM_MISMATCH (gap)."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[1]
    # Second chunk normally starts at spans[0].atom_end, present expected_start as 0 (gap)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(cs, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_overlapping_range_raises():
    """atom_end beyond stream length raises SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[-1]
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, len(stream) + 5, cs.spans, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, cs.atom_start, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_wrong_unit_ids_raises():
    """Incorrect unit_ids raises SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, frozenset({99}), cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_wrong_kind_raises():
    """Incorrect kind raises SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, "heading", None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_wrong_offsets_raises():
    """Corrupted span offsets raise SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    corrupted = ((999, 999),) + cs.spans[1:]
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, corrupted, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_nonzero_end_modes_raises():
    """Non-None end_modes raises SPAN_STREAM_MISMATCH."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, frozenset({"open_end"}))
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_no_indexerror_on_oob():
    """Out-of-bounds atom_end raises SPAN_STREAM_MISMATCH, never IndexError."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, 0, len(stream) + 100, cs.spans, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


# ── Integration: injected corruption through map_section via monkeypatch ──────

def _make_bad_cs_factory(corrupt_fn):
    """Return a ChunkSpan factory that applies corrupt_fn to the produced span."""
    original = _unitmap.ChunkSpan
    call_count = [0]

    def patched(**kwargs):
        cs = original(**kwargs)
        call_count[0] += 1
        if call_count[0] == 1:
            cs = corrupt_fn(cs)
        return cs

    return patched


def test_41_integration_atom_end_plus_one(monkeypatch):
    """map_section with injected atom_end+1 raises SPAN_STREAM_MISMATCH."""
    def corrupt(cs):
        return ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end + 1, cs.spans, cs.unit_ids, cs.kind, None)
    monkeypatch.setattr(_unitmap, "ChunkSpan", _make_bad_cs_factory(corrupt))
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section="01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_integration_empty_spans(monkeypatch):
    """map_section with injected spans=() raises SPAN_STREAM_MISMATCH."""
    def corrupt(cs):
        return ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, (), cs.unit_ids, cs.kind, None)
    monkeypatch.setattr(_unitmap, "ChunkSpan", _make_bad_cs_factory(corrupt))
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section="01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_41_integration_extra_span(monkeypatch):
    """map_section with injected extra span raises SPAN_STREAM_MISMATCH, not IndexError."""
    def corrupt(cs):
        return ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans + ((0, 0),), cs.unit_ids, cs.kind, None)
    monkeypatch.setattr(_unitmap, "ChunkSpan", _make_bad_cs_factory(corrupt))
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section="01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


# ── Valid mappings remain accepted ────────────────────────────────────────────

def test_41_valid_multi_unit_accepted():
    """Valid multi-unit span passes _validate_chunk_span."""
    units = [{"text": "слово"}, {"text": "раз"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово раз"}]
    sm = map_section(units, chunks, section="01_test")
    assert len(sm.spans) == 1
    assert len(sm.spans[0].unit_ids) == 2


def test_41_valid_zero_cyrillic_accepted():
    """Valid zero-Cyrillic (punctuation) chunk passes validation."""
    units = [{"text": "слово,"}, {"text": "раз"}]
    chunks = [
        {"id": "0001", "n": 1, "text": "слово,"},
        {"id": "0002", "n": 2, "text": "раз"},
    ]
    sm = map_section(units, chunks, section="01_test")
    assert len(sm.spans) == 2


# ── #42: independently computed atom-range boundaries (T15-6C11-3g1) ─────────

def _two_atom_sm():
    """Single chunk 'x0 x1' — stream has 2 atoms."""
    units = [{"text": "x0 x1"}]
    chunks = [{"id": "0001", "n": 1, "text": "x0 x1"}]
    return map_section(units, chunks, section="01_test")


def test_42_sol_incomplete_range_coherent_corruption():
    """Sol P2 repro 1: atom_end=1 with matching spans accepts only 1 atom — must MISMATCH."""
    sm = _two_atom_sm()
    stream = sm.stream
    unit_kinds = ["text"]
    cs = sm.spans[0]
    # Coherent corruption: atom_end reduced, span matches first atom only
    bad = ChunkSpan(
        chunk_id=cs.chunk_id,
        atom_start=0,
        atom_end=1,
        spans=(cs.spans[0],),  # only 1 span, consistent with atom_end=1
        unit_ids=cs.unit_ids,
        kind=cs.kind,
        end_modes=None,
    )
    # expected_end is independently derived from manifest (2 atoms)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, stream, unit_kinds, 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_42_sol_incomplete_range_via_map_section(monkeypatch):
    """Sol P2 repro 1 via map_section: injected atom_end=cursor+n-1 raises MISMATCH."""
    def corrupt(cs):
        return ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end - 1, cs.spans[:-1], cs.unit_ids, cs.kind, None)
    monkeypatch.setattr(_unitmap, "ChunkSpan", _make_bad_cs_factory(corrupt))
    units = [{"text": "x0 x1"}]
    chunks = [{"id": "0001", "n": 1, "text": "x0 x1"}]
    with pytest.raises(AnnotationError) as exc:
        map_section(units, chunks, section="01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_42_sol_gap_ranges():
    """Sol P2 repro 2a: gap (0,1),(2,4) — second chunk atom_start != expected_start."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs1 = sm.spans[0]
    cs2 = sm.spans[1]
    # First chunk validated correctly (atom_start=0, atom_end=2)
    _validate_chunk_span(cs1, stream, unit_kinds, 0, cs1.atom_end, cs1.chunk_id, "01_test")
    # Second chunk: inject a gap — tell validator expected_start=1 but cs2.atom_start=2
    # (or use bad cs with atom_start=3 to simulate (0,1),(3,4) gap)
    bad2 = ChunkSpan(cs2.chunk_id, 3, cs2.atom_end, cs2.spans[1:], cs2.unit_ids, cs2.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad2, stream, unit_kinds, cs1.atom_end, cs2.atom_end, cs2.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_42_sol_overlapping_ranges():
    """Sol P2 repro 2b: overlap (0,3),(2,4) — second chunk atom_start < first chunk atom_end."""
    sm, stream, unit_kinds = _base_sm_and_meta()
    cs1 = sm.spans[0]
    cs2 = sm.spans[1]
    # Second chunk: atom_start=1 overlaps with first chunk's range (0,2)
    # expected_start (from cursor after cs1) = cs1.atom_end = 2
    bad2 = ChunkSpan(cs2.chunk_id, 1, cs2.atom_end, (cs1.spans[1],) + cs2.spans, cs2.unit_ids, cs2.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad2, stream, unit_kinds, cs1.atom_end, cs2.atom_end, cs2.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_42_shortened_range_raises():
    """atom_end less than manifest count raises SPAN_STREAM_MISMATCH."""
    sm = _two_atom_sm()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, 0, 1, cs.spans[:1], cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_42_extended_range_raises():
    """atom_end more than manifest count raises SPAN_STREAM_MISMATCH."""
    sm = _two_atom_sm()
    cs = sm.spans[0]
    bad = ChunkSpan(cs.chunk_id, 0, len(sm.stream), cs.spans + cs.spans, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, cs.chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_42_valid_single_chunk_accepted():
    """Valid single-chunk mapping passes validation and chunk_atoms returns atoms."""
    sm = _two_atom_sm()
    result = chunk_atoms(sm, "0001")
    assert len(result) == 2
    assert result[0].text == "x0"
    assert result[1].text == "x1"


def test_42_valid_multi_chunk_accepted():
    """Valid multi-chunk mapping passes validation."""
    sm, _, _ = _base_sm_and_meta()
    assert len(sm.spans) == 2
    atoms_0 = chunk_atoms(sm, "0001")
    atoms_1 = chunk_atoms(sm, "0002")
    assert atoms_0[0].text == "слово"
    assert atoms_1[0].text == "слово"


def test_42_chunk_atoms_provenance_correct():
    """chunk_atoms() returns the exact stored stream slice after 3g1 fix."""
    sm = _two_atom_sm()
    result = chunk_atoms(sm, "0001")
    # Must be the slice from sm.stream, not re-tokenized
    assert result is sm.stream[sm.spans[0].atom_start:sm.spans[0].atom_end]


# ── #43: ChunkSpan metadata type validation (T15-6C11-3g2) ───────────────────

def _valid_cs_and_ctx():
    """Return (cs, stream, unit_kinds, expected_start, expected_end) for one valid chunk."""
    sm = _two_atom_sm()
    cs = sm.spans[0]
    return cs, sm.stream, ["text"], 0, cs.atom_end


def _assert_mismatch(bad_cs, stream, unit_kinds, exp_start, exp_end, exp_chunk_id="0001"):
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad_cs, stream, unit_kinds, exp_start, exp_end, exp_chunk_id, "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


# ── atom_start / atom_end type injections ────────────────────────────────────

def test_43_atom_start_none_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, None, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_atom_start_float_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, 0.0, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_atom_start_bool_raises():
    """bool is a subclass of int but must be rejected (type(True) is int → False)."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, False, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_atom_start_hostile_raises():
    """Hostile atom_start whose __eq__ raises must still raise SPAN_STREAM_MISMATCH."""
    class _H:
        def __eq__(self, other): raise RuntimeError("hostile __eq__")
        def __ne__(self, other): raise RuntimeError("hostile __ne__")

    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, _H(), cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_atom_end_bool_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, True, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


# ── spans type injections ─────────────────────────────────────────────────────

def test_43_spans_none_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, None, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_spans_list_raises():
    """list spans must be rejected (not a tuple)."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, list(cs.spans), cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_spans_malformed_pair_raises():
    """Span element that is not a 2-tuple of ints must be rejected."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad_spans = (("a", "b"),) + cs.spans[1:]  # type: ignore
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, bad_spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_spans_pair_bool_offset_raises():
    """Span with bool offset (subclass of int) must be rejected."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad_spans = ((True, 2),) + cs.spans[1:]  # type: ignore
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, bad_spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_spans_hostile_element_raises():
    """Hostile span element that raises on comparison must raise SPAN_STREAM_MISMATCH."""
    class _H:
        def __eq__(self, other): raise RuntimeError("hostile")
        def __len__(self): raise RuntimeError("hostile len")

    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad_spans = (_H(),) + cs.spans[1:]  # type: ignore
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, bad_spans, cs.unit_ids, cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


# ── unit_ids type injections ──────────────────────────────────────────────────

def test_43_unit_ids_set_raises():
    """Mutable set must be rejected (not frozenset)."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, set(cs.unit_ids), cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_unit_ids_bool_element_raises():
    """frozenset containing bool must be rejected."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, frozenset({False}), cs.kind, None)
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_unit_ids_str_element_raises():
    """frozenset containing str must be rejected."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, frozenset({"0"}), cs.kind, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


# ── kind type injections ──────────────────────────────────────────────────────

def test_43_kind_none_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, None, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


def test_43_kind_int_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, 42, None)  # type: ignore
    _assert_mismatch(bad, stream, uk, es, ee)


# ── end_modes injections ──────────────────────────────────────────────────────

def test_43_end_modes_frozenset_raises():
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    bad = ChunkSpan(cs.chunk_id, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, frozenset())
    _assert_mismatch(bad, stream, uk, es, ee)


# ── Valid metadata still accepted ─────────────────────────────────────────────

def test_43_valid_metadata_accepted():
    """Valid ChunkSpan metadata passes all type checks."""
    cs, stream, uk, es, ee = _valid_cs_and_ctx()
    _validate_chunk_span(cs, stream, uk, es, ee, cs.chunk_id, "01_test")  # must not raise


# ── #44: corrupted ChunkSpan chunk_id diagnostics (T15-6C11-3g3) ─────────────

import traceback
import logging as _log


def _sm_one_chunk():
    """Return SectionMap with one chunk '0001'."""
    return map_section([{"text": "слово"}], [{"id": "0001", "n": 1, "text": "слово"}], section="01_test")


def test_44_sol_repro_secret_id_empty_spans(monkeypatch):
    """Sol P2 repro: secret chunk_id + empty spans — secret must not appear in exception."""
    secret = "SYNTHETIC_SECRET_METADATA"

    def corrupt(cs):
        return ChunkSpan(secret, cs.atom_start, cs.atom_end, (), cs.unit_ids, cs.kind, None)

    monkeypatch.setattr(_unitmap, "ChunkSpan", _make_bad_cs_factory(corrupt))
    with pytest.raises(AnnotationError) as exc:
        map_section([{"text": "слово"}], [{"id": "0001", "n": 1, "text": "слово"}], section="01_test")

    e = exc.value
    assert e.code == "SPAN_STREAM_MISMATCH"
    assert secret not in str(e)
    assert secret not in repr(e)
    assert all(secret not in str(a) for a in e.args)
    for v in vars(e).values():
        if v is not None:
            assert secret not in str(v)


def test_44_valid_meta_secret_id_rejected(monkeypatch):
    """Injected secret chunk_id with otherwise valid metadata must be rejected."""
    secret = "VALID_META_SECRET_ID"

    def corrupt(cs):
        return ChunkSpan(secret, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)

    monkeypatch.setattr(_unitmap, "ChunkSpan", _make_bad_cs_factory(corrupt))
    with pytest.raises(AnnotationError) as exc:
        map_section([{"text": "слово"}], [{"id": "0001", "n": 1, "text": "слово"}], section="01_test")

    e = exc.value
    assert e.code == "SPAN_STREAM_MISMATCH"
    assert secret not in str(e)
    assert secret not in repr(e)


def test_44_hostile_chunk_id_no_dunder_calls():
    """Hostile chunk_id whose dunders raise must not cause exception."""
    class _Hostile:
        def __eq__(self, other): raise RuntimeError("hostile __eq__")
        def __str__(self): raise RuntimeError("hostile __str__")
        def __repr__(self): raise RuntimeError("hostile __repr__")
        def __bool__(self): raise RuntimeError("hostile __bool__")
        def __hash__(self): return 0

    sm = _sm_one_chunk()
    cs = sm.spans[0]
    bad = ChunkSpan(_Hostile(), cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, "0001", "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_44_malformed_id_types_rejected():
    """None, int, bool chunk_id raise SPAN_STREAM_MISMATCH."""
    sm = _sm_one_chunk()
    cs = sm.spans[0]
    for bad_id in (None, 1, True, b"0001"):
        bad = ChunkSpan(bad_id, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)  # type: ignore
        with pytest.raises(AnnotationError) as exc:
            _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, "0001", "01_test")
        assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_44_string_subclass_rejected():
    """str subclass chunk_id must be rejected (type(x) is str → False)."""
    class _StrSub(str):
        pass

    sm = _sm_one_chunk()
    cs = sm.spans[0]
    bad = ChunkSpan(_StrSub("0001"), cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)
    with pytest.raises(AnnotationError) as exc:
        _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, "0001", "01_test")
    assert exc.value.code == "SPAN_STREAM_MISMATCH"


def test_44_no_secret_in_traceback():
    """Secret in chunk_id must not appear in traceback.format_exception output."""
    secret = "TRACEBACK_LEAK_SECRET"
    sm = _sm_one_chunk()
    cs = sm.spans[0]
    bad = ChunkSpan(secret, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)

    try:
        raise ValueError(secret)
    except ValueError:
        with pytest.raises(AnnotationError) as exc:
            _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, "0001", "01_test")

    e = exc.value
    assert e.__cause__ is None
    assert e.__suppress_context__ is True
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    assert secret not in tb


def test_44_no_secret_in_logging(caplog):
    """Logging SPAN_STREAM_MISMATCH must not expose the corrupted chunk_id."""
    secret = "LOG_CHUNK_ID_SECRET"
    sm = _sm_one_chunk()
    cs = sm.spans[0]
    bad = ChunkSpan(secret, cs.atom_start, cs.atom_end, cs.spans, cs.unit_ids, cs.kind, None)

    try:
        _validate_chunk_span(bad, sm.stream, ["text"], 0, cs.atom_end, "0001", "01_test")
    except AnnotationError as e:
        with caplog.at_level(_log.ERROR):
            _log.error("caught: %s", e, exc_info=True)

    assert secret not in caplog.text


def test_44_valid_id_mapping_preserved():
    """Valid chunk_id preserves exact atom mapping and stored Atom identity."""
    sm = _sm_one_chunk()
    result = chunk_atoms(sm, "0001")
    assert len(result) == 1
    assert result[0].text == "слово"
    assert result is sm.stream[0:1]
