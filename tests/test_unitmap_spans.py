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


# ── map_chunks helpers ────────────────────────────────────────────────────────

from audiobook.unitmap import map_chunks


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
