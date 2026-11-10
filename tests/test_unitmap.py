"""Tests for unitmap.annotate_units() — T15-6C1 / T15-6C1b."""
import pytest

from audiobook.unitmap import AnnotationError, annotate_units, find_exact_in_unit


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


# ── I2′: zero-Cyrillic-token chunks ──────────────────────────────────────────
# Scenario 1: standalone unit — zero-token chunk is the entire text of one unit.

def test_i2_prime_standalone_unit():
    units = [
        _unit("paragraph", "Текст до"),
        _unit("paragraph", "http://example.com"),
        _unit("paragraph", "Текст после"),
    ]
    chunks = [
        _chunk("Текст до", id_="0001"),
        _chunk("http://example.com", id_="0002"),
        _chunk("Текст после", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 1
    assert result[1]["kind"] == "text"


# Scenario 2: tail of a text unit — zero-token text follows Cyrillic text in
# the same unit; the split is between Cyrillic and non-Cyrillic parts.

def test_i2_prime_tail_of_text_unit():
    units = [
        _unit("paragraph", "Смотри здесь: http://example.com"),
        _unit("paragraph", "Следующий"),
    ]
    chunks = [
        _chunk("Смотри здесь:", id_="0001"),
        _chunk("http://example.com", id_="0002"),
        _chunk("Следующий", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0  # same unit as chunk 0001
    assert result[1]["kind"] == "text"


# Scenario 3: added trailing period — chunk has a trailing "." the unit
# does not; normalization strips it and the match still succeeds.

def test_i2_prime_trailing_period_stripped():
    units = [
        _unit("paragraph", "Контакт: user@example.com"),
        _unit("paragraph", "Следующий текст"),
    ]
    chunks = [
        _chunk("Контакт:", id_="0001"),
        _chunk("user@example.com.", id_="0002"),   # trailing period
        _chunk("Следующий текст", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0
    assert result[1]["kind"] == "text"


# Scenario 4: duplicate occurrence — key appears twice in the unit → error.

def test_i2_prime_duplicate_occurrence_raises():
    units = [
        _unit("paragraph", "Текст"),
        _unit("paragraph", "abc abc"),    # duplicate non-Cyrillic substring
        _unit("paragraph", "Финал"),
    ]
    chunks = [
        _chunk("Текст", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("Финал", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "ambiguous" in exc_info.value.reason


# Scenario 5: missing occurrence — key not found in any unit in the anchor
# range → error.

def test_i2_prime_missing_occurrence_raises():
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "Нет совпадения"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("http://nothere.com", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "no M1/M2 match" in exc_info.value.reason


# Scenario 6: match only before lower anchor — key exists in a unit whose
# index is below the lower anchor → not found in search range → error.

def test_i2_prime_match_before_lower_anchor_raises():
    # unit[0] contains the key; chunk A covers unit[1]; zero-token chunk
    # follows chunk A, so lower_uid = 1 and unit[0] is out of range.
    units = [
        _unit("paragraph", "http://target.com"),   # unit 0: contains key
        _unit("paragraph", "Опора"),               # unit 1: Cyrillic anchor
        _unit("paragraph", "Финал"),
    ]
    chunks = [
        _chunk("Опора", id_="0001"),              # first chunk covers unit 1
        _chunk("http://target.com", id_="0002"),  # zero-token; prev anchor is unit 1
        _chunk("Финал", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "no M1/M2 match" in exc_info.value.reason


# Scenario 7: whitespace-only chunk → error.

def test_i2_prime_whitespace_only_raises():
    units = [_unit("paragraph", "Текст"), _unit("paragraph", "Финал")]
    chunks = [
        _chunk("Текст", id_="0001"),
        _chunk("   ", id_="0002"),
        _chunk("Финал", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "whitespace" in exc_info.value.reason.lower() or "empty" in exc_info.value.reason.lower()


# Scenario 8: cross-unit occurrence — key appears in two different units
# within the anchor range → error.

def test_i2_prime_cross_unit_occurrence_raises():
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "shared-key"),
        _unit("paragraph", "shared-key"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("shared-key", id_="0002"),  # matches units 1 AND 2
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "ambiguous" in exc_info.value.reason


# Scenario 9a: first chunk is zero-token (no prev Cyrillic anchor).

def test_i2_prime_first_chunk_zero_token():
    units = [
        _unit("paragraph", "http://intro.com"),
        _unit("paragraph", "Основной текст"),
    ]
    chunks = [
        _chunk("http://intro.com", id_="0001"),
        _chunk("Основной текст", id_="0002"),
    ]
    result = annotate_units(chunks, units)
    assert result[0]["unit_id"] == 0
    assert result[0]["kind"] == "text"


# Scenario 9b: last chunk is zero-token (no next Cyrillic anchor).

def test_i2_prime_last_chunk_zero_token():
    units = [
        _unit("paragraph", "Основной текст"),
        _unit("paragraph", "http://end.com"),
    ]
    chunks = [
        _chunk("Основной текст", id_="0001"),
        _chunk("http://end.com", id_="0002"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 1
    assert result[1]["kind"] == "text"


# Scenario 10a: consecutive zero-token chunks in correct source order succeed.

def test_i2_prime_consecutive_zero_token_in_order():
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "first-url second-url"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("first-url", id_="0002"),
        _chunk("second-url", id_="0003"),
        _chunk("Конец", id_="0004"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 1
    assert result[2]["unit_id"] == 1


# Scenario 10b: consecutive zero-token chunks in reversed order → error
# (second chunk's key appears before first chunk's match end).

def test_i2_prime_consecutive_zero_token_reversed_order_raises():
    # In the unit text, "second" comes BEFORE "first".
    # Z1 matches "first" (at pos 7), Z2 must match "second" at pos >= 7+5=12.
    # But "second" is at pos 0 → no valid occurrence for Z2 → error.
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "second first"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("first", id_="0002"),    # matches at pos 7 in "second first"
        _chunk("second", id_="0003"),   # would need pos >= 12, but "second" is at 0
        _chunk("Конец", id_="0004"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "no M1/M2 match" in exc_info.value.reason


# ── T15-6C5a: anchor interval bounds ─────────────────────────────────────────
# Zero-token key must NOT match outside the strict interval [lower_anchor, upper_anchor).


def test_i2_prime_key_before_lower_anchor_raises():
    # Source: "abc Начало Конец"
    # Chunks: Начало | abc | Конец
    # "abc" precedes the lower anchor "Начало" → rejected.
    units = [_unit("paragraph", "abc Начало Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


def test_i2_prime_key_after_upper_anchor_raises():
    # Source: "Начало Конец abc"
    # Chunks: Начало | abc | Конец
    # "abc" follows the upper anchor "Конец" → rejected.
    units = [_unit("paragraph", "Начало Конец abc")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


def test_i2_prime_key_in_prior_chunk_suffix_raises():
    # Source: "Начало abc Конец"
    # Chunks: "Начало abc" | abc | Конец
    # "abc" is claimed by the first Cyrillic chunk's suffix → consumed_end blocks it.
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало abc", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


def test_i2_prime_key_between_anchors_passes():
    # Source: "abc Начало abc Конец"
    # Chunks: Начало | abc | Конец
    # "abc" at pos 11 is strictly between lower anchor "Начало" and upper anchor "Конец".
    units = [_unit("paragraph", "abc Начало abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0
    assert result[1]["kind"] == "text"


# ── T15-6C5b: global source order across units ───────────────────────────────


def test_i2_prime_global_order_reversed_across_units_raises():
    # Required regression: chunks "second" then "first" but source has unit1="first", unit2="second".
    # Chunk 1 matches unit 2 ("second"), chunk 2 would need unit 1 ("first") → backward → error.
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "first"),
        _unit("paragraph", "second"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("second", id_="0002"),
        _chunk("first", id_="0003"),
        _chunk("Конец", id_="0004"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


def test_i2_prime_global_order_forward_across_units_passes():
    # Consecutive zero-token chunks in increasing unit order → valid.
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "first"),
        _unit("paragraph", "second"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("first", id_="0002"),
        _chunk("second", id_="0003"),
        _chunk("Конец", id_="0004"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 1
    assert result[2]["unit_id"] == 2


def test_i2_prime_global_order_same_unit_overlap_raises():
    # Two zero-token chunks mapping to the same position in the same unit → overlap rejected.
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "word"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("word", id_="0002"),
        _chunk("word", id_="0003"),  # same key, same unit → global_zero_pos blocks it
        _chunk("Конец", id_="0004"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


# ── T15-6C5c1a: find_exact_in_unit helper ────────────────────────────────────


def test_exact_simple_word():
    result = find_exact_in_unit("Начало", "Начало Конец")
    assert result == [(0, 6)]


def test_exact_with_terminal_punctuation():
    # Preserves punctuation — does NOT strip it.
    result = find_exact_in_unit("Начало.", "Начало. Конец.")
    assert result == [(0, 7)]


def test_exact_punctuation_only():
    # Punctuation-only key (e.g. "...")
    result = find_exact_in_unit("...", "Текст ... ещё.")
    assert result == [(6, 9)]


def test_exact_repeated_occurrences_returns_all():
    result = find_exact_in_unit("abc", "abc xyz abc")
    assert result == [(0, 3), (8, 11)]


def test_exact_nbsp_treated_as_whitespace():
    # NBSP between tokens in source should match regular space in key.
    text = "a b c"  # NBSP between 'a' and 'b'
    result = find_exact_in_unit("a b", text)
    # Match spans from 'a' (orig 0) to end of 'b' (orig 3, exclusive)
    assert result == [(0, 3)]


def test_exact_repeated_whitespace_collapsed():
    # Three spaces in source collapsed to one; key with single space matches.
    text = "a   b"
    result = find_exact_in_unit("a b", text)
    # Match covers orig 0..5 (the whole string including the 3 spaces)
    assert result == [(0, 5)]


def test_exact_decomposed_unicode_matches_precomposed():
    # Source has decomposed 'e' + combining acute (2 orig chars → 1 NFC char).
    # Key has precomposed 'é'.
    text = "é fin"  # decomposed é at orig 0..2
    result = find_exact_in_unit("é", text)  # precomposed é
    assert result == [(0, 2)]


def test_exact_anchor_lb_filters_earlier_match():
    # Two occurrences; lb cuts out the first one.
    text = "abc xyz abc"
    result = find_exact_in_unit("abc", text, orig_lb=4)
    assert result == [(8, 11)]


def test_exact_anchor_ub_filters_later_match():
    # Two occurrences; ub cuts out the second one.
    text = "abc xyz abc"
    result = find_exact_in_unit("abc", text, orig_ub=5)
    assert result == [(0, 3)]


def test_exact_no_match_returns_empty():
    result = find_exact_in_unit("xyz", "Начало Конец")
    assert result == []


def test_exact_empty_key_returns_empty():
    result = find_exact_in_unit("", "Начало Конец")
    assert result == []


def test_exact_original_offsets_are_precise():
    # Verify byte-precise positions including surrounding text.
    text = "pre Начало post"
    result = find_exact_in_unit("Начало", text)
    assert len(result) == 1
    orig_s, orig_e = result[0]
    assert text[orig_s:orig_e] == "Начало"


def test_exact_ub_boundary_inclusive():
    # Match end exactly at orig_ub → included (ub is exclusive upper bound on orig_end).
    text = "abc xyz"
    result = find_exact_in_unit("abc", text, orig_ub=3)
    assert result == [(0, 3)]


def test_exact_ub_boundary_exclusive():
    # orig_ub less than match end → excluded.
    text = "abc xyz"
    result = find_exact_in_unit("abc", text, orig_ub=2)
    assert result == []


# ── T15-6C5c1b: M1/M2 matching via annotate_units ────────────────────────────
# 12 punctuation scenarios from the architect's spec.


def _zchunk(text: str, id_: str) -> dict:
    """Zero-Cyrillic-token chunk helper."""
    return {"text": text, "id": id_, "pause_after_ms": 400}


# S1: different punctuation on chunk vs source → no match, STOP.

def test_m1_m2_s1_different_punc_stops():
    # Chunk "abc!" (ends '!', not in M2_TERMINAL), source has "abc?" — no M1 or M2.
    units = [_unit("paragraph", "Начало abc? Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc!", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


# S2: chunk has terminal ".", source lacks it → tolerant match.

def test_m1_m2_s2_tolerant_dot():
    # Source "abc" (no dot); chunk "abc." — M2 strips dot, finds "abc" at boundary.
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc.", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == "tolerant:46"  # ord('.') == 46


# S3: chunk "abc.", source "abc." → exact match (M2 "abc" blocked by following ".").

def test_m1_m2_s3_exact_when_source_has_dot():
    units = [_unit("paragraph", "Начало abc. Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc.", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == "exact"


# S4: exact at one position, tolerant at another → two distinct positions, STOP.

def test_m1_m2_s4_exact_plus_tolerant_stops():
    # Source: "abc. xyz abc " — M1 finds "abc." at (7,11), M2 "abc" at (12,15) followed by ' '.
    # Two distinct positions → STOP.
    units = [_unit("paragraph", "Начало abc. xyz abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc.", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "ambiguous" in exc_info.value.reason


# S5a: unique "..." in source → exact.

def test_m1_m2_s5a_unique_ellipsis_exact():
    units = [_unit("paragraph", "Начало ... Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("...", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == "exact"


# S5b: duplicate "..." in source → two positions, STOP.

def test_m1_m2_s5b_duplicate_ellipsis_stops():
    units = [_unit("paragraph", "Начало ... mid ... Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("...", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "ambiguous" in exc_info.value.reason


# S6: case difference → no match, STOP (matching is case-sensitive).

def test_m1_m2_s6_case_mismatch_stops():
    units = [_unit("paragraph", "Начало ABC Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


# S7a: NBSP in source, regular space in chunk → match (ws-collapsed).

def test_m1_m2_s7a_nbsp_matches():
    units = [_unit("paragraph", "Начало a b Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("a b", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0
    assert result[1]["match"] == "exact"


# S7b: multiple spaces in source, single space in chunk → match.

def test_m1_m2_s7b_multiple_spaces_match():
    units = [_unit("paragraph", "Начало a   b Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("a b", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == "exact"


# S8a: missing match → STOP.

def test_m1_m2_s8a_missing_stops():
    units = [_unit("paragraph", "Начало xyz Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("nothere", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)
    assert "no M1/M2 match" in exc_info.value.reason


# S9: punctuation-only chunk → M1 only (M2 key would have no alphanumeric).

def test_m1_m2_s9_punctuation_only_m1_only():
    # "..." ends with '.', M2 key ".." has no letter/digit → not attempted.
    units = [_unit("paragraph", "Начало ... Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("...", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == "exact"


# S10: tolerant with "…" (U+2026) terminal.

def test_m1_m2_s10_tolerant_ellipsis_char():
    # Chunk "abc…", source "abc" at boundary → tolerant match, codepoint 8230.
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc…", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == f"tolerant:{ord(chr(0x2026))}"  # tolerant:8230


# S11: M2 blocked when followed by "!" (not whitespace).

def test_m1_m2_s11_m2_blocked_by_exclamation():
    # Source "abc!xyz" — M2 "abc" at (7,10) followed by '!' → rejected.
    # M1 "abc." not found either → STOP.
    units = [_unit("paragraph", "Начало abc!xyz Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("abc.", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2′" in str(exc_info.value)


# S12: M2 match recorded with correct codepoint.

def test_m1_m2_s12_match_field_codepoint():
    # Match field should encode the stripped terminal char's codepoint.
    units = [_unit("paragraph", "Начало word Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _zchunk("word.", id_="0002"),
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["match"] == "tolerant:46"  # '.' == U+002E == 46


# ── T15-6C7a: Unicode offset correctness (combining-mark reordering) ──────────


def test_sol_p2_repro_1_combining_reorder_orig_lb_filters():
    """Sol P2 repro 1: lone combiner in NFC overlaps orig span before orig_lb=3."""
    # "à̕" has len 3; NFC = "à̕".  '̕' in NFC maps to
    # the whole combining sequence (0,3).  With orig_lb=3, orig_s=0 < 3 → rejected.
    result = find_exact_in_unit("̕", "à̕", orig_lb=3)
    assert result == []


def test_sol_p2_repro_2_char_after_reordered_seq_correct_offset():
    """Sol P2 repro 2: char after reordered combining seq gets correct original offset."""
    # "à̕ X": combining seq (0,3) → NFC "à̕"; 'X' at orig (4,5).
    result = find_exact_in_unit("X", "à̕ X")
    assert result == [(4, 5)]


def test_combining_reorder_no_zero_length_span():
    """Every returned span must be non-empty; zero-length spans are rejected."""
    # '̕' in NFC maps to whole combining seq (0,3), not phantom (3,3).
    result = find_exact_in_unit("̕", "à̕")
    assert all(s < e for s, e in result), "zero-length span detected"
    assert result == [(0, 3)]


def test_combining_reorder_char_immediately_after_seq():
    """Char immediately after a 3-orig-char combining seq has offset 3, not 1."""
    # "à̕b": seq (0,3) + 'b' at (3,4).
    result = find_exact_in_unit("b", "à̕b")
    assert result == [(3, 4)]


def test_combining_reorder_space_after_seq_then_next_word():
    """Space between reordered seq and next word doesn't confuse offsets."""
    result = find_exact_in_unit("fin", "à̕ fin")
    assert result == [(4, 7)]


def test_nfc_decomposed_source_precomposed_key_span():
    """Decomposed source (e+́) matched by precomposed key (é) → span (0,2)."""
    # Existing test covers this; here we verify no cascade into next char.
    result = find_exact_in_unit("fin", "é fin")
    assert result == [(3, 6)]


def test_nbsp_combining_class_zero_starts_new_seq():
    """NBSP (class 0) starts a new combining seq; offsets after it are correct."""
    # "a b": NBSP at (1,2), 'b' at (2,3).
    result = find_exact_in_unit("b", "a b")
    assert result == [(2, 3)]


def test_lone_combiner_at_start_is_own_seq():
    """A lone combiner with no base character forms its own sequence."""
    # "̀abc": lone grave at (0,1), then 'a' at (1,2) etc.
    result = find_exact_in_unit("abc", "̀abc")
    assert result == [(1, 4)]


# ── T15-6C7b: prevent reuse of previous chunk's non-Cyrillic suffix ───────────


def test_6c7b_sol_p1_double_space_suffix_blocks_reuse():
    """Sol P1 repro: double-space in chunk suffix must block subsequent zero-token match.

    Old str.find missed the suffix, leaving consumed_end too low; zero-token
    'abc' was then incorrectly matched against already-consumed text.
    """
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало  abc", id_="0001"),  # double space → suffix "  abc"
        _chunk("abc", id_="0002"),           # zero-token: should be blocked
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7b_decomposed_suffix_blocks_reuse():
    """Decomposed suffix in chunk (NFC-equivalent to source) correctly blocks reuse."""
    # Unit has precomposed é (U+00E9); chunk suffix has decomposed e+combining_acute.
    units = [_unit("paragraph", "Начало \xe9 Конец")]
    chunks = [
        _chunk("Начало é", id_="0001"),  # decomposed é as suffix
        _chunk("\xe9", id_="0002"),             # zero-token: blocked after NFC match
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7b_nbsp_suffix_blocks_reuse():
    """NBSP in chunk suffix is treated as whitespace; consumed text is correctly blocked."""
    units = [_unit("paragraph", "Начало xyz Конец")]
    chunks = [
        _chunk("Начало xyz", id_="0001"),  # NBSP before xyz in suffix
        _chunk("xyz", id_="0002"),              # zero-token: blocked
        _chunk("Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7b_valid_zero_token_after_suffix_passes():
    """Zero-token chunk AFTER the previous chunk's suffix still resolves correctly."""
    units = [_unit("paragraph", "Начало abc xyz Конец")]
    chunks = [
        _chunk("Начало abc", id_="0001"),  # suffix " abc" consumed up to pos 10
        _chunk("xyz", id_="0002"),          # zero-token: starts at pos 11, valid
        _chunk("Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0
    assert result[1]["kind"] == "text"
    assert result[1]["match"] == "exact"


# ── T15-6C7c: prevent overlap with next chunk's non-Cyrillic prefix ───────────


def test_6c7c_sol_p1_prefix_blocks_zero_token_overlap():
    """Sol P1 repro: zero-token must not consume text belonging to next chunk's prefix.

    'abc' in the unit is claimed as a prefix by the following 'abc Конец' chunk;
    the zero-token 'abc' must be rejected.
    """
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("abc", id_="0002"),        # zero-token; 'abc' belongs to next chunk
        _chunk("abc Конец", id_="0003"),  # prefix 'abc ' immediately precedes 'Конец'
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7c_nbsp_prefix_blocks_zero_token():
    """NBSP in next chunk's prefix is treated as whitespace; overlap still rejected."""
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("abc Конец", id_="0003"),  # NBSP between prefix and Cyrillic
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7c_double_space_prefix_blocks_zero_token():
    """Double space in next chunk's prefix collapses to match single space in unit."""
    units = [_unit("paragraph", "Начало abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("abc", id_="0002"),
        _chunk("abc  Конец", id_="0003"),  # double space: prefix 'abc  ' → norm 'abc'
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7c_decomposed_prefix_blocks_zero_token():
    """Decomposed Unicode prefix (NFC-equivalent) correctly blocks the zero-token."""
    # Unit has precomposed é (1 orig char); next chunk has decomposed e+́ as prefix.
    units = [_unit("paragraph", "Начало \xe9 Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("\xe9", id_="0002"),           # zero-token: same as next chunk's prefix
        _chunk("é Конец", id_="0003"),  # prefix 'é ' NFC-matches '\xe9'
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7c_valid_zero_token_before_distinct_prefix():
    """Zero-token with distinct text from the next chunk's prefix resolves correctly."""
    units = [_unit("paragraph", "Начало xyz abc Конец")]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("xyz", id_="0002"),        # zero-token: 'xyz' is distinct from prefix 'abc'
        _chunk("abc Конец", id_="0003"),  # prefix 'abc' starts at pos 11
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0
    assert result[1]["kind"] == "text"
    assert result[1]["match"] == "exact"


# ── T15-6C7d: regression coverage — repeated consumption via annotate_units ───


def test_6c7d_combining_seq_repeated_consumption_blocked():
    """Second zero-token cannot re-consume a combining-sequence span already matched.

    Unit has 'a\\u0315\\u0300 xyz'.  NFC produces 'à\\u0315 xyz'; '\\u0315' in NFC
    maps to the whole combining sequence (0,3).  After the first zero-token claims
    that span, unit_match_end[uid]=3 blocks any subsequent match within [0,3).
    """
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "à̕ xyz"),  # combining seq (0,3) + 'xyz'
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("̕", id_="0002"),    # zero-token: matches combining seq (0,3)
        _chunk("̕", id_="0003"),    # second: same key, same span → blocked
        _chunk("Конец", id_="0004"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)


def test_6c7d_combining_seq_sequential_consumption_passes():
    """Two zero-tokens in the same unit consume non-overlapping spans successfully.

    First zero-token matches the combining sequence; second matches 'xyz' after it.
    """
    units = [
        _unit("paragraph", "Начало"),
        _unit("paragraph", "à̕ xyz"),
        _unit("paragraph", "Конец"),
    ]
    chunks = [
        _chunk("Начало", id_="0001"),
        _chunk("̕", id_="0002"),    # matches combining seq (0,3)
        _chunk("xyz", id_="0003"),       # matches 'xyz' at (4,7) after the seq
        _chunk("Конец", id_="0004"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 1
    assert result[1]["match"] == "exact"
    assert result[2]["unit_id"] == 1
    assert result[2]["match"] == "exact"


def test_6c7d_suffix_and_prefix_both_active_valid():
    """Both suffix (6C7b) and prefix (6C7c) bounds active; zero-token in the middle passes."""
    # Unit: "Начало suf zero pre Конец"
    # chunk1 = "Начало suf" → suffix 'suf' consumed up to pos 11
    # chunk2 = "zero" → zero-token: must land after suf and before pre
    # chunk3 = "pre Конец" → prefix 'pre' blocks from pos 12
    units = [_unit("paragraph", "Начало suf zero pre Конец")]
    chunks = [
        _chunk("Начало suf", id_="0001"),
        _chunk("zero", id_="0002"),
        _chunk("pre Конец", id_="0003"),
    ]
    result = annotate_units(chunks, units)
    assert result[1]["unit_id"] == 0
    assert result[1]["match"] == "exact"


def test_6c7d_suffix_and_prefix_both_active_overlap_raises():
    """With both suffix and prefix active, a key that overlaps either is rejected."""
    # Unit: "Начало suf zero pre Конец"
    # chunk2 = "suf" → would need pos after suf (pos 11) but 'suf' is at (7,10) → blocked
    units = [_unit("paragraph", "Начало suf zero pre Конец")]
    chunks = [
        _chunk("Начало suf", id_="0001"),
        _chunk("suf", id_="0002"),        # 'suf' is in consumed suffix → I2' error
        _chunk("pre Конец", id_="0003"),
    ]
    with pytest.raises(AnnotationError) as exc_info:
        annotate_units(chunks, units)
    assert "I2" in str(exc_info.value)
