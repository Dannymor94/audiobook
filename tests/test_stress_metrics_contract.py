"""Independent numeric and algebraic oracles for ADR §10 pure metrics.

No external source, book vocabulary, gold ledger, models, or audio is used.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from itertools import permutations

import pytest

from audiobook.stress_metrics import (
    Observation, STRATA, calculate_metrics, hint_gate, wilson_interval, yo_gate,
)


def pop(**counts):
    return {s: counts.get(s, 0) for s in STRATA}


def independent_decimal_wilson(k, n):
    if n == 0:
        return (None, None)
    with localcontext() as ctx:
        ctx.prec = 70
        z = Decimal('1.959963984540054')
        nn = Decimal(n)
        p = Decimal(k) / nn
        denom = 1 + z*z/nn
        center = (p + z*z/(2*nn))/denom
        radius = z*((p*(1-p)/nn + z*z/(4*nn*nn)).sqrt())/denom
        return float(max(Decimal(0), center-radius)), float(min(Decimal(1), center+radius))


@pytest.mark.parametrize('k,n', [
    (0, 0), (0, 1), (1, 1), (0, 10), (2, 10), (5, 10), (10, 10),
    (40, 40), (91, 100), (92, 100), (73, 73), (79, 80), (80, 80),
    (4, 7), (33, 127), (93, 127), (1, 1000), (999, 1000),
])
def test_wilson_against_independent_high_precision_decimal(k, n):
    a = wilson_interval(k, n)
    b = independent_decimal_wilson(k, n)
    if n == 0:
        assert a == b
    else:
        assert a == pytest.approx(b, abs=2e-15)


@pytest.mark.parametrize('k,n', [(0, 1), (1, 1), (2, 7), (4, 7),
                                  (30, 100), (51, 100), (91, 100), (99, 100)])
def test_wilson_complement_duality(k, n):
    lo, hi = wilson_interval(k, n)
    clo, chi = wilson_interval(n-k, n)
    assert clo == pytest.approx(1-hi, abs=2e-15)
    assert chi == pytest.approx(1-lo, abs=2e-15)


def test_three_way_gate_boundary_exactness():
    assert hint_gate(dict(n=100, lower=0.85, upper=0.90)) == 'PASS'
    assert hint_gate(dict(n=100, lower=0.849999999999, upper=0.90)) == 'INCONCLUSIVE'
    assert hint_gate(dict(n=80, lower=0.0, upper=0.8499999999)) == 'FAIL'
    assert hint_gate(dict(n=79, lower=0.90, upper=0.99)) == 'INCONCLUSIVE'
    assert hint_gate(dict(n=0, lower=None, upper=None)) == 'INCONCLUSIVE'


def test_false_suggestion_metric_is_exact_mirror_of_true_suggestion():
    obs = ([Observation('omograph', resolved=True, usable_gold=True, correct=True)]*9 +
           [Observation('omograph', resolved=True, usable_gold=True)]*3)
    result = calculate_metrics(obs, pop(omograph=12))['metrics']['overall']
    a, b = result['suggestion_precision'], result['false_suggestion_rate']
    assert (a['k'], a['n'], b['k'], b['n']) == (9, 12, 3, 12)
    assert b['rate'] == pytest.approx(1-a['rate'])
    assert b['lower'] == pytest.approx(1-a['upper'], abs=2e-15)
    assert b['upper'] == pytest.approx(1-a['lower'], abs=2e-15)


def test_independent_subset_denominators_and_total_weights():
    rows = (
        [Observation('omograph', resolved=True, usable_gold=True, correct=True)]*2 +
        [Observation('omograph', resolved=True, usable_gold=False)] +
        [Observation('tail', resolved=True, usable_gold=True, correct=False)] +
        [Observation('tail', resolved=False, usable_gold=True)]
    )
    result = calculate_metrics(rows, pop(omograph=100, tail=300))
    m = result['metrics']['overall']
    assert (m['coverage']['k'], m['coverage']['n']) == (4, 5)
    assert (m['accuracy_resolved']['k'], m['accuracy_resolved']['n']) == (2, 3)
    assert (m['suggestion_precision']['k'], m['suggestion_precision']['n']) == (2, 2)
    assert result['metrics']['book_estimates']['coverage']['rate'] == pytest.approx(
        (100/400) * 1 + (300/400) * (1/2)
    )
    assert result['metrics']['book_estimates']['accuracy_resolved']['rate'] == pytest.approx(
        (100/400) * 1 + (300/400) * 0
    )


def test_yo_changed_property_is_independent_of_stratum_assignment():
    rows = (
        [Observation('omograph', yo_changed=True, yo_correct='y')]*2 +
        [Observation('tail', yo_changed=True, yo_correct='n')] +
        [Observation('yo_changed', yo_changed=True, yo_correct='y')]
    )
    result = calculate_metrics(rows, pop(omograph=2, tail=1, yo_changed=1))
    y = result['metrics']['overall']['yo_precision']
    assert (y['k'], y['n']) == (3, 4)
    assert result['gates']['YO'] == 'YO_WARN'
    assert result['counts']['yo_wrong'] == 1


def test_metrics_are_byte_identical_across_all_permutations():
    rows = [
        Observation('omograph', resolved=True, usable_gold=True, correct=True),
        Observation('tail', resolved=True, usable_gold=True),
        Observation('top300', yo_changed=True, yo_correct='y'),
        Observation('name', resolved=False),
    ]
    populations = pop(omograph=100, tail=500, top300=200, name=300)
    baseline = calculate_metrics(rows, populations)
    for p in permutations(rows):
        assert calculate_metrics(p, populations) == baseline


def test_no_actual_gold_yields_inconclusive_not_passing_hint():
    obs = [Observation('omograph', resolved=True, usable_gold=False)]*100
    result = calculate_metrics(obs, pop(omograph=100))
    assert result['metrics']['overall']['coverage']['rate'] == 1
    assert result['metrics']['overall']['suggestion_precision']['rate'] is None
    assert result['gates']['G_hint'] == 'INCONCLUSIVE'
    assert not result['gates']['hint_allows_ordering_only']


def test_one_wrong_yo_is_warn_despite_many_other_true_judgments():
    r = calculate_metrics(
        [Observation('tail', yo_changed=True, yo_correct='y')]*199 +
        [Observation('tail', yo_changed=True, yo_correct='n')],
        pop(tail=200),
    )
    assert r['gates']['YO'] == 'YO_WARN'


@pytest.mark.parametrize('wrong,n', [(-1, 0), (1, 0), (3, 2), (1.5, 2), (True, 2)])
def test_yo_gate_rejects_invalid_wrong_counts(wrong, n):
    with pytest.raises(ValueError):
        yo_gate({'n': n, 'upper': 1.0 if n else None}, wrong)
