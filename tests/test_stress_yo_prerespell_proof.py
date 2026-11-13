"""T15-7 WP4: source-free, fail-closed pre-respell observation research.

NOT a production implementation or approved gold/YO contract. Caller MUST
independently prove source_key -> exact fragment word ordinal. No search-based
alignment and no reliance on post-respell SUTrace token indices.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pytest

_WORD = re.compile(r"[А-Яа-яЁё]+")
_VOWELS = frozenset("аеёиоуыэюя")


class UnsupportedObservation(ValueError):
    """Refuse unproven token correspondence or non-ё edits."""


@dataclass(frozen=True)
class Probe:
    source_form: str
    restored_form_pre_respell: str
    restored_vowel_indices: tuple[int, ...]
    status: str


def _nfc(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise UnsupportedObservation("INVALID_TEXT")
    if unicodedata.normalize("NFC", value) != value:
        raise UnsupportedObservation("NON_NFC")
    return value


def _tokens(value: str) -> list[str]:
    return _WORD.findall(_nfc(value))


def _compare(source: str, candidate: str) -> tuple[int, ...]:
    """Accept forward е/Е→ё/Ё edits only; return 0-based SOURCE vowel indices."""
    source, candidate = _nfc(source), _nfc(candidate)
    if (len(source) != len(candidate)
            or not _WORD.fullmatch(source) or not _WORD.fullmatch(candidate)):
        raise UnsupportedObservation("NOT_ONE_TO_ONE_WORD")
    indices: list[int] = []
    vowel_index = 0
    for left, right in zip(source, candidate, strict=True):
        if left == right:
            pass
        elif (left, right) in (("е", "ё"), ("Е", "Ё")):
            indices.append(vowel_index)
        else:
            raise UnsupportedObservation("NOT_PURE_FORWARD_YO")
        if left.lower() in _VOWELS:
            vowel_index += 1
    if len(indices) != len(set(indices)):
        raise UnsupportedObservation("DUPLICATE_VOWEL_INDEX")
    return tuple(indices)


def probe_pre_respell(
    source_fragment: str,
    expected_source_word: str,
    grounded_fragment_word_index: int | None,
    prepared_before_respell: str,
    direct_restore: str,
) -> Probe:
    """Prove a strict correspondence at an EXTERNALLY GROUNDED local ordinal.

    prepared_before_respell: voicecfg.prepare_text(raw_fragment, cfg, open_end).
    direct_restore: yo.restore(raw_fragment, explicit controlled dictionary).
    These two paths use the same restoration policy, so their agreement alone
    is NOT independent evidence for the source_key->fragment ordinal.
    """
    index = grounded_fragment_word_index
    if type(index) is not int or index < 0:
        raise UnsupportedObservation("NO_PROVEN_FRAGMENT_ORDINAL")
    source_words = _tokens(source_fragment)
    prepared_words = _tokens(prepared_before_respell)
    direct_words = _tokens(direct_restore)
    if not (len(source_words) == len(prepared_words) == len(direct_words)):
        raise UnsupportedObservation("WORD_COUNT_CHANGED")
    if index >= len(source_words):
        raise UnsupportedObservation("ORDINAL_OUT_OF_RANGE")
    if _nfc(expected_source_word) != source_words[index]:
        raise UnsupportedObservation("SOURCE_WORD_MISMATCH")
    for source, prepared, direct in zip(
        source_words, prepared_words, direct_words, strict=True
    ):
        _compare(source, prepared)
        _compare(source, direct)
        if prepared != direct:
            raise UnsupportedObservation("PREPARED_AND_RESTORED_DISAGREE")
    original = source_words[index]
    candidate = prepared_words[index]
    indices = _compare(original, candidate)
    return Probe(
        original, candidate, indices,
        "RESTORED" if indices else "NO_RESTORATION",
    )


# The following compact, deliberately independent synthetic simulator allows
# offline probes without importing the private application's full environment.
def fake_restore(text: str, mapping: dict[str, str]) -> str:
    def replace(m: re.Match) -> str:
        word = m.group()
        target = mapping.get(word.lower())
        if target is None:
            return word
        return target.upper() if word.isupper() else (
            target.title() if word[0].isupper() else target
        )
    return _WORD.sub(replace, text)


def fake_prepare(
    text: str, mapping: dict[str, str], *, strip=False, terminal=False, open_end=False
) -> str:
    text = fake_restore(text, mapping)
    if strip:
        text = text.translate(str.maketrans("", "", "«»“”„")).strip()
    if open_end:
        text = text.rstrip(",— ") + "…"
    elif terminal:
        text = text.rstrip()
        if text and text[-1] not in ".!?…:;":
            text += "."
    return text


@pytest.mark.parametrize("source,mapping,expected", [
    ("Елепа", {"елепа": "ёлепа"}, (0,)),
    ("ЕЛЕПА", {"елепа": "ёлепа"}, (0,)),
    ("елепа", {"елепа": "ёлепа"}, (0,)),
    ("Ереея", {"ереея": "ёреёя"}, (0, 2)),
    ("Бетё", {}, ()),
    ("Елепа", {}, ()),
])
def test_ordinal_source_vowel_indices(source, mapping, expected):
    result = probe_pre_respell(
        source, source, 0, fake_prepare(source, mapping),
        fake_restore(source, mapping),
    )
    assert result.restored_vowel_indices == expected
    assert result.status == ("RESTORED" if expected else "NO_RESTORATION")


@pytest.mark.parametrize("strip,terminal,open_end", [
    (False, False, False), (True, False, False),
    (True, True, False), (False, False, True),
])
def test_quotes_terminal_and_open_end_do_not_change_word_alignment(
    strip, terminal, open_end
):
    raw = "«Елепа»"
    mapping = {"елепа": "ёлепа"}
    observed = probe_pre_respell(
        raw, "Елепа", 0,
        fake_prepare(raw, mapping, strip=strip, terminal=terminal, open_end=open_end),
        fake_restore(raw, mapping),
    )
    assert observed.restored_form_pre_respell == "Ёлепа"


def test_repeated_words_use_explicit_ordinal_not_text_search():
    raw = "Елепа елепа"
    mapping = {"елепа": "ёлепа"}
    prepared = fake_prepare(raw, mapping)
    direct = fake_restore(raw, mapping)
    assert probe_pre_respell(raw, "елепа", 1, prepared, direct).restored_vowel_indices == (0,)
    with pytest.raises(UnsupportedObservation, match="SOURCE_WORD_MISMATCH"):
        probe_pre_respell(raw, "Елепа", 1, prepared, direct)


def test_padded_carrier_is_not_source_and_must_be_removed():
    raw = "Елепа."
    direct = fake_restore(raw, {"елепа": "ёлепа"})
    with pytest.raises(UnsupportedObservation, match="WORD_COUNT_CHANGED"):
        probe_pre_respell(raw, "Елепа", 0, "Другая фраза. " + direct, direct)


def test_yo_from_post_respell_is_not_yo_restore():
    raw = "Елепа."
    pre = fake_prepare(raw, {})
    post = pre.replace("Елепа", "Ёлепа")
    assert post != pre
    assert probe_pre_respell(raw, "Елепа", 0, pre, raw).status == "NO_RESTORATION"


def test_phrase_respell_can_change_word_count_without_corrupting_pre_observation():
    raw = "Елепа елепа."
    mapping = {"елепа": "ёлепа"}
    pre = fake_prepare(raw, mapping)
    post = pre.replace("Ёлепа ёлепа", "Ёлепа")
    assert len(_tokens(post)) != len(_tokens(pre))
    assert probe_pre_respell(
        raw, "елепа", 1, pre, fake_restore(raw, mapping)
    ).restored_vowel_indices == (0,)


@pytest.mark.parametrize("prepared,direct,reason", [
    ("Ёлепа", "Елепа", "PREPARED_AND_RESTORED_DISAGREE"),
    ("Елопа", "Елопа", "NOT_PURE_FORWARD_YO"),
    ("Ёле па", "Ёле па", "WORD_COUNT_CHANGED"),
    ("ЕЛЕПА", "ЕЛЕПА", "NOT_PURE_FORWARD_YO"),
])
def test_mismatched_or_non_yo_edit_fails_closed(prepared, direct, reason):
    with pytest.raises(UnsupportedObservation, match=reason):
        probe_pre_respell("Елепа", "Елепа", 0, prepared, direct)


@pytest.mark.parametrize("index", [None, -1, True, 2])
def test_unproven_or_invalid_ordinal_is_refused(index):
    with pytest.raises(UnsupportedObservation):
        probe_pre_respell("Елепа", "Елепа", index, "Ёлепа", "Ёлепа")


def test_two_fragments_need_separate_grounded_ordinals():
    for source in ("Елепа,", "елепа!"):
        mapping = {"елепа": "ёлепа"}
        assert probe_pre_respell(
            source, _tokens(source)[0], 0,
            fake_prepare(source, mapping), fake_restore(source, mapping)
        ).restored_vowel_indices == (0,)
    with pytest.raises(UnsupportedObservation, match="ORDINAL_OUT_OF_RANGE"):
        probe_pre_respell("елепа!", "елепа", 1, "ёлепа!", "ёлепа!")


def test_unicode_nfc_and_reverse_restoration_are_not_guessed():
    with pytest.raises(UnsupportedObservation, match="NON_NFC"):
        _compare("е\u0308лепа", "ёлепа")
    with pytest.raises(UnsupportedObservation, match="NOT_PURE_FORWARD_YO"):
        _compare("Ёлепа", "Елепа")


def test_unrelated_phrase_edit_refused():
    with pytest.raises(UnsupportedObservation):
        probe_pre_respell("Елепа елепа", "елепа", 1, "Ёлепа другое", "Ёлепа другое")


def test_repo_voicecfg_and_yo_path_if_installed(monkeypatch):
    voicecfg = pytest.importorskip("audiobook.voicecfg")
    yo = pytest.importorskip("audiobook.yo")
    pron = pytest.importorskip("audiobook.pronounce")
    mapping = {"елепа": "ёлепа", "ереея": "ёреёя"}
    monkeypatch.setattr(yo, "book_map", lambda: mapping)
    raw = "«Елепа ереея»"
    cfg = {"text_prep": {
        "yo_restore": True, "strip_quotes": True, "ensure_terminal": True
    }}
    prepared = voicecfg.prepare_text(raw, cfg, False)
    direct = yo.restore(raw, mapping)
    assert probe_pre_respell(
        raw, "Елепа", 0, prepared, direct
    ).restored_vowel_indices == (0,)
    assert probe_pre_respell(
        raw, "ереея", 1, prepared, direct
    ).restored_vowel_indices == (0, 2)
    changed = pron.respell(prepared, {"Ёлепа ёреёя": "Ёлепа"})
    assert len(_tokens(changed)) != len(_tokens(prepared))


def test_repo_yo_restore_off_does_not_infer_respell_restoration(monkeypatch):
    voicecfg = pytest.importorskip("audiobook.voicecfg")
    yo = pytest.importorskip("audiobook.yo")
    pron = pytest.importorskip("audiobook.pronounce")
    monkeypatch.setattr(yo, "book_map", lambda: {"елепа": "ёлепа"})
    raw = "Елепа."
    pre = voicecfg.prepare_text(raw, {"text_prep": {"yo_restore": False}})
    assert pron.respell(pre, {"Елепа": "Ёлепа"}) != pre
    assert probe_pre_respell(raw, "Елепа", 0, pre, raw).status == "NO_RESTORATION"
