import hashlib
import json

import pytest

from audiobook.chapter_quality import build, chapter_rows, verify_ctc, DIMENSIONS
from audiobook.stress_ctc_evidence import summarize_gold


def manifest():
    rows = [
        dict(id="01", hash="h1", text="Мама.", status="done", cer=.01),
        dict(id="02", hash="h2", text="Папа.", status="done", suspect=True),
        dict(id="03", hash="h3", text="Мука.", status="pending"),
    ]
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def findings():
    return [dict(id=cid,hash=h,ordinal=1,start=0,end=4,word=w,status=s)
            for cid,h,w,s in [("01","h1","Мама","agree"),
                              ("02","h2","Папа","disagree"),
                              ("03","h3","Мука","unresolved")]]


def test_no_evidence_is_not_quality_pass():
    summary,rows = build(manifest(),{"01":"a"*64,"02":"b"*64})
    assert [r["priority"] for r in rows] == ["unverified","review","incomplete"]
    assert summary["text_accounting"] is None
    assert summary["release_ready"] is False
    assert summary["human_coverage"]["voice"] == {"unmeasured":3}


def test_complete_text_accounting_is_not_acoustic_verification():
    summary,rows = build(manifest(),{"01":"a"*64,"02":"b"*64},findings=findings())
    assert rows[0]["priority"] == "unverified"
    assert rows[1]["text_risks"] == 1
    assert summary["text_accounting"]["multisyllabic_findings"] == 3
    assert summary["text_accounting"]["acoustic_verified"] == 0
    with pytest.raises(ValueError,match="MISSING_FINDINGS"):
        build(manifest(),{},findings=findings()[:-1])


def human_row(cid="01", dimension="voice", rating="bad"):
    return dict(id=cid,dimension=dimension,rating=rating,
                hash="h1",wav_sha256="a"*64,independently_reviewed=True)


def test_human_defect_and_unmeasured_dimensions():
    h = dict(manifest_sha256=digest(manifest()),rows=[human_row()])
    summary,rows = build(manifest(),{"01":"a"*64},human=h)
    assert rows[0]["priority"] == "human_defect"
    assert summary["human_coverage"]["voice"] == {"bad":1,"unmeasured":2}
    assert summary["human_coverage"]["stress"] == {"unmeasured":3}


@pytest.mark.parametrize("change", ["wav_sha256","hash","independently_reviewed"])
def test_stale_human_evidence_rejected(change):
    row = human_row()
    row[change] = "stale"
    h = dict(manifest_sha256=digest(manifest()),rows=[row])
    with pytest.raises(ValueError,match="HUMAN_IDENTITY_MISMATCH"):
        build(manifest(),{"01":"a"*64},human=h)


def test_explicit_human_ok_still_not_release_authorization():
    h = dict(manifest_sha256=digest(manifest()),
             rows=[human_row(dimension=d,rating="ok") for d in DIMENSIONS])
    summary,rows = build(manifest(),{"01":"a"*64},human=h)
    assert rows[0]["priority"] == "human_review_ok"
    assert summary["release_ready"] is False


def test_ctc_uncertain_human_error_retained_and_no_promotion():
    c = dict(id="01",gold="wrong_stress",wav_sha256="a"*64)
    summary,rows = build(manifest(),{"01":"a"*64},ctc=[(c,"uncertain")])
    assert rows[0]["priority"] == "human_defect"
    assert rows[0]["measurements"]["experimental_stress"] == {"uncertain":1}
    assert summary["human_coverage"]["stress"] == {"unmeasured":3}


def test_ctc_bundle_checks_exact_controls_and_signals():
    m = manifest()
    rows = chapter_rows(m)
    fs = findings()
    controls = [dict(f,expected_index=1,wav_sha256=d,split=s,gold=g)
                for f,d,s,g in [(fs[0],"a"*64,"development","wrong_stress"),
                                (fs[1],"b"*64,"heldout","correct")]]
    results = [dict(id=f"{c['id']}:1",split=c["split"],gold=c["gold"],
                    expected_ordinal=1,evidence={"status":"uncertain"},signal="uncertain")
               for c in controls]
    summary = dict(summarize_gold(results),diagnostic_only=True,thresholds=None,
                   input_sha256={"manifest":digest(m),"controls":"control-digest"})
    args = (digest(m),rows,fs,controls,results,summary,{"01":"a"*64,"02":"b"*64},"control-digest")
    assert len(verify_ctc(*args)) == 2
    results[0]["signal"] = "not_flagged"
    with pytest.raises(ValueError,match="CTC_SIGNAL_MISMATCH"):
        verify_ctc(*args)


def test_rhythm_measurement_is_not_human_rating():
    summary,rows = build(manifest(),{"01":"a"*64},rhythm=[
        dict(id="01",hash="h1",comparison={"status":"measured","rate_delta_pct":25})])
    assert summary["rhythm_measured_chunks"] == 1
    assert rows[0]["priority"] == "unverified"
    assert summary["human_coverage"]["rhythm"] == {"unmeasured":3}
