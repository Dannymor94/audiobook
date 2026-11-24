import hashlib
import json

import pytest

from audiobook.stress_control_baseline import trial_plan
from audiobook.stress_control_review import evaluate, make_key, public_rows, read_run


def fixture_run(path, failed=()):
    plan = trial_plan(77)
    takes = []
    for r in plan:
        if r["id"] in failed:
            takes.append(dict(id=r["id"], status="failed"))
            continue
        data = r["id"].encode()
        (path / (r["id"] + ".wav")).write_bytes(data)
        takes.append(dict(id=r["id"], status="generated",
                          sha256=hashlib.sha256(data).hexdigest(),
                          seconds=3.0, elapsed_seconds=24.0, rtf=8.0))
    (path / "plan_PRIVATE.json").write_text(json.dumps(plan))
    (path / "takes_PRIVATE.jsonl").write_text("\n".join(map(json.dumps, takes)))
    (path / "summary.json").write_text(json.dumps(dict(planned=16,
        generated=16-len(failed), failed=len(failed), release_ready=False)))
    (path / "provenance_PRIVATE.json").write_text(json.dumps(dict(
        snapshot_sha256={"model": "fixture"}, reference_sha256="fixture")))


def test_complete_run_and_blind_scores(tmp_path):
    fixture_run(tmp_path)
    records, audio, digest = read_run(tmp_path)
    key = make_key(records, 1)
    assert len(audio) == 16 and len(digest) == 64
    assert key == make_key(records, 1)
    rows = public_rows(key)
    assert all("condition" not in r and "\u0301" not in r["sentence"] for r in rows)
    for r, k in zip(rows, key):
        from audiobook.stress_consensus import VOWELS
        expected = sum(c.lower() in VOWELS for c in k["expected_word"][:k["expected_index"] + 1])
        alternative = 2 if expected == 1 else 1
        r.update(lexical="ok", heard_vowel=str(expected if k["condition"] == "acute" else alternative),
                 naturalness="good")
    result = evaluate(records, key, rows)
    assert result["outcomes"] == {"plain": {"wrong_stress": 8}, "acute": {"correct": 8}}
    assert result["paired_changes"] == {"improved": 8}
    assert not result["release_ready"]
    with pytest.raises(ValueError, match="MISSING_RATINGS"):
        evaluate(records, key, rows[:-1])
    with pytest.raises(ValueError, match="RATING_IDENTITY"):
        evaluate(records, key, rows + rows[:1])


def test_uncertain_lexical_and_generation_failures_count(tmp_path):
    fixture_run(tmp_path, failed=("001",))
    records, _, _ = read_run(tmp_path)
    key = make_key(records, 2)
    rows = public_rows(key)
    for r in rows:
        r.update(lexical="uncertain", heard_vowel="unknown", naturalness="uncertain")
    rows[0]["lexical"] = "error"
    s = evaluate(records, key, rows)
    assert s["rated"] == 15
    assert sum(v.get("generation_failed", 0) for v in s["outcomes"].values()) == 1
    assert sum(v.get("lexical_error", 0) for v in s["outcomes"].values()) == 1
    assert s["paired_changes"] == {"not_comparable": 8}
    rows[0]["heard_vowel"] = "1"
    with pytest.raises(ValueError, match="STRESS_LABEL_WITH_LEXICAL_ERROR"):
        evaluate(records, key, rows)


def test_modified_wav_and_unfinished_run_rejected(tmp_path):
    fixture_run(tmp_path)
    (tmp_path / "001.wav").write_bytes(b"bad")
    with pytest.raises(ValueError, match="WAV_DIGEST_MISMATCH"):
        read_run(tmp_path)
    fixture_run(tmp_path)
    p = tmp_path / "takes_PRIVATE.jsonl"
    p.write_text("\n".join(p.read_text().splitlines()[:-1]))
    with pytest.raises(ValueError, match="INCOMPLETE_OR_REORDERED_TAKES"):
        read_run(tmp_path)


def test_voicy_comparison_reuses_only_stock_plain(tmp_path):
    from audiobook.stress_control_review import read_voicy_comparison
    from audiobook.stress_voicy import ADAPTER_PIN, ADAPTER_SHA256, BASE_PIN

    stock = tmp_path / "stock"
    stock.mkdir()
    fixture_run(stock)
    old, _, digest = read_run(stock)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    plan = [r for r in trial_plan(77) if r["condition"] == "acute"]
    takes = []
    for r in plan:
        data = ("adapted-" + r["id"]).encode()
        (candidate / (r["id"] + ".wav")).write_bytes(data)
        takes.append(dict(id=r["id"], status="generated",
                          sha256=hashlib.sha256(data).hexdigest(),
                          seconds=3.0, elapsed_seconds=24.0, rtf=8.0))
    (candidate / "plan_PRIVATE.json").write_text(json.dumps(plan))
    (candidate / "takes_PRIVATE.jsonl").write_text("\n".join(map(json.dumps, takes)))
    (candidate / "summary.json").write_text(json.dumps(dict(
        planned=8, generated=8, failed=0, release_ready=False)))
    p = candidate / "provenance_PRIVATE.json"
    provenance = json.loads((stock / p.name).read_text())
    provenance.update(baseline_run_digest=digest, variant="voicy_v3",
                      adapter_revision=ADAPTER_PIN, adapter_sha256=ADAPTER_SHA256,
                      base_revision=BASE_PIN, matrices=196, checkpoint_written=False)
    p.write_text(json.dumps(provenance))
    records, audio, _ = read_voicy_comparison(stock, candidate)
    assert len(records) == len(audio) == 16
    assert {r["id"] for r in records if r["condition"] == "plain"} == {
        r["id"] for r in old if r["condition"] == "plain"}
    assert all(audio[r["id"]].startswith(b"adapted-") for r in plan)
    p.write_text(json.dumps(dict(provenance, baseline_run_digest="wrong")))
    with pytest.raises(ValueError, match="COMPARISON_PROVENANCE_MISMATCH"):
        read_voicy_comparison(stock, candidate)
