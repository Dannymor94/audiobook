"""CLOUD-QUOTA-01: conservative admission and append-only event replay.

No provider calls or submission. Durable store must use compare-and-swap
against the exact prior ledger revision before any external side effect.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
import re

ACTIVE = frozenset({"RESERVED","SUBMITTING","SUBMITTED","QUEUED","RUNNING",
                    "UNKNOWN","COMPLETE_UNVERIFIED"})
TERMINAL = frozenset({"VERIFIED","FAILED","CANCELLED"})
TRANSITIONS = {
    "RESERVED": {"SUBMITTING","CANCELLED"},
    "SUBMITTING": {"SUBMITTED","UNKNOWN","FAILED"},
    "SUBMITTED": {"QUEUED","RUNNING","UNKNOWN","COMPLETE_UNVERIFIED","FAILED","CANCELLED"},
    "QUEUED": {"QUEUED","RUNNING","UNKNOWN","COMPLETE_UNVERIFIED","FAILED","CANCELLED"},
    "RUNNING": {"RUNNING","UNKNOWN","COMPLETE_UNVERIFIED","FAILED","CANCELLED"},
    "UNKNOWN": {"UNKNOWN","SUBMITTED","QUEUED","RUNNING","COMPLETE_UNVERIFIED","FAILED","CANCELLED"},
    "COMPLETE_UNVERIFIED": {"VERIFIED","UNKNOWN"},
}
HEX = re.compile(r"[0-9a-f]{64}")
KEY = re.compile(r"[a-z0-9][a-z0-9_-]{0,100}")


def timestamp(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt


def integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("INVALID_INTEGER")
    return value


def hours_to_seconds(value):
    """Provider CSV display is rounded; use conservatively rounded down elsewhere."""
    if not isinstance(value,str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?h",value):
        raise ValueError("INVALID_QUOTA")
    try:
        return Decimal(value[:-1])*3600
    except InvalidOperation as exc:
        raise ValueError("INVALID_QUOTA") from exc


def event_hash(event):
    return hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",",":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def replay(events):
    jobs = {}
    prev = "0"*64
    last = None
    for event in events:
        if event["previous_sha256"] != prev:
            raise ValueError("LEDGER_CHAIN_MISMATCH")
        at = timestamp(event["at"])
        if last is not None and at < last:
            raise ValueError("LEDGER_TIME_REVERSED")
        last = at
        key,state = event["key"],event["state"]
        if not KEY.fullmatch(key):
            raise ValueError("INVALID_JOB_KEY")
        if key not in jobs:
            if state != "RESERVED" or any(j["state"] in ACTIVE for j in jobs.values()):
                raise ValueError("RESERVATION_CONFLICT")
            data = event["job"]
            if (data["provider"] != "kaggle" or data["resource"] != "GPU"
                    or data["data_class"] != "public_fixture"
                    or not HEX.fullmatch(data["plan_sha256"])
                    or not HEX.fullmatch(data["code_sha256"])
                    or not HEX.fullmatch(data["model_sha256"])
                    or not data["account"] or not data["slug"]):
                raise ValueError("INVALID_JOB_IDENTITY")
            integer(data["reserved_seconds"],minimum=1)
            jobs[key] = dict(data,state=state,remote_ref=None)
        else:
            j = jobs[key]
            if state not in TRANSITIONS.get(j["state"],set()) or "job" in event:
                raise ValueError("INVALID_TRANSITION")
            ref = event.get("remote_ref")
            if ref is not None:
                if not re.fullmatch(re.escape(j["account"]+"/"+j["slug"])+r"/[1-9][0-9]*",ref):
                    raise ValueError("REMOTE_IDENTITY_MISMATCH")
                if j["remote_ref"] is not None and ref != j["remote_ref"]:
                    raise ValueError("REMOTE_VERSION_CHANGED")
                j["remote_ref"] = ref
            if state in {"SUBMITTED","QUEUED","RUNNING","COMPLETE_UNVERIFIED","VERIFIED"} and not j["remote_ref"]:
                raise ValueError("REMOTE_VERSION_REQUIRED")
            if state in TERMINAL:
                # Evidence is an externally obtained immutable receipt digest,
                # not proof by itself. Controller must verify provider state.
                if not HEX.fullmatch(event.get("evidence_sha256","")):
                    raise ValueError("TERMINAL_EVIDENCE_REQUIRED")
                if state=="VERIFIED" and not HEX.fullmatch(event.get("output_sha256","")):
                    raise ValueError("OUTPUT_EVIDENCE_REQUIRED")
                if j["state"]!="RESERVED" and not j["remote_ref"]:
                    raise ValueError("AMBIGUOUS_SUBMISSION_STILL_RESERVED")
            j["state"] = state
        prev = event_hash(event)
    return jobs,prev


def append_event(events, event, *, expected_tip):
    _,tip = replay(events)
    if tip != expected_tip:
        raise ValueError("LEDGER_COMPARE_AND_SWAP_CONFLICT")
    new = [*events,dict(event,previous_sha256=tip)]
    replay(new)
    return new


def admit(events, quota, request, now):
    """Return a reservation decision only. No submission authorization by itself."""
    jobs,_ = replay(events)
    if any(j["state"] in ACTIVE for j in jobs.values()):
        return dict(allowed=False,reason="OUTSTANDING_GPU_JOB")
    if request["provider"]!="kaggle" or request["resource"]!="GPU" or request["data_class"]!="public_fixture":
        return dict(allowed=False,reason="UNQUALIFIED_ROUTE")
    if quota.get("zero_spend_verified") is not True:
        return dict(allowed=False,reason="ZERO_SPEND_UNVERIFIED")
    if quota.get("account")!=request["account"]:
        return dict(allowed=False,reason="ACCOUNT_MISMATCH")
    at,observed,reset = timestamp(now),timestamp(quota["observed_at"]),timestamp(quota["refresh_at"])
    if not timedelta(0)<=at-observed<=timedelta(minutes=5) or reset<=at:
        return dict(allowed=False,reason="STALE_QUOTA")
    runtime=integer(request["timeout_seconds"],minimum=1)
    count=integer(request["max_gpu_count"],minimum=1)
    # First qualified stage: one GPU, <=10 minutes, no unbounded queue horizon.
    if runtime>600 or count!=1 or request.get("gpu_accounting_verified") is not True:
        return dict(allowed=False,reason="UNQUALIFIED_GPU_BOUND")
    queue=integer(request["max_queue_seconds"],minimum=1)
    if queue>7200 or at+timedelta(seconds=queue+runtime)>=reset:
        return dict(allowed=False,reason="RESET_OR_QUEUE_BOUND")
    total=hours_to_seconds(quota["total"])
    remaining=hours_to_seconds(quota["remaining"])
    used=hours_to_seconds(quota["used"])
    if total<=0 or remaining>total or used>total or abs(total-remaining-used)>Decimal(36):
        return dict(allowed=False,reason="INCONSISTENT_QUOTA")
    # Two decimal hour display can overstate by ~18s; subtract 36s.
    remaining=max(Decimal(0),remaining-36)
    reserve=(total*Decimal(".2")).to_integral_value(rounding=ROUND_CEILING)
    debit=runtime*count
    if remaining-debit<reserve or used+36+debit>total-reserve:
        return dict(allowed=False,reason="RESERVE_LIMIT")
    return dict(allowed=True,reserved_seconds=debit,reserve_seconds=int(reserve),
                refresh_at=quota["refresh_at"],observed_at=quota["observed_at"],
                note="Persist reservation and submission intent with durable CAS before push")
