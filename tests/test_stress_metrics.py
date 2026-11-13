"""Standalone, source-free synthetic oracles for T15-7.8 §10 score arithmetic."""
from __future__ import annotations

import pytest

from audiobook.stress_metrics import (
    STRATA, Observation, calculate_metrics, hint_gate, wilson_interval, yo_gate,
)


def populations(**kw):
    return {s: kw.get(s, 0) for s in STRATA}


def observed(stratum: str = "tail", **kwargs) -> Observation:
    return Observation(stratum, **kwargs)


def rate(rows, metric, pops=None):
    if pops is None:
        pops = populations(**{s: len([x for x in rows if x.stratum == s]) for s in STRATA})
    return calculate_metrics(rows, pops)["metrics"]["overall"][metric]


@pytest.mark.parametrize("k,n,expected", [
    (40, 40, 0.9124), (92, 100, 0.8500), (91, 100, 0.8377),
    (73, 73, 0.9500),
])
def test_wilson_adr_reference_rounded(k, n, expected):
    lower, upper = wilson_interval(k, n)
    assert round(lower, 4) == expected
    assert lower <= k / n <= upper


def test_wilson_reference_92_100_exact_gate_boundary():
    lower, upper = wilson_interval(92, 100)
    assert 0.85001 < lower < 0.85003
    assert upper > lower
    assert hint_gate({"n": 100, "lower": lower, "upper": upper}) == "PASS"


def test_wilson_91_100_is_inconclusive():
    lower, upper = wilson_interval(91, 100)
    assert lower < 0.85 < upper
    assert hint_gate({"n": 100, "lower": lower, "upper": upper}) == "INCONCLUSIVE"


def test_wilson_undefined_no_false_zero():
    assert wilson_interval(0, 0) == (None, None)
    r = rate([], "coverage")
    assert r == {"k": 0, "n": 0, "rate": None, "lower": None, "upper": None}


@pytest.mark.parametrize("k,n", [(-1, 0), (1, -1), (2, 1), (True, 1), (0, False), (1.0, 2)])
def test_wilson_rejects_invalid_counts(k, n):
    with pytest.raises(ValueError):
        wilson_interval(k, n)


def test_wilson_zero_and_all_success_are_bounded():
    assert wilson_interval(0, 40)[0] == 0.0
    assert wilson_interval(40, 40)[1] == 1.0


def test_coverage_and_unresolved_rate_are_complements_with_mirrored_wilson():
    rows = [observed(resolved=True), observed(resolved=True), observed(resolved=False)]
    a = rate(rows, "coverage")
    b = rate(rows, "unresolved_rate")
    assert (a["k"], a["n"]) == (2, 3)
    assert (b["k"], b["n"]) == (1, 3)
    assert a["rate"] + b["rate"] == pytest.approx(1)
    assert b["lower"] == pytest.approx(1 - a["upper"], abs=1e-15)
    assert b["upper"] == pytest.approx(1 - a["lower"], abs=1e-15)


def test_resolved_accuracy_excludes_unusable_gold_and_unresolved():
    rows = [
        observed(resolved=True, usable_gold=True, correct=True),
        observed(resolved=True, usable_gold=True),
        observed(resolved=True, usable_gold=False),
        observed(resolved=False, usable_gold=True),
    ]
    assert rate(rows, "accuracy_resolved")["k"] == 1
    assert rate(rows, "accuracy_resolved")["n"] == 2
    assert rate(rows, "coverage")["n"] == 4
    assert rate(rows, "coverage")["k"] == 3


def test_precision_only_omograph_and_false_rate_mirror():
    rows = [
        observed("omograph", resolved=True, usable_gold=True, correct=True),
        observed("omograph", resolved=True, usable_gold=True),
        observed("tail", resolved=True, usable_gold=True, correct=True),
        observed("omograph", resolved=True, usable_gold=False),
    ]
    a = rate(rows, "suggestion_precision")
    b = rate(rows, "false_suggestion_rate")
    assert (a["k"], a["n"]) == (1, 2)
    assert (b["k"], b["n"]) == (1, 2)
    assert b["lower"] == pytest.approx(1 - a["upper"])
    assert b["upper"] == pytest.approx(1 - a["lower"])


def test_override_disagreement_denominator_is_resolved_and_usable():
    rows = [
        observed(resolved=True, usable_gold=True, covered_by_override=True, correct=False),
        observed(resolved=True, usable_gold=True, covered_by_override=True, correct=True),
        observed(resolved=False, usable_gold=True, covered_by_override=True),
        observed(resolved=True, usable_gold=False, covered_by_override=True),
    ]
    a = rate(rows, "override_disagreement")
    assert (a["k"], a["n"]) == (1, 2)


def test_yo_precision_only_yo_changed_and_independently_human_judged():
    rows = [
        observed(yo_changed=True, yo_correct="y"),
        observed(yo_changed=True, yo_correct="n"),
        observed(yo_changed=False, yo_correct="y"),
    ]
    a = rate(rows, "yo_precision")
    assert (a["k"], a["n"]) == (1, 2)
    assert calculate_metrics(rows, populations(tail=3))["gates"]["YO"] == "YO_WARN"


def test_yo_warn_on_any_wrong_even_if_confidence_high():
    rows = [observed(yo_changed=True, yo_correct="y") for _ in range(100)]
    rows.append(observed(yo_changed=True, yo_correct="n"))
    m = calculate_metrics(rows, populations(tail=101))
    assert m["counts"]["yo_wrong"] == 1
    assert m["gates"]["YO"] == "YO_WARN"


def test_yo_no_evidence_with_only_good_small_sample():
    rows = [observed(yo_changed=True, yo_correct="y") for _ in range(4)]
    m = calculate_metrics(rows, populations(tail=4))
    assert m["gates"]["YO"] == "YO_NO_EVIDENCE"
    assert m["metrics"]["overall"]["yo_precision"]["upper"] == 1


def test_yo_no_evidence_zero_denominator():
    m = calculate_metrics([], populations())
    assert m["gates"]["YO"] == "YO_NO_EVIDENCE"
    assert m["metrics"]["overall"]["yo_precision"]["rate"] is None


def test_yo_gate_warns_if_upper_lower_than_threshold_without_wrong():
    # This condition is only independently reachable for an externally supplied
    # aggregate; real all-success Wilson intervals have upper=1.
    assert yo_gate({"n": 3, "upper": 0.94}, wrong_count=0) == "YO_WARN"


def test_hint_fail_even_with_small_denominator_if_upper_below_threshold():
    lower, upper = wilson_interval(0, 10)
    assert hint_gate({"n": 10, "lower": lower, "upper": upper}) == "FAIL"


def test_hint_inconclusive_with_n_less_than_80_even_if_perfect():
    lower, upper = wilson_interval(73, 73)
    assert hint_gate({"n": 73, "lower": lower, "upper": upper}) == "INCONCLUSIVE"


def test_hint_inconclusive_n_zero():
    assert hint_gate({"n": 0, "lower": None, "upper": None}) == "INCONCLUSIVE"


def test_hint_true_pass_allows_only_ordering_flag():
    rows = ([observed("omograph", resolved=True, usable_gold=True, correct=True) for _ in range(92)] +
            [observed("omograph", resolved=True, usable_gold=True) for _ in range(8)])
    result = calculate_metrics(rows, populations(omograph=100))
    assert result["gates"] == {"G_hint": "PASS", "hint_allows_ordering_only": True,
                               "YO": "YO_NO_EVIDENCE"}


def test_book_weights_do_not_renormalize_to_defined_strata():
    rows = [observed("omograph", resolved=True), observed("omograph", resolved=True)]
    pops = populations(omograph=10, tail=30)
    result = calculate_metrics(rows, pops)
    weighted = result["metrics"]["book_estimates"]["coverage"]
    assert weighted == {"rate": 0.25, "covered_population": 10, "total_population": 40}
    assert result["metrics"]["book_estimates"]["suggestion_precision"]["rate"] is None


def test_book_weighted_rates_are_deterministic_across_input_order():
    rows = [
        observed("omograph", resolved=True), observed("omograph", resolved=False),
        observed("tail", resolved=True), observed("tail", resolved=True),
    ]
    pops = populations(omograph=10, tail=20)
    a = calculate_metrics(rows, pops)
    b = calculate_metrics(list(reversed(rows)), pops)
    assert a == b
    assert a["metrics"]["book_estimates"]["coverage"]["rate"] == pytest.approx(5 / 6)


def test_all_strata_exposed_in_normative_order():
    m = calculate_metrics([], populations())
    assert tuple(m["metrics"]["by_stratum"]) == STRATA
    assert tuple(m["counts"]["by_stratum"]) == STRATA


@pytest.mark.parametrize("bad", [
    observed("extra"), observed(yo_changed=True), observed(yo_correct="bad"),
    observed(resolved=False, usable_gold=True, correct=True),
    observed(resolved=True, usable_gold=False, correct=True),
    observed(eligible=1),
])
def test_rejects_invalid_observations(bad):
    with pytest.raises((ValueError, TypeError)):
        calculate_metrics([bad], populations(tail=1))


def test_rejects_incomplete_population_map():
    with pytest.raises(ValueError):
        calculate_metrics([], {"tail": 10})


@pytest.mark.parametrize("invalid", [-1, True, 1.5])
def test_rejects_invalid_population_size(invalid):
    with pytest.raises(ValueError):
        calculate_metrics([], populations(tail=invalid))


def test_rejects_selected_greater_than_population():
    with pytest.raises(ValueError):
        calculate_metrics([observed(), observed()], populations(tail=1))


def test_empty_metrics_do_not_claim_pass_or_quality():
    m = calculate_metrics([], populations())
    assert m["gates"] == {"G_hint": "INCONCLUSIVE",
                           "hint_allows_ordering_only": False,
                           "YO": "YO_NO_EVIDENCE"}
    for r in m["metrics"]["overall"].values():
        assert (r["n"], r["rate"], r["lower"], r["upper"]) == (0, None, None, None)


def test_result_contains_only_aggregates_not_private_data():
    rows = [observed("tail", resolved=True, usable_gold=True, correct=True)]
    data = calculate_metrics(rows, populations(tail=1))
    flat = repr(data)
    assert "source_key" not in flat
    assert "form_source" not in flat
    assert "labeler" not in flat
    assert "context" not in flat
