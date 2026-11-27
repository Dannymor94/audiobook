"""ALG-09: one local report/review batch from explicitly frozen evidence.

No new inference, automatic repairs, chapter acceptance or production writes.
The configuration is data, never an arbitrary shell command.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

from audiobook.chapter_quality import POLICY as CHAPTER_POLICY, chapter_rows
from audiobook.rhythm_acoustic_measure import frozen
from audiobook import review

POLICY = "chapter-quality-batch-v1"
EVIDENCE = {"findings", "human", "ctc-controls", "ctc-results", "ctc-summary",
            "rhythm-plan", "voice-results", "voice-summary"}
MAX_REVIEW = 12


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_plan(plan):
    required = {"policy", "manifest", "chunks_dir", "evidence"}
    if (not required <= set(plan) or set(plan)-required-{"rhythm_audio_root","review_limit"}
            or plan["policy"] != POLICY or not isinstance(plan["evidence"],dict)
            or not set(plan["evidence"]) <= EVIDENCE):
        raise ValueError("INVALID_BATCH_PLAN")
    limit = plan.get("review_limit",MAX_REVIEW)
    if type(limit) is not int or not 1 <= limit <= MAX_REVIEW:
        raise ValueError("INVALID_REVIEW_LIMIT")
    for item in [plan["manifest"],*plan["evidence"].values()]:
        if (set(item)!={"path","sha256"} or not Path(item["path"]).is_absolute()
                or not re.fullmatch(r"[a-f0-9]{64}",item["sha256"])):
            raise ValueError("EXPLICIT_FROZEN_INPUT_REQUIRED")
    for key in ("chunks_dir","rhythm_audio_root"):
        if key in plan and not Path(plan[key]).is_absolute():
            raise ValueError("ABSOLUTE_DIRECTORY_REQUIRED")
    names = set(plan["evidence"])
    ctc = {"ctc-controls","ctc-results","ctc-summary"}
    voice = {"voice-results","voice-summary"}
    if names & ctc and not ctc|{"findings"} <= names:
        raise ValueError("INCOMPLETE_CTC_BUNDLE")
    if names & voice and not voice <= names:
        raise ValueError("INCOMPLETE_VOICE_BUNDLE")
    if ("rhythm-plan" in names)!=("rhythm_audio_root" in plan):
        raise ValueError("INCOMPLETE_RHYTHM_BUNDLE")
    return limit


def choose_review(rows,limit):
    """Prioritize actual issues; sample at most four unverified chunks."""
    if type(limit) is not int or not 1<=limit<=MAX_REVIEW:
        raise ValueError("INVALID_REVIEW_LIMIT")
    ranked = {"human_defect":0,"review":1}
    eligible = [r for r in rows if r["render_status"]=="done" and r["wav_sha256"]]
    flagged = sorted((r for r in eligible if r["priority"] in ranked),
                     key=lambda r:(ranked[r["priority"]],-r["text_risks"]))
    chosen=flagged[:limit]
    unknown=[r for r in eligible if r["priority"]=="unverified"]
    n=min(4,limit-len(chosen),len(unknown))
    if n==1:
        chosen.append(unknown[len(unknown)//2])
    elif n>1:
        chosen.extend(unknown[i*(len(unknown)-1)//(n-1)] for i in range(n))
    return chosen


def make_review(manifest,report,summary,chunks,out,limit):
    idx=chapter_rows(manifest)
    if (summary["policy"]!=CHAPTER_POLICY or summary["manifest_sha256"]!=digest(manifest)
            or summary.get("release_ready") is not False
            or len(report)!=len(idx) or {r["id"] for r in report}!=set(idx)):
        raise ValueError("REPORT_IDENTITY_MISMATCH")
    for r in report:
        if r["hash"]!=idx[r["id"]]["hash"] or r["render_status"]!=idx[r["id"]].get("status","unknown"):
            raise ValueError("REPORT_ROW_MISMATCH")
    selected=choose_review(report,limit)
    if not selected:
        return dict(selected=0,page_id=None)
    out.mkdir(mode=0o700,exist_ok=False)
    groups=[]
    items=[]
    titles={"human_defect":"Подтверждённая проблема","review":"Требуется проверка",
            "unverified":"Контрольная выборка"}
    for r in selected:
        cid=r["id"]
        data=frozen(chunks/f"{cid}.wav",r["wav_sha256"])
        name=f"{cid}.wav"
        (out/name).write_bytes(data)
        meta=dict(chunk=cid,hash=r["hash"],wav_sha256=r["wav_sha256"],
                  text=idx[cid]["text"],item=titles[r["priority"]])
        groups.append([dict(file=name,name=f"{cid} · {titles[r['priority']]}",meta=meta)])
        items.append(dict(file=name,id=cid,hash=r["hash"],wav_sha256=r["wav_sha256"],
                          priority=r["priority"],issues=r["issues"]))
    # Bind localStorage/export identity to the exact audio, not directory name.
    identity=dict(manifest_sha256=digest(manifest),items=items)
    pid=digest(json.dumps(identity,sort_keys=True).encode())[:16]
    (out/"review.html").write_text(review.render("Глава — контроль качества","generic",groups,pid),
                                   encoding="utf-8")
    (out/"review_inventory_PRIVATE.json").write_text(json.dumps(dict(identity,page_id=pid),
                                    ensure_ascii=False,indent=2),encoding="utf-8")
    return dict(selected=len(items),page_id=pid,
                review_candidates_total=sum(r["priority"] in ranked_priorities()
                                             and r["render_status"]=="done" and bool(r["wav_sha256"])
                                             for r in report))


def ranked_priorities():
    return ("human_defect","review")


def execute(plan,out):
    limit=validate_plan(plan)
    m=plan["manifest"]
    manifest=frozen(Path(m["path"]),m["sha256"])
    chunks=Path(plan["chunks_dir"]).resolve(strict=True)
    from audiobook import paths
    forbidden=[paths.ROOT.resolve(),paths.OUT.resolve(),chunks]
    if "rhythm_audio_root" in plan:
        forbidden.append(Path(plan["rhythm_audio_root"]).resolve(strict=True))
    out=out.resolve()
    if out.exists() or any(out.is_relative_to(r) for r in forbidden):
        raise ValueError("NEW_ISOLATED_OUTPUT_REQUIRED")
    # Fail before any report if an explicitly requested evidence file is stale.
    for e in plan["evidence"].values():
        frozen(Path(e["path"]),e["sha256"])
    out.mkdir(mode=0o700,exist_ok=False)
    started=datetime.now(timezone.utc).isoformat()
    clock=perf_counter()
    args=[sys.executable,"-m","audiobook.chapter_quality",
          "--manifest",m["path"],"--manifest-sha256",m["sha256"],
          "--chunks-dir",str(chunks),"--out",str(out/"report")]
    for name,e in sorted(plan["evidence"].items()):
        args.extend(["--"+name,e["path"],"--"+name+"-sha256",e["sha256"]])
    if "rhythm_audio_root" in plan:
        args.extend(["--rhythm-audio-root",plan["rhythm_audio_root"]])
    receipt=dict(policy=POLICY,started_at=started,release_ready=False,
                 manifest_sha256=m["sha256"],status="FAILED")
    try:
        # Fixed module/arguments; no shell, no arbitrary commands, no inference.
        subprocess.run(args,check=True,timeout=600)
        summary=json.loads((out/"report"/"summary.json").read_bytes())
        report=json.loads((out/"report"/"chapter_PRIVATE.json").read_bytes())
        receipt["review"]=make_review(manifest,report,summary,chunks,out/"listen",limit)
        frozen(Path(m["path"]),m["sha256"])
        for e in plan["evidence"].values():
            frozen(Path(e["path"]),e["sha256"])
        receipt["status"]="REPORT_READY"
        receipt["summary_sha256"]=digest((out/"report"/"summary.json").read_bytes())
        receipt["evidence_included"]=sorted(plan["evidence"])
        receipt["evidence_not_supplied"]=sorted(EVIDENCE-set(plan["evidence"]))
    finally:
        receipt.update(finished_at=datetime.now(timezone.utc).isoformat(),
                       elapsed_s=perf_counter()-clock)
        (out/"run_PRIVATE.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--plan-sha256",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    data=frozen(a.plan,a.plan_sha256)
    result=execute(json.loads(data),a.out)
    frozen(a.plan,a.plan_sha256)
    print(json.dumps(result))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
