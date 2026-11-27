import hashlib
import json

import numpy as np
import pytest
import soundfile as sf

from audiobook.rhythm_acoustic_measure import POLICY, measure, compare, quiet_fraction, evaluate


TEXT = "Мама читает, папа слушает."


def words(scale=1):
    return [dict(w=w,s=a*scale,e=b*scale,p=.95)
            for w,a,b in [("Мама",.1,.4),("читает",.5,.9),
                          ("папа",1.3,1.6),("слушает",1.7,2.1)]]


def test_exact_boundary_and_rate():
    m = measure(TEXT,words(),2.3)
    assert m["status"] == "measured"
    assert m["words"] == 4 and m["syllable_proxy"] == 10
    assert m["leading_ms"] == pytest.approx(100)
    assert m["trailing_ms"] == pytest.approx(200)
    assert m["words_per_min"] == pytest.approx(120)
    assert m["gaps"][1]["offset"] == TEXT.index(",")
    assert m["gaps"][1]["category"] == "comma"
    assert m["gaps"][1]["gap_ms"] == pytest.approx(400)
    result = compare(m,measure(TEXT,words(.5),1.15))
    assert result["rate_delta_pct"] == pytest.approx(100)
    assert result["categories"]["comma"]["median_delta_ms"] == pytest.approx(-200)


@pytest.mark.parametrize("kind", ["wrong_word","confidence","overlap","missing"])
def test_bad_alignment_abstains(kind):
    w = words()
    if kind == "wrong_word":
        w[2]["w"] = "мама"
    elif kind == "confidence":
        w[2]["p"] = .2
    elif kind == "overlap":
        w[2]["s"] = .8
    else:
        w.pop()
    r = measure(TEXT,w,2.3)
    assert r["status"] == "uncertain"
    assert compare(measure(TEXT,words(),2.3),r)["status"] == "uncertain"


def test_unsupported_text():
    assert measure("Мама читает 3 книги.",words(),2.3)["reason"] == "unsupported_text"
    assert measure("Мама, папа.",words(),2.3)["reason"] == "short_text"


def test_quiet_gap_measure_not_vad():
    x = np.ones(16000)
    x[4000:8000] = 0
    assert quiet_fraction(x,16000,.25,.5) == 1
    assert quiet_fraction(x,16000,.5,.75) == 0
    assert quiet_fraction(x,16000,.25,.252) is None
    assert quiet_fraction(np.zeros(16000),16000,.25,.5) is None


def fixture(tmp_path):
    def sha(data):
        return hashlib.sha256(data).hexdigest()
    manifest = json.dumps(dict(id="01",hash="fixture",status="done",text=TEXT)).encode()
    pair = dict(id="01",hash="fixture",reference_text_independently_verified=True)
    for arm,scale in (("reference",1),("candidate",.5)):
        name = f"{arm}.wav"
        path = tmp_path/name
        sf.write(path,np.full(int(2.4*scale*16000),.1,dtype=np.float32),16000,subtype="FLOAT")
        digest = sha(path.read_bytes())
        pair[arm] = dict(wav=name,wav_sha256=digest,asr=dict(wav_sha256=digest,words=words(scale)))
    return manifest,dict(policy=POLICY,manifest_sha256=sha(manifest),pairs=[pair])


def test_frozen_pair_runner(tmp_path):
    manifest,plan = fixture(tmp_path)
    summary,rows = evaluate(manifest,plan,tmp_path)
    assert summary["measured"] == 1 and summary["release_ready"] is False
    assert rows[0]["comparison"]["rate_delta_pct"] == pytest.approx(100)


def test_wrong_hash_and_asr_binding(tmp_path):
    manifest,plan = fixture(tmp_path)
    pair = plan["pairs"][0]
    pair["candidate"]["asr"]["wav_sha256"] = "a"*64
    with pytest.raises(ValueError,match="ASR_AUDIO_MISMATCH"):
        evaluate(manifest,plan,tmp_path)
    pair["candidate"]["asr"]["wav_sha256"] = pair["candidate"]["wav_sha256"]
    (tmp_path/"candidate.wav").write_bytes(b"changed")
    with pytest.raises(ValueError,match="DIGEST_MISMATCH"):
        evaluate(manifest,plan,tmp_path)
