import gzip
import hashlib

import pytest

from audiobook.stress_consensus import audit
from audiobook.stress_lexicon import evidence, load_candidates


def compressed(text):
    data = gzip.compress(text.encode("utf-8"))
    return data, hashlib.sha256(data).hexdigest()


def test_exact_lowercase_and_codepoint_index():
    data, digest = compressed("молоко\t6\nсобака\t4\nёлка\t1\n")
    assert load_candidates(data, {"Молоко", "собака", "елка", "ёлка"}, digest) == {
        "молоко": 5, "собака": 3, "ёлка": 0,
    }
    with pytest.raises(ValueError, match="DICTIONARY_SHA256_MISMATCH"):
        load_candidates(data, {"молоко"}, "0" * 64)


@pytest.mark.parametrize("text", ["молоко\t1\n", "молоко\t0\n", "молоко\t6\nмолоко\t6\n", "молоко\t6\t2\n"])
def test_invalid_matched_rows_fail(text):
    data, digest = compressed(text)
    with pytest.raises(ValueError, match="INVALID_MATCHED_DICTIONARY_ROW"):
        load_candidates(data, {"молоко"}, digest)


def test_dictionary_is_not_tiebreaker_or_gold():
    rows = [{"id": "a", "hash": "h", "text": "Замок замок молоко береза"}]
    records, _ = audit(rows, lambda t: "З+амок зам+ок молок+о береза",
                       lambda t: "З+амок з+амок молоко береза")
    data, digest = compressed("замок\t2\nмолоко\t6\nбереза\t4\n")
    candidates = load_candidates(data, {r["word"] for r in records}, digest)
    results, summary = evidence(rows, records, candidates)
    assert [r["lexical_evidence"] for r in results] == [
        "supports_dual_candidate", "context_conflict", "supports_single_candidate",
        "dictionary_only_candidate",
    ]
    assert summary["dictionary_hits"] == 4
    assert summary["decisions_approved"] == 0
    assert not summary["release_ready"]
    assert all(r["decision"] is None and not r["pronunciation_verified"] for r in results)


def test_conflict_missing_and_mixed_tokens():
    rows = [{"id": "a", "hash": "h", "text": "Замок молоко Aбереза по-русски"}]
    records, _ = audit(rows, lambda t: t.replace("Замок", "З+амок"),
                       lambda t: t.replace("Замок", "З+амок"))
    result, _ = evidence(rows, records, {"замок": 3, "береза": 3, "русски": 1})
    assert [r["lexical_evidence"] for r in result] == [
        "dictionary_conflict", "dictionary_missing", "context_or_token_review",
        "context_or_token_review",
    ]
    with pytest.raises(ValueError, match="MISSING_FINDINGS"):
        evidence(rows, records[:-1], {})


def test_bad_predictor_index_cannot_be_supported():
    rows = [{"id": "a", "hash": "h", "text": "Замок"}]
    records, _ = audit(rows, lambda t: "З+амок", lambda t: "З+амок")
    records[0]["ruaccent_stress"] = True
    with pytest.raises(ValueError, match="INVALID_PREDICTOR_INDEX"):
        evidence(rows, records, {"замок": 1})
