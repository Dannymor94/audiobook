import pytest

from audiobook.stress_ctc_calibration import prepare, calibrate, frozen


def controls_fixture():
    rows, findings, controls, pronunciations = [], [], [], []
    # Synthetic identity fixtures, not independently established phonetic gold.
    for i, word in enumerate(("мама", "рама", "каша", "дача", "сила", "липа",
                              "вода", "гора", "река", "луна", "рука", "нога")):
        cid = str(i+1).zfill(4)
        split = "development" if i < 6 else "heldout"
        correct = i % 2 == 0
        row = dict(id=cid, text=word, hash=f"hash-{cid}", status="done")
        finding = dict(id=cid, hash=row["hash"], ordinal=1,
                       start=0, end=len(word), word=word, status="agree")
        control = dict(finding, split=split, independently_reviewed=True,
                       expected_index=1, heard_ordinal=1 if correct else 2,
                       gold="correct" if correct else "wrong_stress",
                       wav_sha256=f"{i+1:064x}")
        p = dict(id=cid, ordinal=1, hash=row["hash"], word=word,
                 independently_reviewed=True, phones={"1":["m","a","m","ə"],
                                                         "2":["m","ə","m","a"]},
                 vowel_positions=[1,3])
        rows.append(row)
        findings.append(finding)
        controls.append(control)
        pronunciations.append(p)
    return rows, findings, controls, pronunciations


def test_preparation_frozen_occurrences():
    data = controls_fixture()
    result = prepare(*data, {"<pad>":0,"m":1,"a":2,"ə":3}, 0)
    assert len(result) == 12
    assert result[0]["expected_ordinal"] == 1
    assert result[0]["hypotheses"] == {1:[1,2,1,3],2:[1,3,1,2]}


def test_missing_phone_is_uncertainty_not_substitution():
    data = controls_fixture()
    result = prepare(*data, {"<pad>":0,"m":1,"a":2}, 0)
    assert all(r["hypotheses"] is None for r in result)


def test_control_leakage_and_gold():
    data = controls_fixture()
    data[2][6]["wav_sha256"] = data[2][0]["wav_sha256"]
    with pytest.raises(ValueError, match="SPLIT_LEAKAGE"):
        prepare(*data, {"<pad>":0}, 0)
    data = controls_fixture()
    data[2][1]["heard_ordinal"] = 1
    with pytest.raises(ValueError, match="HEARD_ORDINAL"):
        prepare(*data, {"<pad>":0}, 0)


def test_insufficient_gold():
    rows, findings, controls, pronunciations = controls_fixture()
    with pytest.raises(ValueError, match="INSUFFICIENT_GOLD"):
        prepare(rows, findings, controls[:-1], pronunciations[:-1], {"<pad>":0}, 0)


def test_calibration_ignores_heldout_and_abstains():
    def row(split, gold, best):
        return dict(split=split, gold=gold, expected_ordinal=1,
                    evidence=dict(status="ranked", best_ordinal=best,
                                  scores={1:-4,2:-4}, margin_per_frame=.2,
                                  fit_per_frame=-2))
    dev = [row("development","correct",1),row("development","wrong_stress",2)]
    first = calibrate(dev+[row("heldout","correct",2)])
    assert first == dict(min_margin=.2,min_fit=-2.)
    assert calibrate(dev+[row("heldout","wrong_stress",1)]) == first
    assert calibrate([row("development","correct",2),row("development","wrong_stress",2)]) is None


def test_frozen_hash(tmp_path):
    import hashlib
    p = tmp_path / "evidence.json"
    p.write_bytes(b"hello")
    assert frozen(p, hashlib.sha256(b"hello").hexdigest()) == b"hello"
    with pytest.raises(ValueError, match="FROZEN_FILE_MISMATCH"):
        frozen(p, "0"*64)
