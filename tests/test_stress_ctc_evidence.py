from itertools import product

import numpy as np
import pytest

from audiobook.stress_ctc_evidence import ctc_log_likelihood, rank_hypotheses, decide, summarize_gold


def collapse(path):
    out = []
    previous = None
    for p in path:
        if p != previous and p != 0:
            out.append(p)
        previous = p
    return tuple(out)


@pytest.mark.parametrize("target", [(1,), (1, 2), (1, 1), (2, 1, 2)])
def test_forward_matches_exhaustive_paths(target):
    probs = np.array([[.2, .5, .3], [.5, .2, .3], [.1, .2, .7], [.3, .5, .2]])
    truth = sum(np.prod([probs[t, p] for t, p in enumerate(path)])
                for path in product(range(3), repeat=len(probs))
                if collapse(path) == target)
    actual = ctc_log_likelihood(np.log(probs), target)
    assert np.exp(actual) == pytest.approx(truth)


def rank(hypotheses=None, allowed=None):
    # Synthetic recognizer posterior, deliberately NOT a Russian sound sample.
    probs = np.full((5, 6), .02)
    for t, label in enumerate([1, 2, 3, 4, 0]):
        probs[t, label] = .90
    return rank_hypotheses(np.log(probs),
                           hypotheses or {1: [1, 2, 3, 4], 2: [1, 4, 3, 2]},
                           vowel_positions=[1, 3], blank=0,
                           allowed_phone_ids=allowed if allowed is not None else set(range(1, 6)))


def test_rank_and_explicit_abstention():
    evidence = rank()
    assert evidence["best_ordinal"] == 1
    assert evidence["margin_per_frame"] > 0
    assert decide(evidence, expected_ordinal=2, min_margin=.1, min_fit=-2) == "stress_suspect"
    assert decide(evidence, expected_ordinal=1, min_margin=.1, min_fit=-2) == "not_flagged"
    assert decide(evidence, expected_ordinal=2, min_margin=100, min_fit=-2) == "uncertain"


@pytest.mark.parametrize("hypotheses,allowed,reason", [
    ({1: [1, 2, 3, 4], 2: [1, 2, 3, 4]}, None, "phone_hypothesis_collision"),
    ({1: [1, 2, 3, 4], 2: [1, 4, 5, 2]}, None, "nonvowel_difference"),
    ({1: [1, 2, 3, 4], 2: [1, 4, 3]}, None, "unequal_phone_inventory"),
    (None, {1, 2, 3}, "unsupported_phone"),
])
def test_uncomparable_variants_abstain(hypotheses, allowed, reason):
    e = rank(hypotheses, allowed)
    assert e == {"status": "uncertain", "reason": reason}
    assert decide(e, expected_ordinal=1, min_margin=.1, min_fit=-2) == "uncertain"


def test_invalid_or_unreachable_ctc():
    with pytest.raises(ValueError, match="NORMALIZED"):
        ctc_log_likelihood(np.zeros((3, 3)), [1])
    with pytest.raises(ValueError, match="INVALID_PHONE"):
        ctc_log_likelihood(np.log(np.full((3, 3), 1/3)), [0])
    assert ctc_log_likelihood(np.log(np.full((2, 3), 1/3)), [1, 1]) == -np.inf


def test_uncertain_errors_count_as_missed():
    rows = [
        dict(id="1", split="development", gold="correct", signal="not_flagged"),
        dict(id="2", split="heldout", gold="wrong_stress", signal="uncertain"),
        dict(id="3", split="heldout", gold="wrong_stress", signal="stress_suspect"),
        dict(id="4", split="heldout", gold="correct", signal="stress_suspect"),
        dict(id="5", split="heldout", gold="lexical_error", signal="stress_suspect"),
    ]
    s = summarize_gold(rows)
    h = s["splits"]["heldout"]
    assert h["recall"] == .5 and h["missed"] == 1 and h["uncertain_errors"] == 1
    assert h["false_flags"] == h["lexical_false_stress"] == 1
    assert s["release_ready"] is False
