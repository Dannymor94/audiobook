import pytest

from audiobook.rhythm_pilot import build_trials


def fixture():
    rows = [{"id": f"{i:04d}", "hash": f"{i:040x}",
             "text": "Большие яблоки, сладкие груши.", "leadin": None}
            for i in range(1, 5)]
    offset = rows[0]["text"].index(",")
    gold = {"rows": [{"id": r["id"], "hash": r["hash"],
                      "split": "development" if i < 2 else "heldout",
                      "positive": [offset], "negative": [],
                      "independently_reviewed": True}
                     for i, r in enumerate(rows)]}
    targets = [{"chunk_id": r["id"], "offset": offset} for r in rows]
    return rows, gold, targets


def test_exact_four_pairs_and_fixed_seeds():
    rows, gold, targets = fixture()
    trials = build_trials(rows, gold, targets, {"model": {}}, {})
    assert len(trials) == 4
    assert all(r["baseline"].replace(",", ";", 1) == r["candidate"]
               for r in trials)


def test_requires_review_and_distinct_heldout():
    rows, gold, targets = fixture()
    gold["rows"][0]["independently_reviewed"] = False
    with pytest.raises(ValueError, match="INDEPENDENT_BOUNDARY"):
        build_trials(rows, gold, targets, {"model": {}}, {})
    rows, gold, targets = fixture()
    gold["rows"][2]["split"] = "development"
    with pytest.raises(ValueError, match="TWO_DEV_TWO_HELDOUT"):
        build_trials(rows, gold, targets, {"model": {}}, {})
    with pytest.raises(ValueError, match="FOUR_DISTINCT"):
        build_trials(rows, gold, targets[:3], {"model": {}}, {})


def freshness_fixture():
    from copy import deepcopy
    rows, _, targets = fixture()
    rows.append({"id": "0005", "hash": "e"*40, "text": "Other.", "leadin": None})
    for i, row in enumerate(rows, 1):
        row.update(n=i, open_end=False, cont=False)
    return rows, deepcopy(rows), targets


def test_non_target_staleness_recorded_without_mutation():
    from audiobook.rhythm_pilot import verify_pilot_freshness
    rows, fresh, targets = freshness_fixture()
    fresh[4]["hash"] = "f"*40
    result = verify_pilot_freshness(rows, fresh, targets)
    assert result == [{"id": "0005", "fields": ["hash"],
                       "frozen_hash": "e"*40, "fresh_hash": "f"*40}]
    assert rows[4]["hash"] == "e"*40


@pytest.mark.parametrize("field,value", [
    ("hash", "f"*40), ("leadin", "Changed carrier."),
    ("open_end", True), ("cont", True),
])
def test_selected_input_staleness_fails(field, value):
    from audiobook.rhythm_pilot import verify_pilot_freshness
    rows, fresh, targets = freshness_fixture()
    fresh[0][field] = value
    with pytest.raises(ValueError, match="PILOT_TARGET_STALE:0001"):
        verify_pilot_freshness(rows, fresh, targets)


def test_non_target_text_or_inventory_change_still_fails():
    from audiobook.rhythm_pilot import verify_pilot_freshness
    rows, fresh, targets = freshness_fixture()
    fresh[4]["text"] = "Different."
    with pytest.raises(ValueError, match="SOURCE_INVENTORY"):
        verify_pilot_freshness(rows, fresh, targets)
    rows, fresh, targets = freshness_fixture()
    with pytest.raises(ValueError, match="SOURCE_INVENTORY"):
        verify_pilot_freshness(rows, fresh[:-1], targets)
