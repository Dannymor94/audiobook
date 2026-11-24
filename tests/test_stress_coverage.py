import pytest

from audiobook.stress_consensus import audit
from audiobook.stress_coverage import build_ledger, spans


def fixture():
    rows = [{"id": "1", "hash": "h", "text": "Молоко и в дом. По-русски, 42, AI, ё, Aдом, $."}]
    records, _ = audit(rows, lambda t: t.replace("Молоко", "Молок+о"),
                       lambda t: t.replace("Молоко", "Молоко\u0301"))
    return rows, records


def test_all_runs_accounted():
    rows, findings = fixture()
    ledger, summary = build_ledger(rows, findings)
    assert [x["token"] for x in ledger] == [
        "Молоко", "и", "в", "дом", "По", "русски", "42", "AI", "ё", "Aдом", "$"]
    assert summary["token_runs"] == sum(summary["statuses"].values()) == 11
    assert summary["dual_agreement_tokens"] == 1
    assert summary["statuses"]["compound_review"] == 2
    assert summary["statuses"]["other_pronunciation_review"] == 4
    assert summary["statuses"]["monosyllable_context_review"] == 3
    assert summary["statuses"]["vowelless_context_review"] == 1
    assert not summary["release_ready"]
    assert not any(x["pronunciation_verified"] for x in ledger)


def test_identity_and_missing_data_fail_closed():
    rows, findings = fixture()
    with pytest.raises(ValueError, match="MISSING_FINDINGS"):
        build_ledger(rows, findings[:-1])
    with pytest.raises(ValueError, match="UNEXPECTED_OR_DUPLICATE_FINDING"):
        build_ledger(rows, findings + findings[:1])
    with pytest.raises(ValueError, match="FINDING_IDENTITY_MISMATCH"):
        build_ledger(rows, [dict(findings[0], hash="stale"), *findings[1:]])
    with pytest.raises(ValueError, match="DUPLICATE_ROW"):
        build_ledger(rows + rows, findings)


def test_unicode_and_no_silent_omission():
    source = "Слово\u0301, café Ⅳ + 5%!"
    tokens = [source[a:b] for a, b in spans(source)]
    assert tokens == ["Слово\u0301", "café", "Ⅳ", "+", "5"]
    # Percent is punctuation, but meaningful in speech: normalization must
    # resolve it upstream; ledger is not proof of source-to-speech equivalence.
    assert source.endswith("%!")


def test_repeated_words_stay_separate():
    rows = [{"id": "1", "hash": "h", "text": "Замок замок"}]
    findings, _ = audit(rows, lambda t: "З+амок зам+ок", lambda t: "З+амок з+амок")
    ledger, summary = build_ledger(rows, findings)
    assert [x["status"] for x in ledger] == ["dual_agree", "dual_disagree"]
    assert ledger[0]["start"] != ledger[1]["start"]
    assert summary["pronunciation_verified"] == 0
