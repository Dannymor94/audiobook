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


def test_marked_trial_input_preserves_source_and_occurrence_order():
    from audiobook.stress_consensus import candidate_input
    text = "Замок, замок! Береза."
    findings = compare(text, "З+амок, зам+ок! Бер+ёза.", "За\u0301мок, за\u0301мок! Бер+ёза.")
    assert candidate_input(text, findings) == "За\u0301мок, замок! Берёза."


def test_reject_conflicting_yo_or_dropped_occurrence():
    import pytest
    from audiobook.stress_consensus import candidate_input
    assert parse_marked("б+ерёза")[1] is None
    assert align("берёза", "бер+еза") is None
    with pytest.raises(ValueError, match="INCOMPLETE_OCCURRENCE_ACCOUNTING"):
        candidate_input("Молоко", [])
    with pytest.raises(ValueError, match="PREMARKED_OR_NONPLAIN_SOURCE"):
        candidate_input("Молоко\u0301", [])


def test_book_inventory_uses_normalized_lines_only(tmp_path):
    from audiobook.stress_consensus import book_rows
    (tmp_path / "01_fixture.norm.txt").write_text("Замок.\n\nБереза.\n", encoding="utf-8")
    (tmp_path / "02_fixture.norm.txt").write_text("Молоко.\n", encoding="utf-8")
    (tmp_path / "01_fixture.acc.txt").write_text("Ложная разметка.", encoding="utf-8")
    rows, hashes = book_rows(tmp_path)
    assert [r["id"] for r in rows] == ["01_fixture.norm:1", "01_fixture.norm:3", "02_fixture.norm:1"]
    assert [r["text"] for r in rows] == ["Замок.", "Береза.", "Молоко."]
    assert len(hashes) == 2
