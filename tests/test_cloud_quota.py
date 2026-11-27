from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from audiobook.cloud_quota import admit, append_event, replay

NOW="2026-11-27T17:10:00+00:00"

def quota(**kw):
    return dict(account="demo",observed_at=NOW,refresh_at="2026-11-28T00:00:00+00:00",
                total="30.00h",remaining="30.00h",used="0.00h",zero_spend_verified=True,**kw)

def request(**kw):
    q=dict(provider="kaggle",resource="GPU",data_class="public_fixture",account="demo",
           timeout_seconds=600,max_gpu_count=1,max_queue_seconds=7200,gpu_accounting_verified=True)
    q.update(kw)
    return q

def reserve():
    return append_event([],dict(at=NOW,key="test",state="RESERVED",
        job=dict(provider="kaggle",resource="GPU",data_class="public_fixture",account="demo",
            slug="public-test",reserved_seconds=600,plan_sha256="a"*64,code_sha256="b"*64,
            model_sha256="c"*64)),expected_tip="0"*64)

def step(events,state,**kw):
    _,tip=replay(events)
    return append_event(events,dict(at=NOW,key="test",state=state,**kw),expected_tip=tip)

def test_admission():
    d=admit([],quota(),request(),NOW)
    assert d["allowed"] and d["reserved_seconds"]==600 and d["reserve_seconds"]==21600

@pytest.mark.parametrize("changes,reason",[
    ({"zero_spend_verified":False},"ZERO_SPEND_UNVERIFIED"),
    ({"observed_at":"2026-11-27T17:04:59+00:00"},"STALE_QUOTA"),
    ({"refresh_at":"2026-11-27T18:00:00+00:00"},"RESET_OR_QUEUE_BOUND"),
    ({"remaining":"6.10h","used":"23.90h"},"RESERVE_LIMIT"),
    ({"remaining":"31.00h"},"INCONSISTENT_QUOTA"),
    ({"account":"other"},"ACCOUNT_MISMATCH")])
def test_quota_block(changes,reason):
    q=quota();q.update(changes)
    assert admit([],q,request(),NOW)==dict(allowed=False,reason=reason)

@pytest.mark.parametrize("changes,reason",[
    ({"max_gpu_count":2},"UNQUALIFIED_GPU_BOUND"),
    ({"timeout_seconds":601},"UNQUALIFIED_GPU_BOUND"),
    ({"gpu_accounting_verified":False},"UNQUALIFIED_GPU_BOUND"),
    ({"data_class":"private"},"UNQUALIFIED_ROUTE"),
    ({"provider":"modal"},"UNQUALIFIED_ROUTE")])
def test_route_block(changes,reason):
    assert admit([],quota(),request(**changes),NOW)==dict(allowed=False,reason=reason)

def test_unknown_stays_reserved():
    e=step(step(reserve(),"SUBMITTING"),"UNKNOWN")
    assert admit(e,quota(),request(),NOW)["reason"]=="OUTSTANDING_GPU_JOB"
    with pytest.raises(ValueError,match="AMBIGUOUS_SUBMISSION"):
        step(e,"FAILED",evidence_sha256="d"*64)

def test_verified_requires_exact_version_and_evidence():
    e=step(step(reserve(),"SUBMITTING"),"SUBMITTED",remote_ref="demo/public-test/1")
    e=step(e,"COMPLETE_UNVERIFIED")
    with pytest.raises(ValueError,match="TERMINAL_EVIDENCE"):
        step(e,"VERIFIED")
    with pytest.raises(ValueError,match="REMOTE_VERSION_CHANGED"):
        step(e,"VERIFIED",remote_ref="demo/public-test/2",evidence_sha256="d"*64,output_sha256="e"*64)
    e=step(e,"VERIFIED",evidence_sha256="d"*64,output_sha256="e"*64)
    assert admit(e,quota(),request(),NOW)["allowed"]

def test_chain_and_cas():
    e=reserve()
    with pytest.raises(ValueError,match="COMPARE_AND_SWAP"):
        append_event(e,{},expected_tip="0"*64)
    bad=deepcopy(step(e,"SUBMITTING"))
    bad[0]["job"]["reserved_seconds"]=601
    with pytest.raises(ValueError,match="CHAIN"):
        replay(bad)

def test_real_legacy_hold():
    path=Path(__file__).resolve().parents[1]/"cloud"/"ledger"/"gpu-events.jsonl"
    events=[json.loads(line) for line in path.read_text().splitlines()]
    jobs,_=replay(events)
    assert jobs["legacy-46019695614"]["state"]=="UNKNOWN"
    assert admit(events,quota(),request(),NOW)["reason"]=="OUTSTANDING_GPU_JOB"
