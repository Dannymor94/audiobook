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
