"""Synthetic witness: sample/1 does not commit to per-key stratum assignments.

This is a characterisation test of an existing design limitation, not an
approved change to the sampler or an authorization to regenerate owner todo.
"""
from __future__ import annotations

import hashlib
import json

from audiobook.stress_eval import select_sample
from test_stress_eval_sample import row


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _stratum_commitment(selection):
    """Illustrative sample/2 input only, not a new normative algorithm."""
    return _digest({
        "algorithm": "stratum-assignment-proposal/1",
        "assignments": sorted(selection.strata_by_key.items()),
    })


def test_sample1_can_keep_same_fp_when_per_key_stratum_swaps():
    rows = [row("Елепа", 0), row("Абрака", 1)]
    a = select_sample(
        rows, "source", "analysis", homographs={"елепа"}, names=set()
    )
    b = select_sample(
        rows, "source", "analysis", homographs={"абрака"}, names=set()
    )

    assert a.record["keys"] == b.record["keys"]
    assert a.record["strata"] == b.record["strata"]
    assert a.record["source_fp"] == b.record["source_fp"]
    assert a.record["analysis_fp"] == b.record["analysis_fp"]
    assert a.strata_by_key != b.strata_by_key
    # This demonstrates the sample/1 fingerprint gap; not a quality PASS.
    assert a.record["sample_fp"] == b.record["sample_fp"]
    assert _stratum_commitment(a) != _stratum_commitment(b)


def test_stratum_assignment_commitment_deterministic_across_row_order():
    rows = [row("Елепа", 0), row("Абрака", 1)]
    a = select_sample(
        rows, "source", "analysis", homographs={"елепа"}, names=set()
    )
    b = select_sample(
        list(reversed(rows)), "source", "analysis", homographs={"елепа"}, names=set()
    )
    assert a.record["sample_fp"] == b.record["sample_fp"]
    assert _stratum_commitment(a) == _stratum_commitment(b)
