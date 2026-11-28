import copy
import json

import pytest

from audiobook.silero_openvoice_score import POLICY, TITLE, score, verify_review
from audiobook.stress_pilot_review import sha


def fixture(tmp_path):
    source, review = tmp_path / "source", tmp_path / "review"
    source.mkdir()
    review.mkdir()
    trials, receipts, keys, items = [], [], [], []
    for n in range(1, 5):
        cid = f"{n:02d}"
        split = "heldout" if n >= 3 else "development"
        target = dict(vowel_ordinal=1 if n % 2 else 2, word="слово", split=split)
        t = dict(chunk_id=cid, chunk_hash=sha(cid.encode()), split=split,
                 status="planned", seed=42, carrier=None, target=target,
                 baseline_sha256=cid, candidate_sha256=cid)
        trials.append(t)
        raw = source / f"{cid}_silero_raw.wav"
        raw.write_bytes(f"raw {cid}".encode())
        for side, arm in zip("AB", ("candidate", "baseline")):
            name = f"ALG04B-{cid}_{side}.wav"
            wav = source / f"{cid}_{arm}.wav"
            payload = name.encode()
            wav.write_bytes(payload)
            (review / name).write_bytes(payload)
            d = sha(payload)
            keys.append(dict(file=name, chunk_id=cid, arm=arm, wav_sha256=d, target=target))
            receipts.append(dict(chunk_id=cid, arm=arm, wav=wav.name, status="generated",
                                 seed=42, carrier=None, input_sha256=cid, generation={},
                                 wav_sha256=d, source_wav_sha256=sha(raw.read_bytes())))
            items.append(dict(file=name, chunk=cid, hash=t["chunk_hash"], label="ok",
                              heard_stress=str(target["vowel_ordinal"]), lexical="yes",
                              voice="yes", rhythm="ok",
                              meta=dict(chunk=cid, hash=t["chunk_hash"], wav_sha256=d,
                                        pair=str(n), side=side)))
    plan = json.dumps(dict(policy=POLICY, inventory={}, trials=trials)).encode()
    (source / "plan_PRIVATE.json").write_bytes(plan)
    log = "\n".join(json.dumps(dict(r, plan_sha256=sha(plan))) for r in receipts).encode()
    (source / "receipts_PRIVATE.jsonl").write_bytes(log)
    (source / "READY_PRIVATE.json").write_text(json.dumps(dict(
        pairs=4, plan_sha256=sha(plan), receipts_sha256=sha(log))), encoding="utf-8")
    pid = sha(json.dumps(keys, sort_keys=True).encode())[:16]
    return source, review, dict(page_id=pid, plan_sha256=sha(plan), items=keys), dict(
        title=TITLE, kind="golden", page_id=pid, items=items)


def test_verified_diagnostic_pass(tmp_path):
    rows = verify_review(*fixture(tmp_path))
    result = score(rows)
    assert result["verdict"] == "DIAGNOSTIC_PASS"
    assert result["counts"]["heldout"]["candidate"]["stress_correct"] == 2
    assert result["production_authorized"] is False


@pytest.mark.parametrize("field,value", [
    ("heard_stress", "2"), ("heard_stress", "unclear"), ("lexical", "no"),
    ("voice", "no"), ("rhythm", "bad"), ("label", "bad")])
def test_heldout_failure(tmp_path, field, value):
    rows = verify_review(*fixture(tmp_path))
    row = next(r for r in rows if r["chunk_id"] == "03" and r["arm"] == "candidate")
    row["ratings"][field] = value
    assert score(rows)["verdict"] == "NOT_PASSED"


def test_incomplete_development_is_not_pass(tmp_path):
    rows = verify_review(*fixture(tmp_path))
    rows[0]["ratings"]["heard_stress"] = ""
    assert score(rows)["verdict"] == "INCOMPLETE"


def test_label_page_and_audio_identity(tmp_path):
    source, review, key, labels = fixture(tmp_path)
    bad = copy.deepcopy(labels)
    bad["items"][0]["meta"]["wav_sha256"] = "bad"
    with pytest.raises(ValueError, match="REVIEW_IDENTITY_MISMATCH"):
        verify_review(source, review, key, bad)
    bad = copy.deepcopy(labels)
    bad["page_id"] = "wrong"
    with pytest.raises(ValueError, match="BLIND_PAGE_MISMATCH"):
        verify_review(source, review, key, bad)
    (review / "ALG04B-01_A.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="AUDIO_DIGEST_MISMATCH"):
        verify_review(source, review, key, labels)
