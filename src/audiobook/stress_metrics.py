"""Pure aggregate stress-quality metrics for T15-7.8, Final ADR §10.

The caller must validate current sample/ledger identity, resolve active human gold,
exclude incomplete samples, and map each selected occurrence to one Observation.
This module never reads manuscript, audio, models, or files and never authorizes
synthesis. Unrounded Wilson bounds govern gates; rounding is presentation-only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping

STRATA = ("omograph", "top300", "name", "override_covered", "yo_changed", "tail")
METRIC_NAMES = ("coverage", "unresolved_rate", "accuracy_resolved",
                "suggestion_precision", "false_suggestion_rate", "yo_precision",
                "override_disagreement")
WILSON_Z_95 = 1.959963984540054


@dataclass(frozen=True, slots=True)
class Observation:
    """Prevalidated synthetic/aggregate observation: no text, keys, or labels."""
    stratum: str
    eligible: bool = True
    resolved: bool = False
    usable_gold: bool = False
    correct: bool = False
    yo_changed: bool = False
    yo_correct: str = "na"
    covered_by_override: bool = False


def _count(x: int, name: str) -> None:
    if type(x) is not int or x < 0:
        raise ValueError(f"{name} must be a nonnegative int")


def wilson_interval(k: int, n: int) -> tuple[float | None, float | None]:
    """Exact ADR Wilson 95% interval; zero-denominator returns undefined."""
    _count(k, "k")
    _count(n, "n")
    if k > n:
        raise ValueError("k exceeds n")
    if n == 0:
        return None, None
    p, z = k / n, WILSON_Z_95
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    # Correct floating noise at exact k=0 and k=n without rounding real bounds.
    return max(0.0, min(p, center - half)), min(1.0, max(p, center + half))


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "rate": k / n if n else None, "lower": lo, "upper": hi}


def hint_gate(precision: Mapping) -> str:
    n, lo, hi = precision["n"], precision["lower"], precision["upper"]
    _count(n, "precision denominator")
    if not n:
        return "INCONCLUSIVE"
    if not isinstance(lo, (float, int)) or not isinstance(hi, (float, int)):
        raise ValueError("missing Wilson bounds")
    if n >= 80 and lo >= 0.85:
        return "PASS"
    if hi < 0.85:
        return "FAIL"
    return "INCONCLUSIVE"


def yo_gate(precision: Mapping, wrong_count: int) -> str:
    n = precision["n"]
    _count(n, "yo denominator")
    _count(wrong_count, "yo wrong")
    if wrong_count > n:
        raise ValueError("wrong count exceeds yo denominator")
    if wrong_count:
        return "YO_WARN"
    hi = precision["upper"]
    if n and (not isinstance(hi, (float, int)) or not 0 <= hi <= 1):
        raise ValueError("invalid Wilson upper")
    return "YO_WARN" if n and hi < 0.95 else "YO_NO_EVIDENCE"


def _rates(rows: list[Observation]) -> dict:
    e = [r for r in rows if r.eligible]
    r = [x for x in e if x.resolved]
    u = [x for x in r if x.usable_gold]
    o = [x for x in u if x.stratum == "omograph"]
    y = [x for x in rows if x.yo_changed and x.yo_correct in {"y", "n"}]
    f = [x for x in u if x.covered_by_override]
    s = sum(x.correct for x in o)
    return {
        "coverage": _rate(len(r), len(e)),
        "unresolved_rate": _rate(len(e) - len(r), len(e)),
        "accuracy_resolved": _rate(sum(x.correct for x in u), len(u)),
        "suggestion_precision": _rate(s, len(o)),
        "false_suggestion_rate": _rate(len(o) - s, len(o)),
        "yo_precision": _rate(sum(x.yo_correct == "y" for x in y), len(y)),
        "override_disagreement": _rate(sum(not x.correct for x in f), len(f)),
    }


def calculate_metrics(observations: Iterable[Observation], population_by_stratum: Mapping[str, int]) -> dict:
    """Return aggregate counts, per-stratum/overall rates, Wilson and gates.

    Population sizes N_s must come from the independently validated sample.
    The weighted book estimate is Σ_s (N_s/N)·rate_s for defined strata only;
    undefined strata never cause renormalization. No COMPLETE status is decided.
    """
    if set(population_by_stratum) != set(STRATA):
        raise ValueError("exactly six ADR strata required")
    pops = dict(population_by_stratum)
    for name, n in pops.items():
        _count(n, f"population {name}")
    rows = list(observations)
    groups: dict[str, list[Observation]] = {s: [] for s in STRATA}
    for row in rows:
        if not isinstance(row, Observation):
            raise TypeError("expected Observation")
        if row.stratum not in groups:
            raise ValueError("unknown stratum")
        for name in ("eligible", "resolved", "usable_gold", "correct", "yo_changed", "covered_by_override"):
            if type(getattr(row, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        if row.yo_correct not in ("y", "n", "na") or (row.yo_changed and row.yo_correct == "na"):
            raise ValueError("invalid yo judgment")
        if row.correct and not (row.resolved and row.usable_gold):
            raise ValueError("correct requires resolved prediction and usable gold")
        groups[row.stratum].append(row)
    if any(len(groups[s]) > pops[s] for s in STRATA):
        raise ValueError("selected sample exceeds population")

    per_stratum = {s: _rates(groups[s]) for s in STRATA}
    overall = _rates(rows)
    N = sum(pops.values())
    weighted = {}
    for metric in METRIC_NAMES:
        defined = [s for s in STRATA if per_stratum[s][metric]["rate"] is not None]
        weighted[metric] = {
            "rate": (sum(pops[s] / N * per_stratum[s][metric]["rate"] for s in defined)
                     if N and defined else None),
            "covered_population": sum(pops[s] for s in defined),
            "total_population": N,
        }
    wrong = sum(x.yo_changed and x.yo_correct == "n" for x in rows)
    hint = hint_gate(overall["suggestion_precision"])
    return {
        "counts": {"selected": len(rows), "eligible": sum(x.eligible for x in rows),
                   "yo_wrong": wrong, "by_stratum": {
                       s: {"N": pops[s], "selected": len(groups[s])} for s in STRATA}},
        "metrics": {"overall": overall, "by_stratum": per_stratum,
                    "book_estimates": weighted},
        "gates": {"G_hint": hint, "hint_allows_ordering_only": hint == "PASS",
                  "YO": yo_gate(overall["yo_precision"], wrong)},
    }


__all__ = ["STRATA", "METRIC_NAMES", "WILSON_Z_95", "Observation",
           "wilson_interval", "hint_gate", "yo_gate", "calculate_metrics"]
