import pytest

from audiobook.stress_consensus import audit
from audiobook.stress_context_replay import local_candidates, replay
from audiobook.stress_lexicon import evidence


def test_unique_local_context_after_unrelated_substitution():
    text = "Вчера мы видим молоко сегодня."
    output = "З+автра мы в+идим молок+о сег+одня."
    got = local_candidates(text, output)
    assert got[4] == ("молоко", 5, "local_context")
    assert 1 not in got
    assert 5 not in got
    assert 2 not in got


def test_repeated_or_compound_not_locally_guessed():
    assert 4 not in local_candidates(
        "Вчера мы видим молоко сегодня молоко.",
        "З+автра мы в+идим молок+о сег+одня молок+о.")
    assert 4 not in local_candidates(
        "Вчера мы видим-молоко сегодня.",
        "З+автра мы в+идим-молок+о сег+одня.")


def test_replay_keeps_candidates_unapproved_and_detects_stale_evidence():
    rows = [{"id": "a", "hash": "h", "text": "Вчера мы видим молоко сегодня."}]
    diagnostics = []
    findings, _ = audit(rows, lambda _: "З+автра мы в+идим молок+о сег+одня.",
                        lambda _: "Вчер+а мы в+идим молок+о сег+одня.",
                        row_diagnostics=diagnostics)
    lexical, _ = evidence(rows, findings, {"молоко": 5})
    queue, summary = replay(rows, findings, diagnostics, lexical)
    target = next(r for r in queue if r["word"] == "молоко")
    assert target["recovery"] == "candidate_agreement"
    assert target["decision"] is None
    assert summary["decisions_approved"] == 0
    assert not summary["release_ready"]
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        replay(rows, findings, [dict(diagnostics[0], ruaccent_output="")], lexical)
    with pytest.raises(ValueError, match="MISSING_DIAGNOSTICS"):
        replay(rows, findings, [], lexical)
    with pytest.raises(ValueError, match="LEXICAL_INVENTORY_MISMATCH"):
        replay(rows, findings, diagnostics, lexical[:-1])


def test_conflicts_preserve_original_proposals():
    rows = [{"id": "a", "hash": "h", "text": "Замок."}]
    diagnostics = []
    findings, _ = audit(rows, lambda _: "З+амок.", lambda _: "Зам+ок.",
                        row_diagnostics=diagnostics)
    lexical, _ = evidence(rows, findings, {"замок": 3})
    queue, summary = replay(rows, findings, diagnostics, lexical)
    assert queue[0]["ruaccent_candidate"] == ("Замок", 1, "full")
    assert queue[0]["silero_candidate"] == ("Замок", 3, "full")
    assert summary["queued_occurrences"] == 1
