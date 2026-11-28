import hashlib
import json

import numpy as np
import pytest

from audiobook.voice_similarity import POLICY, cosine, unit, reference_profile, compare_embedding, prepare


def vector(i):
    x=np.zeros(256)
    x[i]=1.
    return x


def test_cosine_scale_and_bounds():
    a,b=vector(0),vector(1)
    assert cosine(a,100*a)==pytest.approx(1)
    assert cosine(a,b)==pytest.approx(0)
    assert cosine(a,-a)==pytest.approx(-1)


@pytest.mark.parametrize("bad",[np.zeros(256),np.ones(255),np.full(256,np.nan)])
def test_bad_embeddings_reject(bad):
    with pytest.raises(ValueError):
        unit(bad)


def test_reference_profile_leave_one_out_and_outlier():
    a,b=vector(0),vector(1)
    refs=[a,a+.1*b,a-.1*b]
    centroid,profile=reference_profile(refs)
    assert profile["count"]==3
    assert 0<profile["loo_min"]<1
    assert compare_embedding(a,centroid,profile)["cosine"]==pytest.approx(1)
    assert compare_embedding(b,centroid,profile)["below_observed_reference_range"] is True
    assert compare_embedding(a,centroid,profile)["diagnostic_only"] is True
    with pytest.raises(ValueError,match="THREE_TO_TWELVE"):
        reference_profile(refs[:2])


def fixture(root):
    manifest=json.dumps(dict(id="01",hash="h",text="Мама.",status="done")).encode()
    refs=[]
    for i in range(3):
        data=f"reference {i}".encode()
        name=f"ref{i}.wav"
        (root/name).write_bytes(data)
        refs.append(dict(wav=name,wav_sha256=hashlib.sha256(data).hexdigest(),
                         author_recording=True,independent_of_synthesis_reference=True,
                         clean_single_speaker_reviewed=True))
    data=b"candidate"
    (root/"candidate.wav").write_bytes(data)
    candidate=dict(id="01",hash="h",wav="candidate.wav",wav_sha256=hashlib.sha256(data).hexdigest())
    plan=dict(policy=POLICY,manifest_sha256=hashlib.sha256(manifest).hexdigest(),
              references=refs,candidates=[candidate])
    return manifest,plan


def test_frozen_inventory(tmp_path):
    m,p=fixture(tmp_path)
    refs,candidates,snapshots=prepare(m,p,tmp_path)
    assert len(refs)==3 and len(candidates)==1 and len(snapshots)==4
    (tmp_path/"candidate.wav").write_bytes(b"changed")
    with pytest.raises(ValueError,match="DIGEST_MISMATCH"):
        prepare(m,p,tmp_path)


def test_reused_synthesis_reference_not_accepted(tmp_path):
    m,p=fixture(tmp_path)
    p["references"][0]["independent_of_synthesis_reference"]=False
    with pytest.raises(ValueError,match="INDEPENDENT_REFERENCE"):
        prepare(m,p,tmp_path)


def test_duplicate_wav_not_accepted(tmp_path):
    m,p=fixture(tmp_path)
    p["references"][1]=dict(p["references"][0])
    with pytest.raises(ValueError,match="DUPLICATE_AUDIO"):
        prepare(m,p,tmp_path)
