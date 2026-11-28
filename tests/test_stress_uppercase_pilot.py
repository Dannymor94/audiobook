from audiobook.stress_uppercase_pilot import candidate


def occurrence(start=0, word="молоко", stress=5, status="auto"):
    return dict(chunk_start=start, chunk_end=start+len(word), word=word,
                stress_index=stress, status=status)


def test_changes_only_selected_repeated_word_not_carrier():
    raw = "молоко и молоко."
    result = candidate(raw, raw, "молоко. " + raw, occurrence(start=9))
    assert result["status"] == "planned"
    assert result["candidate"] == "молоко. молоко и молокО."
    assert result["baseline"] == "молоко. молоко и молоко."


def test_fail_closed_if_preparation_changed_words():
    raw = "молоко и молоко."
    assert candidate(raw, "молокО и молоко.", "молокО и молоко.",
                     occurrence())["status"] == "prepared_alignment_unproven"


def test_known_negative_and_unresolved_never_transformed():
    assert candidate("тебя", "тебя", "тебя", occurrence(word="тебя", stress=3))[
        "status"] == "historical_negative_form"
    assert candidate("молоко", "молоко", "молоко", occurrence(stress=None,
                     status="unresolved"))["status"] == "unresolved_stress"


def test_punctuation_only_preparation_supported():
    raw = "«молоко»"
    result = candidate(raw, "молоко.", "Смотри. молоко.", occurrence(start=1))
    assert result["candidate"] == "Смотри. молокО."
