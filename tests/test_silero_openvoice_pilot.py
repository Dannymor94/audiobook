import json

import numpy as np
import pytest

from audiobook import silero_openvoice_provision as provision
from audiobook.silero_openvoice_pilot import CASES, make_plan, resample, valid_audio, validate_cases
from audiobook.pocket_preflight import sha


def test_contextual_stress_cases():
    validate_cases()
    plan = make_plan({}, "reference", {})
    assert len(plan["trials"]) == len(CASES) == 4
    assert [t["target"]["vowel_ordinal"] for t in plan["trials"]] == [1, 2, 2, 1]
    assert all(t["baseline_sha256"] == t["candidate_sha256"] for t in plan["trials"])


@pytest.mark.parametrize("text,ordinal,error", [
    ("На холме сто+ял з+амок.", 1, "MISSING_MULTISYLLABLE"),
    ("На холм+е сто+ял зам+ок.", 1, "TARGET_ORDINAL"),
    ("На холм+е сто+ял +замок.", 1, "INVALID_STRESS"),
])
def test_bad_marked_text(text, ordinal, error):
    with pytest.raises(ValueError, match=error):
        validate_cases([("01", "development", text, "замок", ordinal)])


def test_audio_validation_and_matched_rate():
    wave = np.ones(24000, dtype=np.float32)*.1
    low = resample(wave, 24000, 22050)
    assert len(low) == 22050
    assert len(valid_audio(resample(low, 22050, 24000), 24000)) == 24000
    with pytest.raises(ValueError, match="INVALID_AUDIO"):
        valid_audio(np.zeros(24000), 24000)


def test_inventory_rejects_modified_file(tmp_path, monkeypatch):
    (tmp_path/"silero.pt").write_bytes(b"fixture")
    (tmp_path/"checkpoint.pth").write_bytes(b"fixture checkpoint")
    (tmp_path/"config.json").write_text(json.dumps({
        "_version_": "v2", "data": {"sampling_rate": 22050, "n_speakers": 0},
        "model": {"zero_g": True}}))
    files = {n: sha(tmp_path/n) for n in provision.NAMES}
    monkeypatch.setattr(provision, "OV_SHA", files["checkpoint.pth"])
    monkeypatch.setattr(provision, "SILERO_SHA", files["silero.pt"])
    monkeypatch.setattr(provision, "OV_CONFIG_SHA", files["config.json"])
    evidence = dict(provision.OV_LICENSE_EVIDENCE, api_license=None,
                    method="reviewed-exact-release")
    inv = dict(silero_url=provision.SILERO_URL, openvoice_revision=provision.OV_REV,
               openvoice_source=provision.OV_SOURCE, silero_source=provision.SILERO_SOURCE,
               files=files, license_evidence=evidence)
    assert provision.verify_inventory(tmp_path, inv) == inv
    changed = dict(inv, files=dict(files, **{"silero.pt": "b"*64}))
    with pytest.raises(ValueError, match="WRONG_ASSET_INVENTORY"):
        provision.verify_inventory(tmp_path, changed)
    (tmp_path/"silero.pt").write_bytes(b"different")
    with pytest.raises(ValueError, match="ASSET_DIGEST_MISMATCH"):
        provision.verify_inventory(tmp_path, inv)


def test_converter_license_evidence():
    from types import SimpleNamespace
    sibling = SimpleNamespace(rfilename="converter/checkpoint.pth",
                              lfs=SimpleNamespace(sha256=provision.OV_SHA))
    info = SimpleNamespace(id=provision.OV_REPO, sha=provision.OV_REV,
                           card_data=None, siblings=[sibling])
    ev = provision.converter_license_evidence(info)
    assert ev["method"] == "reviewed-exact-release"
    assert ev["api_license"] is None
    info.card_data = {"license": "mit"}
    assert provision.converter_license_evidence(info)["method"] == "api+reviewed-release"
    info.card_data = {"license": "cc-by-nc-4.0"}
    with pytest.raises(ValueError, match="LICENSE_CONFLICT"):
        provision.converter_license_evidence(info)
    info.card_data = None
    info.sha = "b"*40
    with pytest.raises(ValueError, match="REVISION_MISMATCH"):
        provision.converter_license_evidence(info)
    info.sha = provision.OV_REV
    sibling.lfs.sha256 = "b"*64
    with pytest.raises(ValueError, match="WEIGHT_DIGEST_MISMATCH"):
        provision.converter_license_evidence(info)
