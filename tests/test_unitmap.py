"""Tests for unitmap.annotate_units() — T15-6C1."""
import pytest

from audiobook.unitmap import AnnotationError, annotate_units


# ── helpers ──────────────────────────────────────────────────────────────────

def _unit(type_: str, text: str, **kw) -> dict:
    return {"type": type_, "text": text, **kw}


def _chunk(text: str, pause: int = 900, id_: str = "0001") -> dict:
    return {"text": text, "pause_after_ms": pause, "id": id_}


# ── single-unit mapping ───────────────────────────────────────────────────────

def test_single_unit_heading():
    units = [_unit("heading", "Глава первая")]
    chunks = [_chunk("Глава первая", pause=1500)]
    result = annotate_units(chunks, units)
    assert result[0]["unit_id"] == 0
    assert result[0]["kind"] == "heading"


def test_single_unit_paragraph():
    units = [_unit("paragraph", "Привет мир")]
    chunks = [_chunk("Привет мир")]
    result = annotate_units(chunks, units)
    assert result[0]["unit_id"] == 0
    assert result[0]["kind"] == "text"


def test_single_unit_stack():
    units = [_unit("stack", "Пункт один", last_in_stack=True)]
    chunks = [_chunk("Пункт один")]
    result = annotate_units(chunks, units)
    assert result[0]["unit_id"] == 0
    assert result[0]["kind"] == "stack"


def test_original_chunk_fields_preserved():
    units = [_unit("paragraph", "Привет мир")]
    chunks = [{"text": "Привет мир", "pause_after_ms": 350, "id": "0042", "extra": "val"}]
    result = annotate_units(chunks, units)
    assert result[0]["pause_after_ms"] == 350
    assert result[0]["id"] == "0042"
    assert result[0]["extra"] == "val"


# ── one unit split across multiple chunks ─────────────────────────────────────

def test_unit_split_across_two_chunks():
    # Long paragraph unit split into two manifest chunks (chunk_prose behaviour).
    units = [_unit("paragraph", "Первое предложение здесь. Второе предложение там.")]
    chunks = [
        _chunk("Первое предложение здесь.", pause=350, id_="0001"),
        _chunk("Второе предложение там.", pause=900, id_="0002"),
    ]
    result = annotate_units(chunks, units)
    assert result[0]["unit_id"] == 0
    assert result[1]["unit_id"] == 0
    assert result[0]["kind"] == "text"
    assert result[1]["kind"] == "text"


def test_unit_split_three_chunks():
    units = [_unit("paragraph", "Раз два три четыре пять шесть семь восемь девять десять")]
    chunks = [
        _chunk("Раз два три четыре", id_="0001"),
        _chunk("пять шесть семь", id_="0002"),
        _chunk("восемь девять десять", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert all(r["unit_id"] == 0 for r in result)
    assert all(r["kind"] == "text" for r in result)


# ── multiple units with different kinds ───────────────────────────────────────

def test_heading_then_paragraph():
    units = [
        _unit("heading", "Заголовок"),
        _unit("paragraph", "Текст параграфа"),
    ]
    chunks = [
        _chunk("Заголовок", pause=1500, id_="0001"),
        _chunk("Текст параграфа", pause=900, id_="0002"),
    ]
    result = annotate_units(chunks, units)
    assert result[0]["unit_id"] == 0
    assert result[0]["kind"] == "heading"
    assert result[1]["unit_id"] == 1
    assert result[1]["kind"] == "text"


def test_stack_then_paragraph():
    units = [
        _unit("stack", "Пункт раз", last_in_stack=False),
        _unit("stack", "Пункт два", last_in_stack=True),
        _unit("paragraph", "Обычный текст"),
    ]
    chunks = [
        _chunk("Пункт раз", id_="0001"),
        _chunk("Пункт два", id_="0002"),
        _chunk("Обычный текст", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[0]["kind"] == "stack"
    assert result[1]["kind"] == "stack"
    assert result[2]["kind"] == "text"
    assert result[0]["unit_id"] == 0
    assert result[1]["unit_id"] == 1
    assert result[2]["unit_id"] == 2


# ── flow and prose_with_arrow also map to "text" ─────────────────────────────

def test_flow_kind_is_text():
    units = [_unit("flow", "Слово за словом")]
    chunks = [_chunk("Слово за словом")]
    assert annotate_units(chunks, units)[0]["kind"] == "text"


def test_prose_with_arrow_kind_is_text():
    units = [_unit("prose_with_arrow", "Вперёд к цели")]
    chunks = [_chunk("Вперёд к цели")]
    assert annotate_units(chunks, units)[0]["kind"] == "text"


# ── does not mutate input ─────────────────────────────────────────────────────

def test_does_not_mutate_manifest_chunks():
    units = [_unit("paragraph", "Текст")]
    chunks = [_chunk("Текст")]
    original_keys = set(chunks[0].keys())
    annotate_units(chunks, units)
    assert set(chunks[0].keys()) == original_keys


# ── I1: token stream mismatch ─────────────────────────────────────────────────

def test_token_mismatch_raises_I1():
    units = [_unit("paragraph", "Привет мир")]
    chunks = [_chunk("Привет земля")]  # "земля" != "мир"
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I1" in str(exc_info.value)
    assert exc_info.value.mismatch_idx >= 0


def test_manifest_longer_than_units_raises_I1():
    units = [_unit("paragraph", "Одно слово")]
    chunks = [_chunk("Одно слово"), _chunk("лишний чанк")]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I1" in str(exc_info.value)


def test_units_longer_than_manifest_raises_I1():
    units = [
        _unit("paragraph", "Первый юнит"),
        _unit("paragraph", "Второй юнит"),
    ]
    chunks = [_chunk("Первый юнит")]  # second unit has no chunk
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I1" in str(exc_info.value)


# ── I2: zero-token chunk ──────────────────────────────────────────────────────

def test_zero_token_chunk_raises_I2():
    units = [_unit("paragraph", "Текст")]
    chunks = [_chunk("--- 123 ---")]  # no Cyrillic tokens
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units, section="test_sec")
    assert "I2" in str(exc_info.value)
    assert exc_info.value.section == "test_sec"


def test_empty_string_chunk_raises_I2():
    units = [_unit("paragraph", "Текст")]
    chunks = [_chunk("")]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


# ── I3: chunk crossing unit boundaries ───────────────────────────────────────

def test_chunk_crossing_unit_boundary_raises_I3():
    # Two distinct units; a single chunk that covers tokens from both.
    units = [
        _unit("paragraph", "Первый"),
        _unit("paragraph", "Второй"),
    ]
    # Chunk text has tokens from both units.
    chunks = [_chunk("Первый Второй")]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I3" in str(exc_info.value)


def test_chunk_crossing_kind_boundary_raises_I3():
    # heading unit then paragraph — if a chunk spans both, kinds conflict.
    units = [
        _unit("heading", "Заголовок"),
        _unit("paragraph", "Текст"),
    ]
    chunks = [_chunk("Заголовок Текст")]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I3" in str(exc_info.value)


# ── error metadata ────────────────────────────────────────────────────────────

def test_error_includes_section_and_chunk_id():
    units = [_unit("paragraph", "Слово")]
    chunks = [{"text": "Другое", "pause_after_ms": 900, "id": "0099"}]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units, section="17_chapter")
    err = exc_info.value
    assert err.section == "17_chapter"
    assert err.chunk_id == "0099"


def test_error_no_manuscript_text_in_message():
    # Diagnostics must not leak manuscript text.
    units = [_unit("paragraph", "Секретный текст рукописи")]
    chunks = [_chunk("Другой текст")]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    msg = str(exc_info.value)
    # The mismatch token appears in the message; that is acceptable (single word).
    # Full chunk or unit text must not appear.
    assert "Секретный текст рукописи" not in msg
    assert "Другой текст" not in msg


# ── empty inputs ──────────────────────────────────────────────────────────────

def test_empty_units_and_chunks_ok():
    result = annotate_units([], [])
    assert result == []


def test_units_with_no_cyrillic_and_empty_manifest_ok():
    # A unit with only punctuation has no tokens; empty manifest still ok.
    units = [_unit("paragraph", "--- 123 ---")]
    result = annotate_units([], units)
    assert result == []
