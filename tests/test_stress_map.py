import hashlib

import pytest

from audiobook.stress_consensus import compare
from audiobook.stress_lexicon import evidence
from audiobook.stress_map import build, jsonl, title_input


def fixture(text, original, lowered=None, *, silero=None, dictionary=None,
            accents=None, homographs=None):
    row = {"id": "synthetic:1", "text": text,
           "hash": hashlib.sha256(text.encode()).hexdigest()}
    findings = [{**f, "id": row["id"], "hash": row["hash"]}
                for f in compare(text, original, silero or original)]
    lexical, _ = evidence([row], findings, dictionary or {})
    predictions = [dict(id=row["id"], hash=row["hash"], original=original,
                        title_lower=lowered if lowered is not None else original)]
    return ([row], findings, lexical, predictions,
            dict(accents=accents or {}, omographs=homographs or {}, yo_homographs={}))


def test_title_input_preserves_offsets_and_nonstandalone():
    assert title_input("Топливо, ЗАМОК, А, А-Второй, XТекст.") == (
        "топливо, ЗАМОК, А, А-Второй, XТекст.")


def test_map_dictionary_and_homograph_context():
    args = fixture("Топливо и замок.", "Т+опливо и зам+ок.", "т+опливо и зам+ок.",
                   dictionary={"топливо": 1, "замок": 1},
                   accents={"топливо": "т+опливо"},
                   homographs={"замок": ["з+амок", "зам+ок"]})
    result, summary = build(*args, [])
    assert [r["status"] for r in result] == ["auto", "auto"]
    assert [r["stress_index"] for r in result] == [1, 3]
    assert "case_policy_change" not in result[0]["risk_flags"]
    assert "homograph" in result[1]["risk_flags"]
    assert "dictionary_exception" in result[1]["risk_flags"]
    assert result[1]["candidates"]["homograph_readings"] == [["з+амок", "зам+ок"]]
    assert summary["rows"] == 2
    assert summary["statuses"] == {"auto": 2, "confirmed": 0, "unresolved": 0}
    assert jsonl(result) == jsonl(build(*args, [])[0])


def test_case_change_unresolved_and_exact_human_override():
    args = fixture("Замок.", "З+амок.", "зам+ок.", dictionary={"замок": 1},
                   homographs={"замок": ["з+амок", "зам+ок"]})
    result, summary = build(*args, [])
    assert result[0]["status"] == "unresolved"
    assert result[0]["stress_index"] is None
    assert "case_policy_change" in result[0]["risk_flags"]
    assert summary["title_case"]["changed_stress"] == 1
    decision = {k: result[0][k] for k in ("id", "hash", "start", "end", "word", "ordinal")}
    decision.update(authority="human", stress_index=1, reason="synthetic approved context")
    confirmed, _ = build(*args, [decision])
    assert confirmed[0]["status"] == "confirmed"
    assert confirmed[0]["stress_index"] == 1
    with pytest.raises(ValueError, match="INVALID_HUMAN_DECISION"):
        build(*args, [dict(decision, hash="wrong")])


def test_conflict_and_unsafe_tokens_are_retained():
    args = fixture("Мука Xтопливо.", "М+ука Xт+опливо.", "м+ука Xт+опливо.",
                   dictionary={"мука": 3}, accents={"мука": "м+ука", "топливо": "т+опливо"})
    result, summary = build(*args, [])
    assert len(result) == 2
    assert all(r["status"] == "unresolved" for r in result)
    assert "dictionary_conflict" in result[0]["risk_flags"]
    assert "token_review" in result[1]["risk_flags"]
    assert summary["risky_occurrences"] == 2


def test_missing_inventory_fails():
    args = fixture("Топливо.", "Т+опливо.", "т+опливо.")
    rows, findings, lexical, predictions, dictionaries = args
    with pytest.raises(ValueError, match="MISSING_FINDINGS"):
        build(rows, [], [], predictions, dictionaries, [])
    with pytest.raises(ValueError, match="PREDICTION_INVENTORY_MISMATCH"):
        build(rows, findings, lexical, [], dictionaries, [])
