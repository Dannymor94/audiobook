from audiobook.stress_consensus import align, audit, compare, parse_marked


def test_marks_and_yo():
    assert parse_marked("молок+о") == ("молоко", 5)
    assert parse_marked("молоко\u0301") == ("молоко", 5)
    assert parse_marked("ребёнок") == ("ребёнок", 3)
    assert parse_marked("м+олок+о")[1] is None
    assert parse_marked("молок+")[1] is None


def test_context_occurrences_not_word_types():
    rows = compare("Замок, замок.", "З+амок, зам+ок.", "За\u0301мок, за\u0301мок.")
    assert [r["status"] for r in rows] == ["agree", "disagree"]
    assert [r["ordinal"] for r in rows] == [1, 2]
    assert rows[1]["start"] == 7


def test_alignment_and_no_guessed_stress():
    assert align("Замок, тут.", "Зам+ок тут.") is None
    assert compare("замок", "зам+ок", "дом")[0]["status"] == "alignment_error"
    assert compare("замок", "зам+ок", "замок")[0]["status"] == "single_source"
    assert compare("замок", "замок", "замок")[0]["status"] == "unresolved"
    assert compare("веселый", "весёлый", "вес+елый")[0]["status"] == "disagree"


def test_accounting_all_multisyllabic_occurrences():
    rows = [{"id": "0001", "hash": "a", "text": "Замок и замок."}]
    records, summary = audit(rows, lambda t: "З+амок и зам+ок.", lambda t: "З+амок и замок.")
    assert len(records) == summary["occurrences"] == 2
    assert summary["not_agreed"] == 1
    assert summary["agreement_fraction"] == 0.5
    assert summary["acoustic_checked"] == 0
