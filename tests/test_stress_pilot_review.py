import json

import pytest

from audiobook.stress_pilot_review import build, sha


def make_run(folder):
    import numpy as np
    import soundfile as sf

    folder.mkdir()
    trial = dict(status="planned", chunk_id="0001", chunk_hash="hash",
                 seed=42, carrier=None, target={"split": "heldout"},
                 baseline_sha256="b", candidate_sha256="c")
    plan = json.dumps(dict(policy="uppercase-occurrence-pilot-v1",
                           trials=[trial])).encode("utf-8")
    (folder / "plan_PRIVATE.json").write_bytes(plan)
    receipts = []
    for arm, value in (("baseline", 0.1), ("candidate", 0.2)):
        name = f"0001_{arm}.wav"
        path = folder / name
        sf.write(str(path), np.full(240, value, dtype=np.float32), 24000,
                 subtype="FLOAT")
        receipts.append(dict(chunk_id="0001", arm=arm, status="generated",
                             plan_sha256=sha(plan), wav=name,
                             wav_sha256=sha(path.read_bytes()),
                             input_sha256=trial[arm+"_sha256"], seed=42,
                             carrier=None, generation={"model": "fixture"},
                             samples=240))
    (folder / "receipts_PRIVATE.jsonl").write_text(
        "\n".join(json.dumps(r) for r in receipts), encoding="utf-8")
    return receipts


def test_verified_blind_review(tmp_path):
    source = tmp_path / "run"
    receipts = make_run(source)
    out = tmp_path / "review"
    key = tmp_path / "key.json"
    page = build(source, out, key, expected_pairs=1)
    html = page.read_text(encoding="utf-8")
    assert '<meta charset="utf-8">' in html
    assert html.count("<audio controls") == 2
    assert "Пара 1" in html
    assert "0001_baseline.wav" not in html
    assert "0001_candidate.wav" not in html
    data = json.loads(key.read_text(encoding="utf-8"))
    assert {r["arm"] for r in data["items"]} == {"baseline", "candidate"}
    assert {sha(w.read_bytes()) for w in out.glob("*.wav")} == {
        r["wav_sha256"] for r in receipts}
    assert not (out / key.name).exists()
    with pytest.raises(ValueError, match="NEW_REVIEW"):
        build(source, out, key, expected_pairs=1)


def test_wrong_source_or_audio_fails_before_review(tmp_path):
    source = tmp_path / "run"
    make_run(source)
    out = tmp_path / "review"
    key = tmp_path / "key.json"
    with pytest.raises(ValueError, match="WRONG_PAIR_INVENTORY"):
        build(source, out, key)
    (source / "0001_baseline.wav").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="WAV_DIGEST_MISMATCH"):
        build(source, out, key, expected_pairs=1)
    assert not out.exists()


def test_rhythm_requires_ready(tmp_path):
    source = tmp_path / "run"
    make_run(source)
    plan_path = source / "plan_PRIVATE.json"
    plan = json.loads(plan_path.read_bytes())
    plan["policy"] = "single-stream-comma-semicolon-v1"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        build(source, tmp_path / "review", tmp_path / "key.json", 4,
              policy="single-stream-comma-semicolon-v1")


def test_pocket_verified_four_pair_review(tmp_path):
    import shutil

    source = tmp_path / "run"
    records = make_run(source)
    base = json.loads((source / "plan_PRIVATE.json").read_bytes())["trials"][0]
    trials = []
    receipts = []
    for i in range(1, 5):
        cid = f"{i:02d}"
        trials.append(dict(base, chunk_id=cid))
        for r in records:
            name = f"{cid}_{r['arm']}.wav"
            shutil.copyfile(source / r["wav"], source / name)
            receipts.append(dict(r, chunk_id=cid, wav=name))
    plan = json.dumps({"policy": "pocket-ipa-control-v1", "trials": trials}).encode()
    (source / "plan_PRIVATE.json").write_bytes(plan)
    log = source / "receipts_PRIVATE.jsonl"
    log.write_text("\n".join(json.dumps(dict(r, plan_sha256=sha(plan)))
                             for r in receipts), encoding="utf-8")
    (source / "READY_PRIVATE.json").write_text(json.dumps({
        "pairs": 4, "plan_sha256": sha(plan),
        "receipts_sha256": sha(log.read_bytes())}), encoding="utf-8")
    page = build(source, tmp_path / "review", tmp_path / "key.json", 4,
                 policy="pocket-ipa-control-v1")
    html = page.read_text(encoding="utf-8")
    assert html.count("<audio controls") == 8
    assert "ALG-04" in html
    assert len(list(page.parent.glob("ALG04-*.wav"))) == 8


def test_transfer_review_explicit_ratings(tmp_path):
    import shutil

    source = tmp_path / "run"
    records = make_run(source)
    base = json.loads((source / "plan_PRIVATE.json").read_bytes())["trials"][0]
    trials, receipts = [], []
    for i in range(1, 5):
        cid = f"{i:02d}"
        trials.append(dict(base, chunk_id=cid, text="З+амок.",
                           target={"word": "замок", "vowel_ordinal": 1}))
        raw = source / f"{cid}_silero_raw.wav"
        shutil.copyfile(source / records[0]["wav"], raw)
        for r in records:
            name = f"{cid}_{r['arm']}.wav"
            shutil.copyfile(source / r["wav"], source / name)
            receipts.append(dict(r, chunk_id=cid, wav=name,
                                 source_wav_sha256=sha(raw.read_bytes())))
    plan = json.dumps({"policy": "silero-openvoice-control-v1", "trials": trials}).encode()
    (source / "plan_PRIVATE.json").write_bytes(plan)
    log = source / "receipts_PRIVATE.jsonl"
    log.write_text("\n".join(json.dumps(dict(r, plan_sha256=sha(plan)))
                             for r in receipts), encoding="utf-8")
    (source / "READY_PRIVATE.json").write_text(json.dumps({
        "pairs": 4, "plan_sha256": sha(plan),
        "receipts_sha256": sha(log.read_bytes())}), encoding="utf-8")
    page = build(source, tmp_path / "review", tmp_path / "key.json", 4,
                 policy="silero-openvoice-control-v1")
    html = page.read_text(encoding="utf-8")
    assert html.count("<audio controls") == 8
    for field in ("heard_stress", "lexical", "voice", "rhythm"):
        assert html.count(f'data-rating="{field}"') == 8
    assert "З+амок" not in html
    assert "Замок" in html
    raw.write_bytes(b"changed")
    with pytest.raises(ValueError, match="TRANSFER_SOURCE_MISMATCH"):
        build(source, tmp_path / "second", tmp_path / "second-key.json", 4,
              policy="silero-openvoice-control-v1")
