"""Tests for Atom, ChunkSpan, AnnotationError and pre-mapping gates — T15-6C11-1b."""
import unicodedata
import pytest

from audiobook.unitmap import (
    Atom, ChunkSpan, SectionMap, AnnotationError,
    atoms, source_atoms, validate_gates, check_gates,
    map_section, map_chunks, chunk_atoms,
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
    spans = map_chunks(units, chunks)
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
    spans = map_chunks(units, chunks)
    assert [cs.atom_start for cs in spans] == [0, 2]
    assert [cs.atom_end for cs in spans] == [2, 4]


def test_map_chunks_across_units():
    units = _mk_units(_para("а б"), _para("в г"))
    chunks = _mk_chunks("а б", "в г")
    spans = map_chunks(units, chunks)
    assert spans[0].unit_ids == frozenset({0})
    assert spans[1].unit_ids == frozenset({1})


# ── #3: extra chunk / stream exhausted ───────────────────────────────────────

def test_map_stream_exhausted_extra_chunk():
    units = _mk_units(_para("слово"))
    chunks = _mk_chunks("слово", "лишнее")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "STREAM_EXHAUSTED"


def test_map_stream_exhausted_empty_source():
    units = _mk_units(_para(""))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "STREAM_EXHAUSTED"


# ── #4: trailing atoms ────────────────────────────────────────────────────────

def test_map_trailing_source_atoms():
    units = _mk_units(_para("слово раз"))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "TRAILING_SOURCE"


def test_map_trailing_source_multiple_units():
    units = _mk_units(_para("а б"), _para("в"))
    chunks = _mk_chunks("а б")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "TRAILING_SOURCE"


# ── #5–7: atom mismatch (case, ё, punctuation) ───────────────────────────────

def test_map_atom_mismatch_case():
    units = _mk_units(_para("Слово"))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_uppercase():
    units = _mk_units(_para("слово"))
    chunks = _mk_chunks("СЛОВО")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_yo_e():
    units = _mk_units(_para("ёлка"))
    chunks = _mk_chunks("елка")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_e_yo():
    units = _mk_units(_para("елка"))
    chunks = _mk_chunks("ёлка")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_trailing_punct():
    units = _mk_units(_para("слово."))
    chunks = _mk_chunks("слово")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_added_punct():
    units = _mk_units(_para("слово"))
    chunks = _mk_chunks("слово.")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_atom_mismatch_different_word():
    units = _mk_units(_para("кот"))
    chunks = _mk_chunks("кит")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


# ── #8: NBSP and double spaces succeed ───────────────────────────────────────

def test_map_nbsp_in_source():
    # NBSP treated as whitespace by \S+: atoms still split correctly
    units = _mk_units(_para("слово\xa0раз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks)
    assert spans[0].atom_end - spans[0].atom_start == 2


def test_map_double_space_in_source():
    units = _mk_units(_para("слово  раз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks)
    assert spans[0].atom_end - spans[0].atom_start == 2


def test_map_double_space_in_chunk():
    units = _mk_units(_para("слово раз"))
    chunks = _mk_chunks("слово  раз")
    spans = map_chunks(units, chunks)
    assert spans[0].atom_end - spans[0].atom_start == 2


# ── #9: single newlines succeed ──────────────────────────────────────────────

def test_map_newline_in_source():
    units = _mk_units(_para("слово\nраз"))
    chunks = _mk_chunks("слово раз")
    spans = map_chunks(units, chunks)
    assert spans[0].atom_end - spans[0].atom_start == 2


def test_map_newline_between_chunks():
    units = _mk_units(_para("а\nб"))
    chunks = _mk_chunks("а", "б")
    spans = map_chunks(units, chunks)
    assert len(spans) == 2


# ── #10: repeated identical atoms ────────────────────────────────────────────

def test_map_repeated_atoms_sequential():
    units = _mk_units(_para("abc abc abc"))
    chunks = _mk_chunks("abc", "abc", "abc")
    spans = map_chunks(units, chunks)
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
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_mismatch_before_exhaustion():
    # source has atoms at the requested position but they differ → ATOM_MISMATCH, not STREAM_EXHAUSTED
    units = _mk_units(_para("кот пёс"))
    chunks = _mk_chunks("кот рыба")  # "рыба" ≠ "пёс" at position 1
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "ATOM_MISMATCH"


def test_map_genuine_exhaustion():
    # source runs dry mid-chunk (no atom at all at that position) → STREAM_EXHAUSTED
    units = _mk_units(_para("кот"))  # 1 atom
    chunks = _mk_chunks("кот пёс")   # 2 atoms needed
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "STREAM_EXHAUSTED"


# ── #11: cross-kind chunk ────────────────────────────────────────────────────

def test_map_kind_ambiguous():
    units = _mk_units(_head("Глава"), _para("текст"))
    chunks = _mk_chunks("Глава текст")
    with pytest.raises(AnnotationError) as exc:
        map_chunks(units, chunks)
    assert exc.value.code == "KIND_AMBIGUOUS"


def test_map_same_kind_two_units_ok():
    units = _mk_units(_para("а"), _para("б"))
    chunks = _mk_chunks("а б")
    spans = map_chunks(units, chunks)
    assert spans[0].unit_ids == frozenset({0, 1})
    assert spans[0].kind == "text"


# ── #15: zero-Cyrillic chunk as separate manifest chunk ──────────────────────

def test_map_zero_cyrillic_chunk_punct():
    # "—" has no Cyrillic but one atom; must map through cursor correctly
    units = _mk_units(_para("—"))
    chunks = _mk_chunks("—")
    spans = map_chunks(units, chunks)
    assert spans[0].spans == ((0, 1),)
    assert spans[0].kind == "text"


def test_map_zero_cyrillic_between_cyr_chunks():
    units = _mk_units(_para("слово — конец"))
    chunks = _mk_chunks("слово", "—", "конец")
    spans = map_chunks(units, chunks)
    assert len(spans) == 3
    assert spans[1].spans == ((6, 7),)


# ── #16: zero-Cyrillic chunk as unit tail ────────────────────────────────────

def test_map_zero_cyrillic_tail_of_unit():
    units = _mk_units(_para("слово..."))
    chunks = _mk_chunks("слово...")
    spans = map_chunks(units, chunks)
    # "слово..." is one atom
    assert len(spans[0].spans) == 1
    assert spans[0].spans[0] == (0, 8)


def test_map_zero_cyrillic_separate_tail_atom():
    units = _mk_units(_para("слово ..."))
    chunks = _mk_chunks("слово", "...")
    spans = map_chunks(units, chunks)
    assert spans[0].spans == ((0, 5),)
    assert spans[1].spans == ((6, 9),)


# ── #17: reconstruction from spans reproduces atom text ──────────────────────

def test_map_reconstruction_from_spans():
    units = _mk_units(_para("первый второй третий"))
    chunks = _mk_chunks("первый второй", "третий")
    spans = map_chunks(units, chunks)
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
    spans = map_chunks(units, chunks)

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
        map_chunks(units, chunks)
    assert exc.value.code in ("ATOM_MISMATCH", "TRAILING_SOURCE")


def test_map_heading_kind():
    units = _mk_units(_head("Введение"))
    chunks = _mk_chunks("Введение")
    spans = map_chunks(units, chunks)
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
    errors = validate_gates(chunks, [])
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs, "expected MANIFEST_ORDER error"
    _no_disclosure(order_errs[0], _SECRET)


def test_3b_invalid_id_cyrillic_latin_not_disclosed():
    """Cyrillic+Latin marker in ID must not appear in diagnostics."""
    chunks = [{"id": _CYR_MARKER, "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [])
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    _no_disclosure(order_errs[0], _CYR_MARKER)


def test_3b_wrong_format_id_not_disclosed():
    """Wrong-format ID (single digit) must not appear in diagnostics."""
    chunks = [{"id": "1", "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [])
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
    errors = validate_gates(chunks, [])
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    # Second error (the duplicate) must not carry the raw ID
    dup_err = order_errs[-1]
    assert dup_err.chunk_id != marker or dup_err.chunk_id.startswith("@")


def test_3b_unexpected_id_type_not_disclosed():
    """Non-string ID value must not appear in diagnostics."""
    secret_val = 99999
    chunks = [{"id": secret_val, "n": 1, "text": "а"}]
    errors = validate_gates(chunks, [])
    order_errs = [e for e in errors if e.code == "MANIFEST_ORDER"]
    assert order_errs
    assert str(secret_val) not in order_errs[0].chunk_id or order_errs[0].chunk_id.startswith("@")


def test_3b_invalid_id_not_in_nfc_error():
    """NOT_NFC error for chunk with invalid ID must not expose the raw ID."""
    nfd_text = unicodedata.normalize("NFD", "ё")  # non-NFC
    chunks = [{"id": _SECRET, "n": 1, "text": nfd_text}]
    errors = validate_gates(chunks, [])
    nfc_errs = [e for e in errors if e.code == "NOT_NFC" and e.chunk_id != "0"]
    # May or may not raise NOT_NFC (MANIFEST_ORDER may mask it), but if it does, no disclosure
    for e in nfc_errs:
        _no_disclosure(e, _SECRET)


def test_3b_invalid_id_not_in_empty_chunk_error():
    """EMPTY_CHUNK error for chunk with invalid ID must not expose the raw ID."""
    chunks = [{"id": _SECRET, "n": 1, "text": "   "}]
    errors = validate_gates(chunks, [])
    empty_errs = [e for e in errors if e.code == "EMPTY_CHUNK"]
    for e in empty_errs:
        _no_disclosure(e, _SECRET)


def test_3b_valid_ids_still_appear_in_diagnostics():
    """Valid IDs (passed MANIFEST_ORDER) must still appear in permitted diagnostics."""
    nfd_text = unicodedata.normalize("NFD", "ё")
    chunks = [{"id": "0001", "n": 1, "text": nfd_text}]
    errors = validate_gates(chunks, [])
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
    errors = validate_gates([None], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_int_raises_manifest_order():
    errors = validate_gates([42], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_list_raises_manifest_order():
    errors = validate_gates([["id", "0001"]], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_text_none_raises_manifest_order():
    errors = validate_gates([{"id": "0001", "n": 1, "text": None}], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_text_int_raises_manifest_order():
    errors = validate_gates([{"id": "0001", "n": 1, "text": 123}], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_chunk_text_missing_raises_manifest_order():
    errors = validate_gates([{"id": "0001", "n": 1}], [])
    # text defaults to None → structural error
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


# --- n type validation: reject bool and float ---

def test_3c_n_true_rejected():
    """n=True must not be accepted as n=1."""
    errors = validate_gates([{"id": "0001", "n": True, "text": "а"}], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_false_rejected():
    """n=False must not be accepted."""
    errors = validate_gates([{"id": "0001", "n": False, "text": "а"}], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_float_rejected():
    """n=1.0 must not be accepted as n=1."""
    errors = validate_gates([{"id": "0001", "n": 1.0, "text": "а"}], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_none_rejected():
    errors = validate_gates([{"id": "0001", "n": None, "text": "а"}], [])
    assert any(e.code == "MANIFEST_ORDER" for e in errors)


def test_3c_n_valid_int_accepted():
    """Valid int n=1 must pass."""
    errors = validate_gates([{"id": "0001", "n": 1, "text": "а"}], [])
    assert not any(e.code == "MANIFEST_ORDER" for e in errors)


# --- Unit structural errors ---

def test_3c_unit_none_raises_not_nfc():
    errors = validate_gates([], [None])
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_int_raises_not_nfc():
    errors = validate_gates([], [42])
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_text_none_raises_not_nfc():
    errors = validate_gates([], [{"text": None}])
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_text_int_raises_not_nfc():
    errors = validate_gates([], [{"text": 0}])
    assert any(e.code == "NOT_NFC" for e in errors)


def test_3c_unit_text_missing_raises_not_nfc():
    errors = validate_gates([], [{}])
    assert any(e.code == "NOT_NFC" for e in errors)


# --- No raw secret in structural errors ---

def test_3c_chunk_none_no_disclosure():
    """None chunk must not disclose repr(None) in diagnostics."""
    errors = validate_gates([None], [])
    for e in errors:
        assert "None" not in e.chunk_id


def test_3c_chunk_text_none_no_disclosure():
    errors = validate_gates([{"id": "0001", "n": 1, "text": None}], [])
    for e in errors:
        assert "None" not in str(e) or e.chunk_id in ("", "0001")


# --- Valid metadata preserved (extra fields must pass through) ---

def test_3c_valid_chunk_with_extra_metadata():
    """Extra fields on valid chunks must not cause errors."""
    chunks = [{"id": "0001", "n": 1, "text": "а", "meta": "ok", "extra": 42}]
    units = [{"text": "а", "type": "text"}]
    errors = validate_gates(chunks, units)
    assert errors == []


def test_3c_valid_unit_with_extra_metadata():
    units = [{"text": "а", "type": "heading", "speaker": "narrator"}]
    errors = validate_gates([], units)
    assert not any(e.code in ("NOT_NFC", "UNIT_INNER_PARA") for e in errors)


# ── 6C11-3d: CRLF and Unicode whitespace blank-line detection ─────────────────

def _inner_para_errors(unit_text: str) -> list[AnnotationError]:
    units = [{"text": unit_text}]
    return [e for e in validate_gates([], units) if e.code == "UNIT_INNER_PARA"]


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

def _mk_sm(unit_texts, chunk_texts, *, section=""):
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
    sm = map_section(units_A, chunks)
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
    sm = map_section(units_B, chunks)
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
    sm_A = map_section(units_A, chunks)
    sm_B = map_section(units_B, chunks)
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
    sm1 = map_section(units_A, chunks)
    sm2 = map_section(units_A, chunks)
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
    sm = map_section(units, chunks)
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


# ── #31: map_chunks() == list(map_section(...).spans) ────────────────────────

def test_31_map_chunks_equals_map_section_spans():
    """map_chunks() elements and order equal map_section(...).spans."""
    units = [{"text": "а б в г"}, {"text": "д е"}]
    chunks = [
        {"id": "0001", "n": 1, "text": "а б"},
        {"id": "0002", "n": 2, "text": "в г"},
        {"id": "0003", "n": 3, "text": "д е"},
    ]
    result_map_chunks = map_chunks(units, chunks, section="ch01")
    sm = map_section(units, chunks, section="ch01")
    assert result_map_chunks == list(sm.spans)


def test_31_map_chunks_equals_map_section_single():
    """Single-chunk case: map_chunks == list(map_section.spans)."""
    units = [{"text": "слово"}]
    chunks = [{"id": "0001", "n": 1, "text": "слово"}]
    assert map_chunks(units, chunks) == list(map_section(units, chunks).spans)


# ── SectionMap structure and chunk_atoms basics ───────────────────────────────

def test_sectionmap_is_frozen():
    sm = _mk_sm(["а"], ["а"])
    with pytest.raises((AttributeError, TypeError)):
        sm.section = "other"  # type: ignore[misc]


def test_sectionmap_section_field():
    sm = _mk_sm(["а"], ["а"], section="ch03")
    assert sm.section == "ch03"


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
    sm = map_section(units, chunks)
    assert sm.stream == source_atoms(units)


# ── #32: UNKNOWN_CHUNK diagnostic privacy; section validation (BLOCKED) ───────

def _mk_sm_one(unit_text: str, chunk_text: str, section: str = "") -> "SectionMap":
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


# BLOCKED: no approved AnnotationError code for invalid section type.
# The section parameter of map_section() / validate_gates() / check_gates() currently
# accepts non-string values without raising AnnotationError. The requirement is to reject
# them with a structured error, but the approved code set has no code for invalid section
# metadata. These tests document the REQUIRED final behaviour; they are marked xfail
# until an architect assigns a code and the validation is implemented.

@pytest.mark.xfail(reason="BLOCKED: no approved code for invalid section type", strict=False)
def test_32_section_dict_rejected():
    """Non-string section (dict) must raise AnnotationError — BLOCKED."""
    units = [{"text": "а"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    with pytest.raises(AnnotationError):
        map_section(units, chunks, section={"key": "value"})  # type: ignore[arg-type]


@pytest.mark.xfail(reason="BLOCKED: no approved code for invalid section type", strict=False)
def test_32_section_none_rejected():
    """Non-string section (None) must raise AnnotationError — BLOCKED."""
    units = [{"text": "а"}]
    chunks = [{"id": "0001", "n": 1, "text": "а"}]
    with pytest.raises(AnnotationError):
        map_section(units, chunks, section=None)  # type: ignore[arg-type]
