import hashlib
import json

import pytest

from audiobook.rhythm_eval import evaluate


def fixture():
    rows = [{"id": "1", "hash": "h1", "text": "А, Б, В, Г."},
            {"id": "2", "hash": "h2", "text": "Д, Е."}]
    data = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode()
    sha = hashlib.sha256(data).hexdigest()
    pred = {"manifest_sha256": sha, "rows": [
        {"id": "1", "hash": "h1", "status": "parsed", "candidate_offsets": [1, 4, 7]},
        {"id": "2", "hash": "h2", "status": "unresolved"}]}
    gold = {"manifest_sha256": sha, "rows": [
        {"id": "1", "hash": "h1", "split": "development",
         "positive": [1], "negative": [4]},
        {"id": "2", "hash": "h2", "split": "heldout",
         "positive": [1], "negative": []}]}
    return data, pred, gold


def test_partial_labels_and_unresolved_misses():
    data, pred, gold = fixture()
    out = evaluate(data, pred, gold)["splits"]
    assert out["development"]["tp"] == 1
    assert out["development"]["fp"] == 1
    assert out["development"]["unknown_proposals"] == 1
    assert out["development"]["precision_on_labeled_proposals"] == 0.5
    assert out["heldout"]["fn"] == 1
    assert out["heldout"]["unresolved"] == 1
    assert out["heldout"]["precision_on_labeled_proposals"] is None
    assert out["heldout"]["recall_on_known_positive"] == 0


def test_identity_and_offset_fail_closed():
    data, pred, gold = fixture()
    pred["rows"][0]["hash"] = "wrong"
    with pytest.raises(ValueError, match="IDENTITY"):
        evaluate(data, pred, gold)
    data, pred, gold = fixture()
    gold["rows"][0]["positive"] = [0]
    with pytest.raises(ValueError, match="INVALID_COMMA"):
        evaluate(data, pred, gold)


def test_conflicting_labels_rejected():
    data, pred, gold = fixture()
    gold["rows"][0]["negative"] = [1]
    with pytest.raises(ValueError, match="GOLD_CONFLICT"):
        evaluate(data, pred, gold)
