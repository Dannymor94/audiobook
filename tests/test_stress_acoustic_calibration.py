import pytest

from audiobook.stress_acoustic_calibration import (
    expected_form, summarize, validate_controls, word_windows,
)
from audiobook.stress_consensus import audit


def test_repeated_occurrences_have_distinct_windows():
    heard = [{"w": "Замок", "s": 0.1, "e": 0.5, "p": 0.9},
             {"w": "замок.", "s": 0.6, "e": 1.0, "p": 0.9}]
    assert word_windows("Замок замок.", heard, 1.2) == {1: (0.1, 0.5), 2: (0.6, 1.0)}
    assert word_windows("Замок замок.", heard[:1], 1.2) is None
    assert word_windows("Замок молоко.", heard, 1.2) is None
    assert word_windows("Замок 3 замок.", heard, 1.2) is None
    assert word_windows("Замок замок.", [heard[0], dict(heard[1], s=0.3)], 1.2) is None
    assert word_windows("Замок замок.", [heard[0], dict(heard[1], p=0.2)], 1.2) == {1: (0.1, 0.5)}


def test_expected_form_validates_exact_vowel():
    assert expected_form("Замок", 3) == "замОк"
    assert expected_form("Берёза", 3) == "берЁза"
    with pytest.raises(ValueError):
        expected_form("Берёза", 1)
    with pytest.raises(ValueError):
        expected_form("Замок", True)


def test_control_identity_and_no_implicit_gold():
    rows = [{"id": "0001", "hash": "h", "text": "Замок замок."}]
    findings, _ = audit(rows, lambda t: "З+амок зам+ок.", lambda t: "З+амок зам+ок.")
    c = dict(findings[1], gold="wrong_stress", expected_index=3, wav_sha256="a" * 64)
    assert validate_controls(rows, findings, [c])[("0001", 2)] == c
    with pytest.raises(ValueError, match="CONTROL_IDENTITY"):
        validate_controls(rows, findings, [dict(c, ordinal=1)])
    with pytest.raises(ValueError, match="CONTROL_IDENTITY"):
        validate_controls(rows, findings, [c, c])
    with pytest.raises(ValueError, match="UNKNOWN_GOLD"):
        validate_controls(rows, findings, [dict(c, gold="agree")])


def test_uncertain_is_not_correct_or_missed_silently():
    s = summarize([{"gold": "wrong_stress", "signal": "stress_suspect"},
                   {"gold": "wrong_stress", "signal": "not_flagged"},
                   {"gold": "wrong_stress", "signal": "uncertain"},
                   {"gold": "correct", "signal": "stress_suspect"},
                   {"gold": "lexical_error", "signal": "uncertain"}])
    assert s["known_stress_errors"] == 3
    assert s["stress_errors_flagged"] == 1
    assert s["stress_errors_missed"] == 1
    assert s["correct_false_flags"] == 1
    assert s["outcomes"]["wrong_stress:uncertain"] == 1
    assert not s["release_ready"]


def test_unique_context_recovers_only_target_when_chunk_differs():
    from audiobook.stress_acoustic_calibration import contextual_window
    heard = [
        {"w": "лишнее", "s": 0.0, "e": 0.2, "p": 0.9},
        {"w": "мы", "s": 0.2, "e": 0.4, "p": 0.9},
        {"w": "видим", "s": 0.4, "e": 0.7, "p": 0.9},
        {"w": "молоко", "s": 0.7, "e": 1.1, "p": 0.9},
        {"w": "сегодня", "s": 1.1, "e": 1.5, "p": 0.9},
    ]
    text = "Вчера мы видим молоко сегодня"
    assert word_windows(text, heard, 2.0) is None
    assert contextual_window(text, heard, 2.0, 4) == (0.7, 1.1)
    assert contextual_window(text + " молоко", heard, 2.0, 4) is None
    assert contextual_window(text, heard + [
        {"w": "молоко", "s": 1.5, "e": 1.8, "p": 0.9}], 2.0, 4) is None
    assert contextual_window(text, [dict(w, p=0.1) for w in heard], 2.0, 4) is None
    assert contextual_window("Вчера мы видим-молоко сегодня", heard, 2.0, 4) is None
    assert contextual_window(text, heard, 2.0, 1) is None
    assert contextual_window(text, heard, 1.0, 4) is None


def test_uncertain_known_defect_is_counted_as_not_detected():
    from audiobook.stress_acoustic_calibration import summarize
    out = summarize([{"gold": "wrong_stress", "signal": "uncertain"}])
    assert out["stress_errors_uncertain"] == 1
    assert out["stress_errors_not_detected"] == 1
    assert out["stress_errors_flagged"] == 0
