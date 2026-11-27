import hashlib
import json

import pytest

from audiobook.quality_batch import POLICY, validate_plan, choose_review, execute


def digest(b):
    return hashlib.sha256(b).hexdigest()


def fixture(tmp_path):
    chunks=tmp_path/"chunks"
    chunks.mkdir()
    rows=[]
    for i in range(1,7):
        cid=f"{i:02d}"
        rows.append(dict(id=cid,hash=f"hash{i}",text="Мама.",status="done",
                         suspect=i==2))
        (chunks/f"{cid}.wav").write_bytes(f"synthetic fixture {i}".encode())
    manifest=tmp_path/"manifest.jsonl"
    data="\n".join(json.dumps(r,ensure_ascii=False) for r in rows).encode()
    manifest.write_bytes(data)
    plan=dict(policy=POLICY,manifest=dict(path=str(manifest),sha256=digest(data)),
              chunks_dir=str(chunks),evidence={},review_limit=3)
    return plan


def test_one_command_report_and_review_pack(tmp_path):
    plan=fixture(tmp_path)
    out=tmp_path/"batch"
    receipt=execute(plan,out)
    assert receipt["status"]=="REPORT_READY" and receipt["release_ready"] is False
    assert receipt["review"]["selected"]==3
    summary=json.loads((out/"report"/"summary.json").read_bytes())
    assert summary["chunks"]==6 and summary["human_coverage"]["voice"]=={"unmeasured":6}
    inv=json.loads((out/"listen"/"review_inventory_PRIVATE.json").read_bytes())
    assert [r["id"] for r in inv["items"]]==["02","01","06"]
    assert inv["page_id"]==receipt["review"]["page_id"]
    for row in inv["items"]:
        assert digest((out/"listen"/row["file"]).read_bytes())==row["wav_sha256"]
    assert "Глава" in (out/"listen"/"review.html").read_text(encoding="utf-8")
    assert len(list((tmp_path/"chunks").glob("*.wav")))==6


def test_stale_evidence_no_report(tmp_path):
    plan=fixture(tmp_path)
    evidence=tmp_path/"human.json"
    evidence.write_bytes(b"{}")
    plan["evidence"]["human"]=dict(path=str(evidence),sha256="0"*64)
    with pytest.raises(ValueError,match="DIGEST_MISMATCH"):
        execute(plan,tmp_path/"batch")
    assert not (tmp_path/"batch").exists()


@pytest.mark.parametrize("kind",["ctc-controls","voice-results","rhythm-plan"])
def test_partial_evidence_bundle_rejected(tmp_path,kind):
    plan=fixture(tmp_path)
    plan["evidence"][kind]=dict(path=str(tmp_path/"unused"),sha256="a"*64)
    with pytest.raises(ValueError,match="INCOMPLETE"):
        validate_plan(plan)


def test_review_prioritizes_defects_and_bounds_samples():
    rows=[dict(id=str(i),render_status="done",wav_sha256="hash",text_risks=0,
               priority="unverified") for i in range(20)]
    rows[2]["priority"]="review"
    rows[9]["priority"]="human_defect"
    rows[1]["priority"]="human_review_ok"
    rows[5]["render_status"]="pending"
    chosen=choose_review(rows,12)
    assert [r["id"] for r in chosen[:2]]==["9","2"]
    assert len(chosen)==6
    assert {"1","5"}.isdisjoint(r["id"] for r in chosen)
