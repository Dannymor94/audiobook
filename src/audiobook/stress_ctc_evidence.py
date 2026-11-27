"""Experimental acoustic stress evidence via competing CTC phone hypotheses.

Pure scorer; does not load a model, infer phonetic spelling or approve audio.
All vowel positions and candidate phone IDs must be independently reviewed
against the exact recognizer vocabulary before use.
"""
from __future__ import annotations

import math
import numpy as np


def _validate_log_probs(log_probs: np.ndarray, blank: int) -> np.ndarray:
    x = np.asarray(log_probs, dtype=np.float64)
    if (x.ndim != 2 or not 1 <= x.shape[0] <= 1500
            or not 2 <= x.shape[1] <= 4096
            or type(blank) is not int or not 0 <= blank < x.shape[1]
            or np.isnan(x).any() or np.isposinf(x).any()):
        raise ValueError("INVALID_CTC_POSTERIORS")
    if not np.allclose(np.logaddexp.reduce(x, axis=1), 0.0, atol=1e-5, rtol=0):
        raise ValueError("CTC_REQUIRES_NORMALIZED_LOG_PROBS")
    return x


def _validate_ids(ids, vocab_size, blank):
    if (not isinstance(ids, (tuple, list)) or not 1 <= len(ids) <= 128
            or any(type(i) is not int or not 0 <= i < vocab_size or i == blank
                   for i in ids)):
        raise ValueError("INVALID_PHONE_IDS")
    return tuple(ids)


def _ctc_forward(x, ids, blank):
    """Log sum over ALL paths collapsing to the exact phone sequence."""
    if len(ids) + sum(a == b for a, b in zip(ids, ids[1:])) > len(x):
        return -math.inf
    ext = np.full(2*len(ids)+1, blank, dtype=np.int64)
    ext[1::2] = ids
    skip = np.zeros(len(ext), dtype=bool)
    skip[3::2] = ext[3::2] != ext[1:-2:2]
    prev = np.full(len(ext), -np.inf)
    prev[0] = x[0, blank]
    prev[1] = x[0, ids[0]]
    for frame in x[1:]:
        one = np.concatenate(([-np.inf], prev[:-1]))
        two = np.concatenate(([-np.inf, -np.inf], prev[:-2]))
        two[~skip] = -np.inf
        prev = np.logaddexp(np.logaddexp(prev, one), two) + frame[ext]
    return float(np.logaddexp(prev[-1], prev[-2]))


def ctc_log_likelihood(log_probs, ids, blank=0):
    x = _validate_log_probs(log_probs, blank)
    return _ctc_forward(x, _validate_ids(ids, x.shape[1], blank), blank)


def rank_hypotheses(log_probs, hypotheses: dict[int, list[int]], *,
                    vowel_positions: list[int], blank: int,
                    allowed_phone_ids: set[int]) -> dict:
    """Compare equal-length segmental sequences varying only reviewed vowels.

    Reject/abstain rather than invent phones, drop unsupported tokens or
    compare alternatives that collapse to the same recognizer IDs. In
    particular, stress-only marker changes with identical recognized phones
    carry no information. Clitics, consonant-changing or unequal-length
    variants are out of scope for this conservative first experiment.
    """
    x = _validate_log_probs(log_probs, blank)
    n = len(vowel_positions)
    if (not 2 <= n <= 8 or any(type(k) is not int for k in hypotheses)
            or set(hypotheses) != set(range(1, n+1))
            or any(type(i) is not int for i in vowel_positions)
            or sorted(set(vowel_positions)) != vowel_positions):
        raise ValueError("EXACT_VOWEL_HYPOTHESES_REQUIRED")
    seqs = {k: _validate_ids(ids, x.shape[1], blank) for k, ids in hypotheses.items()}
    first = seqs[1]
    if any(len(s) != len(first) for s in seqs.values()):
        return {"status": "uncertain", "reason": "unequal_phone_inventory"}
    if not all(0 <= p < len(first) for p in vowel_positions):
        raise ValueError("INVALID_VOWEL_POSITIONS")
    if any(i not in allowed_phone_ids for s in seqs.values() for i in s):
        return {"status": "uncertain", "reason": "unsupported_phone"}
    if any(s[p] != first[p] for s in seqs.values()
           for p in range(len(first)) if p not in vowel_positions):
        return {"status": "uncertain", "reason": "nonvowel_difference"}
    if len(set(seqs.values())) != n:
        return {"status": "uncertain", "reason": "phone_hypothesis_collision"}
    if any(len(s) + sum(a == b for a, b in zip(s, s[1:])) > len(x)
           for s in seqs.values()):
        return {"status": "uncertain", "reason": "insufficient_frames"}
    scores = {k: _ctc_forward(x, s, blank) for k, s in seqs.items()}
    if not all(math.isfinite(v) for v in scores.values()):
        return {"status": "uncertain", "reason": "nonfinite_hypothesis_score"}
    order = sorted(scores, key=lambda k: (-scores[k], k))
    best, second = order[:2]
    margin = (scores[best] - scores[second]) / len(x)
    return dict(status="ranked", best_ordinal=best, margin_per_frame=margin,
                fit_per_frame=scores[best]/len(x), scores=scores,
                frames=len(x))


def decide(evidence: dict, *, expected_ordinal: int, min_margin: float,
           min_fit: float) -> str:
    """Thresholds supplied by frozen development calibration, never defaulted."""
    if (type(expected_ordinal) is not int or expected_ordinal < 1
            or not math.isfinite(min_margin) or min_margin <= 0
            or not math.isfinite(min_fit) or min_fit >= 0):
        raise ValueError("INVALID_FROZEN_THRESHOLDS")
    if evidence["status"] != "ranked":
        return "uncertain"
    if expected_ordinal not in evidence["scores"]:
        raise ValueError("EXPECTED_ORDINAL_NOT_IN_HYPOTHESES")
    if (evidence["margin_per_frame"] < min_margin
            or evidence["fit_per_frame"] < min_fit):
        return "uncertain"
    return ("stress_suspect" if evidence["best_ordinal"] != expected_ordinal
            else "not_flagged")


def summarize_gold(rows: list[dict]) -> dict:
    """Uncertain errors are NOT caught. Never interpret not_flagged as proof."""
    from collections import Counter
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("UNIQUE_GOLD_CONTROLS_REQUIRED")
    out = {}
    for split in ("development", "heldout"):
        selected = [r for r in rows if r["split"] == split]
        if not selected:
            raise ValueError("BOTH_SPLITS_REQUIRED")
        c = Counter((r["gold"], r["signal"]) for r in selected)
        if any(g not in ("correct", "wrong_stress", "lexical_error")
               or s not in ("stress_suspect", "not_flagged", "uncertain")
               for g, s in c):
            raise ValueError("INVALID_GOLD_OUTCOME")
        wrong = sum(v for (g, _), v in c.items() if g == "wrong_stress")
        correct = sum(v for (g, _), v in c.items() if g == "correct")
        lexical = sum(v for (g, _), v in c.items() if g == "lexical_error")
        caught = c["wrong_stress", "stress_suspect"]
        false = c["correct", "stress_suspect"]
        out[split] = dict(wrong_stress=wrong, correct=correct, lexical_error=lexical,
                          caught=caught, missed=wrong-caught,
                          uncertain_errors=c["wrong_stress", "uncertain"],
                          false_flags=false, lexical_false_stress=c["lexical_error", "stress_suspect"],
                          uncertain=sum(v for (_, s), v in c.items() if s == "uncertain"),
                          recall=caught/wrong if wrong else None,
                          false_flag_rate=false/correct if correct else None)
    if sum(s["wrong_stress"]+s["correct"]+s["lexical_error"] for s in out.values()) != len(rows):
        raise ValueError("UNKNOWN_SPLIT")
    return dict(splits=out, release_ready=False)
