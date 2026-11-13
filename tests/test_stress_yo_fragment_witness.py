"""T15-7 research-only: source-key -> fragment ordinal witness, no fuzzy lookup.

A witness is safe only if every word in the ordered pre-respell fragment stream
matches the independently supplied chunk-source stream EXACTLY. The caller
must separately prove chunk_word_index comes from that same chunk.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pytest

WORD = re.compile(r"[А-Яа-яЁё]+")


class UnsupportedWitness(ValueError):
    pass


@dataclass(frozen=True)
class FragmentWitness:
    fragment: int
    fragment_word_index: int
    chunk_word_index: int
    form_source: str


def witness(
    chunk_source_words: list[str],
    fragments_before_prep: list[str],
    chunk_word_index: int | None,
    expected_source_word: str,
) -> FragmentWitness:
    if not fragments_before_prep or type(chunk_word_index) is not int or chunk_word_index < 0:
        raise UnsupportedWitness("UNPROVEN_ORDINAL")
    if not all(isinstance(w, str) and w and WORD.fullmatch(w) and
               unicodedata.is_normalized("NFC", w) for w in chunk_source_words):
        raise UnsupportedWitness("INVALID_CHUNK_WORDS")
    if not all(isinstance(s, str) and s and unicodedata.is_normalized("NFC", s)
               for s in fragments_before_prep):
        raise UnsupportedWitness("INVALID_FRAGMENTS")
    parsed = [WORD.findall(fragment) for fragment in fragments_before_prep]
    flat = [w for words in parsed for w in words]
    if flat != chunk_source_words:
        raise UnsupportedWitness("FRAGMENT_STREAM_NOT_EXACT_SOURCE")
    if chunk_word_index >= len(flat):
        raise UnsupportedWitness("ORDINAL_OUT_OF_RANGE")
    if chunk_source_words[chunk_word_index] != expected_source_word:
        raise UnsupportedWitness("SOURCE_WORD_IDENTITY_MISMATCH")
    cursor = 0
    for i, words in enumerate(parsed):
        if cursor <= chunk_word_index < cursor + len(words):
            return FragmentWitness(
                i, chunk_word_index - cursor, chunk_word_index,
                expected_source_word,
            )
        cursor += len(words)
    raise UnsupportedWitness("UNREACHABLE")


def test_identical_repeated_tokens_are_distinguished_by_ordinal():
    w = witness(["Елепа", "елепа", "елепа"], ["Елепа?", "елепа, елепа!"], 2, "елепа")
    assert w == FragmentWitness(1, 1, 2, "елепа")


def test_fragment_boundaries_are_independent_of_terminal_punctuation():
    w = witness(["Елепа", "Другой"], ["Елепа?", "Другой!"], 1, "Другой")
    assert w.fragment == 1 and w.fragment_word_index == 0


def test_single_fragment_word_index_is_preserved():
    assert witness(["Елепа", "Другой"], ["Елепа, Другой."], 1, "Другой").fragment_word_index == 1


@pytest.mark.parametrize("words,frags,index,form,error", [
    (["Елепа"], ["Елепа", "Елепа"], 0, "Елепа", "FRAGMENT_STREAM_NOT_EXACT_SOURCE"),
    (["Елепа"], ["Ёлепа"], 0, "Елепа", "FRAGMENT_STREAM_NOT_EXACT_SOURCE"),
    (["Елепа", "Другой"], ["Елепа"], 0, "Елепа", "FRAGMENT_STREAM_NOT_EXACT_SOURCE"),
    (["Елепа", "Другой"], ["Елепа, Другое"], 0, "Елепа", "FRAGMENT_STREAM_NOT_EXACT_SOURCE"),
    (["Елепа"], ["Елепа"], 1, "Елепа", "ORDINAL_OUT_OF_RANGE"),
    (["Елепа"], ["Елепа"], 0, "елепа", "SOURCE_WORD_IDENTITY_MISMATCH"),
    (["Елепа"], ["Елепа"], None, "Елепа", "UNPROVEN_ORDINAL"),
    (["Елепа"], ["Елепа"], True, "Елепа", "UNPROVEN_ORDINAL"),
    (["Елепа"], [], 0, "Елепа", "UNPROVEN_ORDINAL"),
])
def test_no_fuzzy_matching_or_unverified_fragment_alignment(words, frags, index, form, error):
    with pytest.raises(UnsupportedWitness, match=error):
        witness(words, frags, index, form)


def test_no_normalization_guessing():
    with pytest.raises(UnsupportedWitness, match="INVALID_CHUNK_WORDS"):
        witness(["е\u0308лепа"], ["ёлепа"], 0, "е\u0308лепа")


def test_no_silent_punctuation_lead_in_word_inclusion():
    with pytest.raises(UnsupportedWitness, match="FRAGMENT_STREAM_NOT_EXACT_SOURCE"):
        witness(["Елепа"], ["Другая фраза. Елепа"], 0, "Елепа")
