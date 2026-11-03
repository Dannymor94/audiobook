"""Layer-1 tests for T12 additions to phoneme_check — no real models."""

import pytest
from audiobook.phoneme_check import (
    ctc_greedy_counts,
    _ctc_frame_starts,
    stress_from_pron,
    parse_acc_word,
    stress_from_acc_line,
    analyze_iyU,
    _CYR_VOWELS,
)


# ── ctc_greedy_counts ─────────────────────────────────────────────────────────

def _vocab():
    """Minimal stub vocabulary."""
    return {0: "<pad>", 1: "a", 2: "b", 3: "c", 4: "|"}


def test_ctc_greedy_counts_basic():
    """Simple sequence: [1,1,2,2,3] → tokens [a,b,c], counts [2,2,1]."""
    vocab = _vocab()
    tokens, counts = ctc_greedy_counts([1, 1, 2, 2, 3], vocab, blank=0)
    assert tokens == ["a", "b", "c"]
    assert counts == [2, 2, 1]


def test_ctc_greedy_counts_blank_removed():
    """Blanks and repeated tokens after blank are collapsed."""
    vocab = _vocab()
    tokens, counts = ctc_greedy_counts([1, 0, 1, 2], vocab, blank=0)
    assert tokens == ["a", "a", "b"]
    assert counts == [1, 1, 1]


def test_ctc_greedy_counts_pipe_ignored():
    """The | word-boundary token is not included."""
    vocab = _vocab()
    tokens, counts = ctc_greedy_counts([1, 4, 2], vocab, blank=0)
    assert "|" not in tokens
    assert tokens == ["a", "b"]


def test_ctc_frame_starts_matches_counts():
    """Frame starts must be consistent with counts."""
    vocab = _vocab()
    ids = [1, 1, 1, 0, 2, 2]
    tokens, counts = ctc_greedy_counts(ids, vocab, blank=0)
    starts = _ctc_frame_starts(ids, vocab, blank=0)
    assert len(starts) == len(tokens)
    # First token starts at frame 0
    assert starts[0] == 0


# ── stress_from_pron ──────────────────────────────────────────────────────────

def test_stress_from_pron_normal():
    """'запить' → 'запИть' (value 'запИть')."""
    result = stress_from_pron("запить", "запИть")
    assert result == "запИть"


def test_stress_from_pron_tail_stress():
    """'волну' → 'волнУ' (stress on last vowel)."""
    result = stress_from_pron("волну", "волнУ")
    assert result == "волнУ"


def test_stress_from_pron_doubled_vowel():
    """'Отзывы' → 'Оотзывы': stress on first vowel of 'отзывы'."""
    result = stress_from_pron("Отзывы", "Оотзывы")
    # First vowel of 'отзывы' is 'о' at position 0 → 'Отзывы'
    assert result == "Отзывы"


def test_stress_from_pron_returns_none_on_bad_value():
    """Value with no uppercase vowel → None."""
    result = stress_from_pron("слово", "слово")
    assert result is None


# ── parse_acc_word ────────────────────────────────────────────────────────────

def test_parse_acc_word_normal():
    """'зап+ить' → ('запить', 1) — second vowel stressed."""
    plain, idx = parse_acc_word("зап+ить")
    assert plain == "запить"
    assert idx == 1  # а is 0th vowel, и is 1st


def test_parse_acc_word_first_vowel():
    """'Т+ы' → ('ты', 0)."""
    plain, idx = parse_acc_word("Т+ы")
    assert plain == "ты"
    assert idx == 0


def test_parse_acc_word_no_plus():
    """Word without '+' → None."""
    assert parse_acc_word("запить") is None


def test_parse_acc_word_plus_before_consonant():
    """'+' before a consonant → None (malformed)."""
    assert parse_acc_word("за+пить") is None


# ── stress_from_acc_line ──────────────────────────────────────────────────────

def test_stress_from_acc_line_finds_word():
    """Finds stressed form of 'запить' in an acc.txt line."""
    line = "Когда б+оль прих+одит зап+ить заснуть."
    result = stress_from_acc_line("запить", line)
    assert result == "запИть"


def test_stress_from_acc_line_not_found():
    """Word not in line → None."""
    assert stress_from_acc_line("ударить", "просто текст") is None


def test_stress_from_acc_line_first_vowel():
    """'Т+ы' in line → 'Ты' (stressed ы)."""
    result = stress_from_acc_line("ты", "Т+ы уж+е")
    assert result == "тЫ"


# ── analyze_iyU ───────────────────────────────────────────────────────────────

def _stub_tokens_iy():
    """Stub: 'ти' → IPA vowels for 2-vowel word where stressed is и (1st vowel)."""
    # 'тися': т=consonant, и=vowel(stressed), с=consonant, я=vowel
    # Simplified stub: 2 vowels, index 0 is stressed и
    # IPA: 'i' for и
    return ["t", "i", "s", "ɐ"]  # tisɐ: stressed index 0 (и=i), unstressed (я=ɐ)


def test_analyze_iyU_ok_when_stressed_louder():
    """Stressed и has 2× duration and 2× rms → verdict ok."""
    form = "тИся"   # stress on и (index 0)
    tokens = ["t", "i", "s", "ɐ"]
    # i is at token index 1, ɐ at index 3
    n_frames = [1, 10, 1, 5]     # i runs 10 frames, ɐ runs 5 → duration ratio 10/7.5 = 1.33
    rms_vals  = [0.0, 0.3, 0.0, 0.1]  # rms ratio 0.3/0.2 = 1.5
    # score ≈ sqrt(1.33 * 1.5) ≈ 1.41 > 1.2 → ok
    res = analyze_iyU(form, tokens, n_frames, rms_vals)
    assert res["verdict"] == "ok"
    assert "iyU_score" in res


def test_analyze_iyU_bad_when_unstressed():
    """Stressed и has 0.5× duration and 0.5× rms → verdict bad."""
    form = "тИся"
    tokens = ["t", "i", "s", "ɐ"]
    n_frames = [1, 3, 1, 10]    # i runs 3, ɐ runs 10 → mean=6.5, ratio=3/6.5≈0.46
    rms_vals  = [0.0, 0.05, 0.0, 0.3]
    res = analyze_iyU(form, tokens, n_frames, rms_vals)
    assert res["verdict"] == "bad"


def test_analyze_iyU_falls_back_for_non_iuy():
    """analyze_iyU for non-и/у/ы stressed vowel falls back to standard analyze."""
    form = "тЕбя"   # stressed е — not и/у/ы
    tokens = ["t", "ɪ", "b", "ɐ"]
    n_frames = [1, 1, 1, 1]
    rms_vals = [0.0, 0.1, 0.0, 0.1]
    res = analyze_iyU(form, tokens, n_frames, rms_vals)
    # Should not have iyU_score (fell back to analyze())
    assert "iyU_score" not in res
