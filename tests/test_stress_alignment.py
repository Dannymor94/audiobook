from audiobook.stress_consensus import align, align_detailed, audit, compare


def test_horizontal_format_only_recovers_exact_occurrences():
    source = "Замок,   замок. Молоко!"
    output = "З+амок , зам+ок.\tМолок+о! "
    assert align_detailed(source, output, strict=True)[0] is None
    mapping, reason = align_detailed(source, output)
    assert reason == "format_only"
    assert mapping == [("Замок", 1), ("замок", 3), ("Молоко", 5)]
    assert [r["status"] for r in compare(source, output, output)] == ["agree"] * 3


def test_not_a_fuzzy_alignment():
    for source, output in [
        ("Замок, тут.", "Зам+ок тут."),
        ("Замок, тут.", "Зам+ок; тут."),
        ("Замок-замок", "Зам+ок - зам+ок"),
        ("Замок 5 тут", "Зам+ок 6 тут"),
        ("Замок A тут", "Зам+ок A  тут"),
        ("Замок\nтут", "Зам+ок тут"),
        ("Замок замок", "Зам+ок"),
        ("Замок молоко", "Молок+о зам+ок"),
        ("Берёза", "Бер+еза"),
    ]:
        assert align(source, output) is None, (source, output)


def test_diagnostics_and_baseline_same_predictor_calls():
    rows = [{"id": "a", "hash": "h", "text": "Замок, замок."},
            {"id": "b", "hash": "i", "text": "Молоко."}]
    calls = []
    diagnostics = []

    def primary(t):
        calls.append("a")
        return "З+амок , зам+ок." if "Замок" in t else "Молок+о."

    def secondary(t):
        calls.append("b")
        return "З+амок, з+амок." if "Замок" in t else "Соб+ака."

    records, summary = audit(rows, primary, secondary, row_diagnostics=diagnostics)
    assert calls == ["a", "b", "a", "b"]
    assert [r["status"] for r in records] == ["agree", "disagree", "alignment_error"]
    assert summary["strict_baseline_alignment_error_occurrences"] == 3
    assert summary["format_recovered_occurrences"] == 2
    assert summary["alignment_reasons_by_row"] == {
        "ruaccent:exact": 1, "ruaccent:format_only": 1,
        "silero:exact": 1, "silero:word_changed": 1}
    assert diagnostics[0]["ruaccent_output"] == "З+амок , зам+ок."
    assert diagnostics[0]["hash"] == "h"
    assert summary["acoustic_checked"] == 0
