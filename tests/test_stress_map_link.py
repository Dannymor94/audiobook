import hashlib

import pytest

from audiobook.stress_map_link import link


def fixture():
    text = "Замок, замок."
    h = hashlib.sha256(text.encode()).hexdigest()
    rows = [dict(id="01_demo.norm:1", hash=h, text=text)]
    records = [dict(id=rows[0]["id"], hash=h, ordinal=i, start=start,
                    end=start + 5, word=word, stress_index=pos, status="auto",
                    risk_flags=["homograph"])
               for i, start, word, pos in ((1, 0, "Замок", 1), (2, 7, "замок", 3))]
    chunks = [dict(id="0001", n=1, hash="a", text="Замок,"),
              dict(id="0002", n=2, hash="b", text="замок.")]
    return rows, records, chunks


def test_repeated_words_bound_by_order_not_search():
    rows, records, chunks = fixture()
    queue, missing, report = link(rows, records, {"01_demo": chunks})
    assert not missing
    assert report["mapped_occurrences"] == report["mapped_chunks"] == 2
    assert [r["occurrences"][0]["stress_index"] for r in queue] == [1, 3]
    assert [r["occurrences"][0]["chunk_start"] for r in queue] == [0, 0]
    assert [r["chunk_hash"] for r in queue] == ["a", "b"]


def test_no_manifest_and_text_mismatch_fail_closed():
    rows, records, chunks = fixture()
    for manifests, reason in (({}, "no_manifest"),
                              ({"01_demo": [chunks[0], {**chunks[1], "text": "замок!"}]},
                               "section_text_mismatch")):
        queue, missing, report = link(rows, records, manifests)
        assert not queue
        assert report["unmapped_occurrences"] == 2
        assert {r["reason"] for r in missing} == {reason}


def test_missing_map_record_and_duplicate_chunk_rejected():
    rows, records, chunks = fixture()
    with pytest.raises(ValueError, match="INCOMPLETE_MAP"):
        link(rows, records[:1], {"01_demo": chunks})
    with pytest.raises(ValueError, match="DUPLICATE_CHUNK_ID"):
        link(rows, records, {"01_demo": [chunks[0], chunks[0]]})
