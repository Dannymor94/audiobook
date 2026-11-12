"""Tests for src/audiobook/stress_facts.py — T15-7.4

Covers every §9 matrix row + F1-F6 basics + AST import guard.
All tests use synthetic data only; no real corpus text.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trace(prep_text, pad_len=0, matches=None, status="ok", chunk_id="0001"):
    from audiobook.sutrace import SUTrace
    return SUTrace(
        section="01_test",
        chunk_id=chunk_id,
        fragment=None,
        prep_text=prep_text,
        pad_len=pad_len,
        matches=matches or [],
        final_sha256=hashlib.sha256(prep_text.encode()).hexdigest(),
        phrase_sha256=None,
        status=status,
    )


def _facts(trace=None, su_token_index=0, alignment_status="aligned",
           form_analysis="тест", verified_forms=None):
    from audiobook.stress_facts import compute_facts
    return compute_facts(trace, su_token_index, alignment_status,
                         form_analysis, verified_forms)


def _resolve(f2_approval="none", f2_vowel=None, f5_status="none", f5_vowel=None,
             f6_status="not_run", f6_vowel=None):
    from audiobook.stress_facts import resolve_expected
    return resolve_expected(f2_approval, f2_vowel, f5_status, f5_vowel, f6_status, f6_vowel)


def _classify(alignment_status="aligned", f1_flag="none", f1_rule=None,
              expected_source="none", f6_status="not_run", f6_vowel=None,
              expected_vowel=None, f3_verified=False):
    from audiobook.stress_facts import classify_status
    return classify_status(alignment_status, f1_flag, f1_rule, expected_source,
                           f6_status, f6_vowel, expected_vowel, f3_verified)


# ---------------------------------------------------------------------------
# F5: dormant guard
# ---------------------------------------------------------------------------

def test_f5_dormant():
    t = _make_trace("тест")
    f = _facts(trace=t)
    assert f.f5_status == "none"
    assert f.f5_vowel is None


# ---------------------------------------------------------------------------
# F6: always not_run at WP-2
# ---------------------------------------------------------------------------

def test_f6_not_run():
    t = _make_trace("тест")
    f = _facts(trace=t)
    assert f.f6_status == "not_run"
    assert f.f6_vowel is None


# ---------------------------------------------------------------------------
# F1: basic — no matches → f1_rule=None, f1_flag="none"
# ---------------------------------------------------------------------------

def test_f1_no_matches():
    t = _make_trace("тест", matches=[])
    f = _facts(trace=t)
    assert f.f1_rule is None
    assert f.f1_flag == "none"
    assert f.f1_phrase is False


def test_f1_unaligned_no_rule():
    """Unaligned → F1 is never computed."""
    t = _make_trace("тест")
    f = _facts(trace=t, alignment_status="fragment_mismatch")
    assert f.f1_rule is None
    assert f.f1_flag == "none"


def test_f1_full_coverage():
    """Single match covering 'тест' fully → f1_rule set, f1_flag='none'."""
    # "тест" is at positions 0-4 in prep_text "тест"
    # In absolute prep_text coords (pad_len=0): start=0, end=4
    t = _make_trace("тест", matches=[{"start": 0, "end": 4, "key": "тест", "value": "тест"}])
    f = _facts(trace=t)
    assert f.f1_rule == "тест"
    assert f.f1_flag == "none"
    assert f.f1_phrase is False  # single-word match


def test_f1_phrase_match():
    """Match covering 2+ words → f1_phrase=True."""
    # "два слова": два at 0-3, слова at 4-9
    t = _make_trace("два слова", matches=[{"start": 0, "end": 9, "key": "два слова", "value": "два слова"}])
    f = _facts(trace=t, form_analysis="два")
    assert f.f1_rule == "два слова"
    assert f.f1_phrase is True


def test_f1_partial_overlap_span_ambiguous():
    """Match partially overlapping the token → span_ambiguous."""
    # "тест" at 0-4; match covers only 0-2 (partial)
    t = _make_trace("тест", matches=[{"start": 0, "end": 2, "key": "те", "value": "те"}])
    f = _facts(trace=t)
    assert f.f1_flag == "span_ambiguous"


def test_f1_match_in_pad_ignored():
    """Match entirely within pad prefix → not counted for post-pad word."""
    # pad="вводный " (8 chars), post_pad="тест"
    # "тест" is at absolute coords 8-12; match in pad: 0-7
    prep = "вводный тест"
    pad_len = len("вводный ")  # 8
    t = _make_trace(prep, pad_len=pad_len,
                    matches=[{"start": 0, "end": 7, "key": "вводный", "value": "вводный"}])
    f = _facts(trace=t)
    assert f.f1_rule is None


# ---------------------------------------------------------------------------
# F2: derived from F1
# ---------------------------------------------------------------------------

def test_f2_unknown_when_f1_present():
    t = _make_trace("тест", matches=[{"start": 0, "end": 4, "key": "тест", "value": "тест"}])
    f = _facts(trace=t)
    assert f.f2_approval == "unknown"
    assert f.f2_vowel is None


def test_f2_none_when_f1_absent():
    t = _make_trace("тест", matches=[])
    f = _facts(trace=t)
    assert f.f2_approval == "none"
    assert f.f2_vowel is None


# ---------------------------------------------------------------------------
# F3: verified form lookup (advisory)
# ---------------------------------------------------------------------------

def test_f3_verified_true():
    t = _make_trace("тест")
    f = _facts(trace=t, form_analysis="тест", verified_forms={"тест"})
    assert f.f3_verified is True


def test_f3_verified_false():
    t = _make_trace("тест")
    f = _facts(trace=t, form_analysis="тест", verified_forms={"другое"})
    assert f.f3_verified is False


def test_f3_case_insensitive():
    t = _make_trace("ТЕСТ")
    f = _facts(trace=t, form_analysis="ТЕСТ", verified_forms={"тест"})
    assert f.f3_verified is True


# ---------------------------------------------------------------------------
# resolve_expected: T1/T2/T3 branches
# ---------------------------------------------------------------------------

def test_resolve_t3_default():
    src, v = _resolve()
    assert src == "none"
    assert v is None


def test_resolve_t2_ruaccent():
    src, v = _resolve(f6_status="resolved", f6_vowel=3)
    assert src == "ruaccent"
    assert v == 3


def test_resolve_t1_source_mark():
    src, v = _resolve(f5_status="ok", f5_vowel=2)
    assert src == "source_mark"
    assert v == 2


def test_resolve_t1_decision():
    src, v = _resolve(f2_approval="approved", f2_vowel=4)
    assert src == "decision"
    assert v == 4


def test_resolve_t1_conflict():
    """F5 and F2 both present but disagree → conflict."""
    src, v = _resolve(f5_status="ok", f5_vowel=2, f2_approval="approved", f2_vowel=4)
    assert src == "conflict"
    assert v is None


def test_resolve_t1_agree():
    """F5 and F2 both present and agree → source_mark."""
    src, v = _resolve(f5_status="ok", f5_vowel=2, f2_approval="approved", f2_vowel=2)
    assert src == "source_mark"
    assert v == 2


# ---------------------------------------------------------------------------
# §9 status/reason matrix — one test per row
# ---------------------------------------------------------------------------

def test_matrix_unresolved_alignment():
    """Row 1: alignment_status ≠ aligned → unresolved/<alignment_status>."""
    status, reason = _classify(alignment_status="fragment_mismatch")
    assert status == "unresolved"
    assert reason == "fragment_mismatch"


def test_matrix_unresolved_prep_token():
    status, reason = _classify(alignment_status="prep_token_mismatch")
    assert status == "unresolved"
    assert reason == "prep_token_mismatch"


def test_matrix_unresolved_trace_mismatch():
    status, reason = _classify(alignment_status="trace_mismatch")
    assert status == "unresolved"
    assert reason == "trace_mismatch"


def test_matrix_unresolved_span_ambiguous():
    """Row 2: span_ambiguous → unresolved/override_span_ambiguous."""
    status, reason = _classify(f1_flag="span_ambiguous")
    assert status == "unresolved"
    assert reason == "override_span_ambiguous"


def test_matrix_covered_by_override():
    """Row 3: complete F1 (rule set, flag=none) → covered_by_override."""
    status, reason = _classify(f1_rule="rule_x", f1_flag="none")
    assert status == "covered_by_override"
    assert reason == ""


def test_matrix_unresolved_conflict():
    """Row 4: expected_source=conflict → unresolved/conflict."""
    status, reason = _classify(expected_source="conflict")
    assert status == "unresolved"
    assert reason == "conflict"


def test_matrix_unresolved_no_stress():
    """Row 5: f6_status=no_stress → unresolved/no_stress."""
    status, reason = _classify(f6_status="no_stress")
    assert status == "unresolved"
    assert reason == "no_stress"


def test_matrix_unresolved_multi_stress():
    status, reason = _classify(f6_status="multi_stress")
    assert status == "unresolved"
    assert reason == "multi_stress"


def test_matrix_unresolved_invalid_mark():
    status, reason = _classify(f6_status="invalid_mark")
    assert status == "unresolved"
    assert reason == "invalid_mark"


def test_matrix_unresolved_tokenization_mismatch():
    status, reason = _classify(f6_status="tokenization_mismatch")
    assert status == "unresolved"
    assert reason == "tokenization_mismatch"


def test_matrix_unresolved_ruaccent_not_run():
    """Row 6: not_run with no T1 → unresolved/ruaccent_not_run."""
    status, reason = _classify(f6_status="not_run", expected_source="none")
    assert status == "unresolved"
    assert reason == "ruaccent_not_run"


def test_matrix_ok_no_info():
    """Row 7: fully covered → ok, no informational reasons."""
    # F6 resolved with same vowel as expected
    status, reason = _classify(
        f6_status="resolved", expected_source="ruaccent",
        expected_vowel=3, f6_vowel=3,
    )
    assert status == "ok"
    assert reason == ""


def test_matrix_ok_ruaccent_disagreement():
    """ok status with ruaccent disagreement informational reason."""
    status, reason = _classify(
        f6_status="resolved", expected_source="decision",
        expected_vowel=3, f6_vowel=5,  # disagree
    )
    assert status == "ok"
    assert "ruaccent_disagreement" in reason


def test_matrix_ok_verified_disagreement():
    """ok status with both disagreements → semicolon-separated."""
    status, reason = _classify(
        f6_status="resolved", expected_source="decision",
        expected_vowel=3, f6_vowel=5,
        f3_verified=True,
    )
    assert status == "ok"
    assert "ruaccent_disagreement" in reason
    assert "verified_disagreement" in reason


def test_matrix_precedence_span_ambiguous_before_f1():
    """span_ambiguous checked before f1_rule — both set, span_ambiguous wins."""
    status, reason = _classify(f1_rule="r", f1_flag="span_ambiguous")
    assert status == "unresolved"
    assert reason == "override_span_ambiguous"


def test_matrix_alignment_before_span():
    """alignment error checked before span_ambiguous."""
    status, reason = _classify(alignment_status="fragment_mismatch", f1_flag="span_ambiguous")
    assert status == "unresolved"
    assert reason == "fragment_mismatch"


# ---------------------------------------------------------------------------
# AST guard: stress_facts must not import from wordprov (I3)
# ---------------------------------------------------------------------------

def test_ast_no_wordprov_import_in_stress_facts():
    """wordprov must only appear under TYPE_CHECKING guard, never at runtime."""
    p = REPO_ROOT / "src" / "audiobook" / "stress_facts.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))

    # Collect nodes inside `if TYPE_CHECKING:` blocks
    type_checking_bodies: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            ):
                for child in ast.walk(node):
                    type_checking_bodies.add(id(child))

    for node in ast.walk(tree):
        if id(node) in type_checking_bodies:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "wordprov" not in alias.name, \
                    "stress_facts.py has runtime import of wordprov"
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "wordprov" not in mod, \
                "stress_facts.py has runtime import from wordprov"


# ---------------------------------------------------------------------------
# AST guard: F4 gold never consulted (ADR constraint)
# ---------------------------------------------------------------------------

def test_ast_no_gold_lookup_in_stress_facts():
    """stress_facts must not reference gold or f4 identifiers."""
    p = REPO_ROOT / "src" / "audiobook" / "stress_facts.py"
    source = p.read_text(encoding="utf-8")
    for forbidden in ("gold", "f4_", "F4", "gold_identity", "gold_ledger"):
        assert forbidden not in source, f"Found {forbidden!r} in stress_facts.py"


def test_fix_r3_length_changing_rules_literal_oracle():
    from audiobook import leadin
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook.stress_facts import _classify_f1
    # All strings synthetic. Prefix/suffix punctuation changes byte positions
    # without changing Cyrillic tokens; rule values never supply stress positions.
    table = {"Альфа": "+++Альфа", "бета": "бета++", "гамма": "++++гамма",
             "Ввод": "++++Ввод"}
    trace = _trace_su("01_test", "0001", None, "Альфа бета гамма", False,
                      _DeepRecordingConfig({"text_prep": {"ensure_terminal": False}}),
                      "Ввод", table, " .")
    assert trace.prep_text == "++++Ввод +++Альфа бета++ ++++гамма ."
    assert [_classify_f1(trace, i) for i in range(3)] == [
        ("Альфа", False, "none"), ("бета", False, "none"), ("гамма", False, "none")]


@pytest.mark.parametrize("source", ["decision", "source_mark"])
def test_fix_r6_t1_with_f6_not_run(source):
    assert _classify(expected_source=source, expected_vowel=0, f6_status="not_run") == ("ok", "")


def test_fix_r3_phrase_and_partial_literal_oracles():
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook.stress_facts import _classify_f1
    cfg = _DeepRecordingConfig({"text_prep": {"ensure_terminal": False}})
    trace = _trace_su("01_test", "0001", None, "Альфа бета. Гамма", False,
                      cfg, None, {"Альфа бета": "+Альфа бета++"}, " .")
    assert [_classify_f1(trace, i) for i in range(3)] == [
        ("Альфа бета", True, "none"), ("Альфа бета", True, "none"), (None, False, "none")]
    # Synthetic partial span: the same match covers a whole neighboring word.
    trace = _make_trace("альфа бета", matches=[
        {"start": 0, "end": 7, "key": "альфа б", "value": "альфа б"}])
    assert [_classify_f1(trace, i) for i in range(2)] == [
        (None, False, "span_ambiguous"), (None, False, "span_ambiguous")]


@pytest.mark.parametrize("mutation", ["value", "start", "end", "token_count"])
def test_fix_r3_unproven_coordinates_fail_closed(mutation):
    from audiobook.unitmap import AnnotationError
    from audiobook.stress_facts import _classify_f1
    match = {"start": 0, "end": 5, "key": "альфа", "value": "альфа"}
    text = "альфа"
    if mutation == "token_count":
        text, match["value"] = "два слова", "два слова"
    else:
        match[mutation] = {"value": "иначе", "start": 1, "end": 6}[mutation]
    trace = _make_trace(text, matches=[match])
    with pytest.raises(AnnotationError, match="F1_COORDINATES_UNPROVEN"):
        _classify_f1(trace, 0)


def test_fix_r6_t1_conflict_and_higher_priorities():
    assert _classify(expected_source="conflict", f6_status="not_run") == ("unresolved", "conflict")
    assert _classify(expected_source="decision", expected_vowel=None) == ("unresolved", "ruaccent_not_run")
    assert _classify(expected_source="decision", expected_vowel=0,
                     f6_status="invalid_mark") == ("unresolved", "invalid_mark")
    assert _classify(expected_source="decision", expected_vowel=0,
                     f1_flag="span_ambiguous", f1_rule="альфа") == ("unresolved", "override_span_ambiguous")
