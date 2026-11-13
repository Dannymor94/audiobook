"""Synthetic-only additional Sol F1 oracles for the proposed B architecture.

All xfails are deliberately STRICT and pending explicit owner approval of ADR.
Do not treat expected failures as acceptance. After approval Sonnet must specify
contractual state representation, remove xfail, and independently verify PASS.
"""
from __future__ import annotations

import pytest

from audiobook import stress_eval as evaluation
from test_stress_eval_sample import context_for


def human_row(context, *, gold_vowel, yo_correct):
    occ = context.rows[0]
    return {
        **evaluation._todo_row(occ, context.sources),
        "gold_vowel": gold_vowel,
        "yo_correct": yo_correct,
        "labeler": "synthetic-human",
        "date": "2026-11-13",
    }


@pytest.mark.xfail(
    strict=True, reason="Architect B proposal, owner approval pending: legacy source-less yo remains unresolved"
)
def test_legacy_synth_only_yo_is_preserved_not_reinterpreted_or_rejected():
    units = [{"type": "text", "text": "Елепа."}]
    prior = context_for(units, synth={"Елепа.": "Ёлепа."})
    current = context_for(units)
    legacy = human_row(prior, gold_vowel="yo", yo_correct="y")
    assert prior.source_fp == current.source_fp
    state = evaluation.inspect_ledger([legacy], current)
    # No reusable stress truth for this shorthand: a human must label the
    # explicit source-vowel index. A current analysis is not historical proof.
    assert legacy["source_key"] not in state.active
    assert legacy not in state.stale
    # The approved implementation should expose a distinguishable unresolved
    # state or count, rather than a silent deletion. Adapt after ADR signature.
    assert legacy in getattr(state, "legacy_yo_unresolved", ())


@pytest.mark.xfail(
    strict=True, reason="Architect B proposal, owner approval pending: numeric gold unaffected by new ё restoration"
)
def test_numeric_stress_survives_introduced_restoration_with_na_history():
    units = [{"type": "text", "text": "Елепа."}]
    prior = context_for(units)
    current = context_for(units, synth={"Елепа.": "Ёлепа."})
    gold = human_row(prior, gold_vowel="0", yo_correct="na")
    assert prior.source_fp == current.source_fp
    previous_truth = evaluation._accepted_vowels(gold, prior.rows[0])
    state = evaluation.inspect_ledger([gold], current)
    assert state.active[gold["source_key"]]["gold_vowel"] == "0"
    assert evaluation._accepted_vowels(gold, current.rows[0]) == previous_truth == frozenset({0})
    # The new orthographic judgment MUST be requested via separate todo,
    # not inferred from historical yo_correct=na.


@pytest.mark.xfail(
    strict=True, reason="Architect B proposal, owner approval pending: native source ё independent of synth toggles"
)
def test_native_source_yo_remains_source_anchored_on_analysis_only_change():
    units = [{"type": "text", "text": "Бетё."}]
    native = context_for(units)
    alternate = context_for(units, synth={"Бетё.": "Бете."})
    gold = human_row(native, gold_vowel="yo", yo_correct="na")
    assert native.source_fp == alternate.source_fp
    state = evaluation.inspect_ledger([gold], alternate)
    assert gold["source_key"] in state.active
    assert evaluation._accepted_vowels(gold, alternate.rows[0]) == frozenset({1})


def test_zero_source_restoration_evidence_is_not_inferred_from_yo_correct_na():
    # Source/context identity alone cannot show whether an orthographic
    # restoration was ever proposed. This is an independent setup oracle.
    units = [{"type": "text", "text": "Елепа."}]
    first = context_for(units)
    second = context_for(units, synth={"Елепа.": "Ёлепа."})
    gold = human_row(first, gold_vowel="0", yo_correct="na")
    assert tuple(gold[k] for k in evaluation.IDENTITY_FIELDS) == tuple(
        evaluation._todo_row(second.rows[0], second.sources)[k]
        for k in evaluation.IDENTITY_FIELDS
    )
    assert first.rows[0].form_synth != second.rows[0].form_synth
