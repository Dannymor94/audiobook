import pytest

from audiobook.rhythm_actuator import plan


def fixture(text="Большие яблоки, сладкие груши."):
    row = {"id": "0001", "hash": "a"*40, "text": text,
           "leadin": None, "seed_override": 42}
    offset = text.index(",")
    annotation = {"id": row["id"], "hash": row["hash"],
                  "split": "development", "positive": [offset], "negative": []}
    return row, annotation, offset


def test_single_stream_exact_edit():
    row, annotation, offset = fixture()
    r = plan(row, annotation, offset, {"model": {}}, {})
    assert r["status"] == "planned"
    assert r["baseline"] == row["text"]
    assert r["candidate"] == row["text"][:offset] + ";" + row["text"][offset+1:]
    assert r["seed"] == 42
    assert r["baseline_sha256"] != r["candidate_sha256"]


def test_same_carrier_and_source_comma_ordinal():
    row, annotation, offset = fixture()
    row["leadin"] = "Вот, начало."
    r = plan(row, annotation, offset, {"model": {}}, {})
    assert r["status"] == "planned"
    assert r["baseline"].startswith("Вот, начало.")
    assert r["candidate"].startswith("Вот, начало.")
    assert r["prepared_offset"] > offset


@pytest.mark.parametrize("text", ['«Яблоки, груши».', "Число 3,14."])
def test_protected_boundary(text):
    row, annotation, offset = fixture(text)
    with pytest.raises(ValueError, match="UNSAFE_BOUNDARY"):
        plan(row, annotation, offset, {"model": {}}, {})


def test_stale_annotation_and_locked():
    row, annotation, offset = fixture()
    annotation["hash"] = "wrong"
    with pytest.raises(ValueError, match="BOUNDARY_IDENTITY"):
        plan(row, annotation, offset, {"model": {}}, {})
    row["locked"] = True
    assert plan(row, annotation, offset, {"model": {}}, {}) == {"status": "locked"}


def test_legacy_enum_is_not_used():
    row, annotation, offset = fixture()
    with pytest.raises(ValueError, match="LEGACY_ENUM"):
        plan(row, annotation, offset,
             {"model": {}, "pauses_ms": {"enum_pause_ms": 250}}, {})
