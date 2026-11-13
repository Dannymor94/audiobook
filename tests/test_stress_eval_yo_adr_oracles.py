"""Independent source-free F1 regression probes for historical restored-ё gold.

These tests do NOT choose an ADR migration/schema design. The xfail cases pin the
dangerous CURRENT behavior: an unchanged human label must not silently refer to
a different stress vowel after only analysis/synthesis ё placement moves.

Their strict xfail markers are a temporary blocker tracker, NOT a passing
acceptance gate. After the architect approves the new contract, adapt the
assertions to that contract, REMOVE each xfail, and require ordinary PASS.
"""
from __future__ import annotations

import pytest

from audiobook import stress_eval as evaluation
from test_stress_eval_sample import context_for


# All examples below are invented synthetic strings, never book excerpts.
@pytest.mark.parametrize(
    "source,old_synth,new_synth",
    [
        ("Елепа.", "Ёлепа.", "Елёпа."),
        ("Елепа.", "Елёпа.", "Ёлепа."),
        ("Еребея.", "Еребёя.", "Ёребея."),
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason="WP-4 Sol F1: ten-column source-only gold lacks historical ё position; ADR pending",
)
def test_gold_yo_never_silently_moves_to_new_stress_vowel(
    source: str, old_synth: str, new_synth: str
) -> None:
    units = [{"type": "text", "text": source}]
    former = context_for(units, synth={source: old_synth})
    current = context_for(units, synth={source: new_synth})
    assert former.source_fp == current.source_fp
    old_occ, current_occ = former.rows[0], current.rows[0]
    assert old_occ.source_key == current_occ.source_key
    assert old_occ.form_source == current_occ.form_source

    gold = evaluation._todo_row(old_occ, former.sources)
    gold = {
        **gold,
        "gold_vowel": "yo",
        "yo_correct": "y",
        "labeler": "synthetic-human",
        "date": "2026-11-13",
    }
    identity_fields = evaluation.IDENTITY_FIELDS
    assert all(gold[field] == evaluation._todo_row(
        current_occ, current.sources
    )[field] for field in identity_fields)

    first_truth = evaluation._accepted_vowels(gold, old_occ)
    assert len(first_truth) == 1
    state = evaluation.inspect_ledger([gold], current)

    # Either the old human judgment remains bound to the same vowel, or
    # the new contract explicitly requires fresh proof (row not active).
    # What is forbidden: accept the same immutable row as ACTIVE with a
    # different stressed-vowel index inferred from the current synthesis.
    if gold["source_key"] in state.active:
        second_truth = evaluation._accepted_vowels(
            state.active[gold["source_key"]], current_occ
        )
        assert second_truth == first_truth, (
            "Historical human gold_vowel=yo silently changed accepted vowel"
        )
    else:
        assert gold in state.stale


def test_source_only_identity_is_unchanged_by_yo_analysis_move() -> None:
    source = "Елепа."
    units = [{"type": "text", "text": source}]
    before = context_for(units, synth={source: "Ёлепа."})
    after = context_for(units, synth={source: "Елёпа."})
    a = evaluation._todo_row(before.rows[0], before.sources)
    b = evaluation._todo_row(after.rows[0], after.sources)
    assert before.source_fp == after.source_fp
    assert tuple(a[key] for key in evaluation.IDENTITY_FIELDS) == tuple(
        b[key] for key in evaluation.IDENTITY_FIELDS
    )
    assert before.rows[0].form_synth != after.rows[0].form_synth
