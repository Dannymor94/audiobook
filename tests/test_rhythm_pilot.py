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
