"""Read-only local unblinding and scoring for ALG-04B. No TTS or private export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audiobook.stress_pilot_review import sha

POLICY = "silero-openvoice-control-v1"
TITLE = "ALG-04B — произношение и голос"
ARMS = ("baseline", "candidate")
FIELDS = {
    "label": {"ok", "bad", "unsure"},
    "heard_stress": {"1", "2", "unclear"},
    "lexical": {"yes", "no", "unclear"},
    "voice": {"yes", "no", "unclear"},
    "rhythm": {"ok", "bad", "unclear"},
}


def index_unique(rows, field):
    idx = {r[field]: r for r in rows}
    if len(idx) != len(rows):
        raise ValueError("DUPLICATE_IDENTITY:" + field)
    return idx


def verify_review(source: Path, review_dir: Path, key: dict, labels: dict) -> list:
    plan_bytes = (source / "plan_PRIVATE.json").read_bytes()
    receipt_bytes = (source / "receipts_PRIVATE.jsonl").read_bytes()
    plan = json.loads(plan_bytes)
    ready = json.loads((source / "READY_PRIVATE.json").read_bytes())
    plan_sha = sha(plan_bytes)
    if (plan["policy"] != POLICY or ready["pairs"] != 4
            or ready["plan_sha256"] != plan_sha
            or ready["receipts_sha256"] != sha(receipt_bytes)
            or key["plan_sha256"] != plan_sha):
        raise ValueError("FROZEN_RUN_MISMATCH")
    trials = index_unique(plan["trials"], "chunk_id")
    if (set(trials) != {"01", "02", "03", "04"}
            or any(t["status"] != "planned" for t in trials.values())
            or sum(t["split"] == "heldout" for t in trials.values()) != 2
            or sum(t["split"] == "development" for t in trials.values()) != 2):
        raise ValueError("TRIAL_INVENTORY_MISMATCH")
    recs = [json.loads(line) for line in receipt_bytes.splitlines() if line.strip()]
    ri = {(r["chunk_id"], r["arm"]): r for r in recs}
    if len(recs) != 8 or set(ri) != {(c, a) for c in trials for a in ARMS}:
        raise ValueError("RECEIPT_INVENTORY_MISMATCH")
    pid = sha(json.dumps(key["items"], sort_keys=True).encode("utf-8"))[:16]
    if (key["page_id"] != pid or labels["page_id"] != pid
            or labels["title"] != TITLE or labels["kind"] != "golden"):
        raise ValueError("BLIND_PAGE_MISMATCH")
    ki = index_unique(key["items"], "file")
    li = index_unique(labels["items"], "file")
    expected = {f"ALG04B-{n:02d}_{side}.wav" for n in range(1, 5) for side in "AB"}
    if set(ki) != expected or set(li) != expected:
        raise ValueError("REVIEW_INVENTORY_MISMATCH")
    seen, verified = set(), []
    for name, k in ki.items():
        cid, arm = k["chunk_id"], k["arm"]
        if (cid, arm) not in ri or (cid, arm) in seen or name[7:9] != cid:
            raise ValueError("BLIND_MAPPING_MISMATCH")
        seen.add((cid, arm))
        t, r, label = trials[cid], ri[cid, arm], li[name]
        expected_source = source / f"{cid}_silero_raw.wav"
        wav = source / f"{cid}_{arm}.wav"
        copied = review_dir / name
        meta = label["meta"]
        if (r["status"] != "generated" or r["plan_sha256"] != plan_sha
                or r["wav"] != wav.name or r["seed"] != t["seed"]
                or r["carrier"] != t["carrier"]
                or r["input_sha256"] != t[arm + "_sha256"]
                or r["generation"] != plan["inventory"]
                or k["target"] != t["target"]
                or k["wav_sha256"] != r["wav_sha256"]
                or meta["wav_sha256"] != r["wav_sha256"]
                or meta["chunk"] != cid or label["chunk"] != cid
                or meta["hash"] != t["chunk_hash"] or label["hash"] != t["chunk_hash"]
                or meta["side"] != name[-5]
                or meta["pair"] != str(int(cid))):
            raise ValueError("REVIEW_IDENTITY_MISMATCH:" + name)
        for path, digest in ((expected_source, r["source_wav_sha256"]),
                             (wav, r["wav_sha256"]), (copied, r["wav_sha256"])):
            if path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != digest:
                raise ValueError("AUDIO_DIGEST_MISMATCH:" + path.name)
        ratings = {field: label.get(field, "") for field in FIELDS}
        if any(value != "" and value not in FIELDS[field] for field, value in ratings.items()):
            raise ValueError("INVALID_RATING:" + name)
        ordinal = t["target"]["vowel_ordinal"]
        if type(ordinal) is not int or ordinal not in (1, 2):
            raise ValueError("INVALID_TARGET_ORDINAL")
        verified.append(dict(chunk_id=cid, split=t["split"], arm=arm,
                             expected_stress=str(ordinal), ratings=ratings))
    return verified


def score(rows: list) -> dict:
    by_pair = {(r["chunk_id"], r["arm"]): r for r in rows}
    if len(rows) != 8 or set(by_pair) != {(c, a) for c in ("01", "02", "03", "04") for a in ARMS}:
        raise ValueError("SCORING_INVENTORY_MISMATCH")
    reasons, incomplete = [], []
    aggregates = {}
    for split in ("development", "heldout"):
        aggregates[split] = {}
        for arm in ARMS:
            selected = [r for r in rows if r["split"] == split and r["arm"] == arm]
            if len(selected) != 2:
                raise ValueError("SCORING_SPLIT_MISMATCH")
            counts = dict(total=2, stress_correct=0, stress_wrong=0,
                          stress_unmeasured=0, lexical_yes=0, voice_yes=0, rhythm_ok=0)
            for r in selected:
                a = r["ratings"]
                h = a["heard_stress"]
                k = ("stress_correct" if h == r["expected_stress"]
                     else "stress_wrong" if h in ("1", "2") else "stress_unmeasured")
                counts[k] += 1
                counts["lexical_yes"] += a["lexical"] == "yes"
                counts["voice_yes"] += a["voice"] == "yes"
                counts["rhythm_ok"] += a["rhythm"] == "ok"
            aggregates[split][arm] = counts
    for cid in ("01", "02", "03", "04"):
        b, c = (by_pair[cid, arm] for arm in ARMS)
        for r in (b, c):
            a = r["ratings"]
            if any(not a[k] for k in FIELDS):
                incomplete.append(f"{cid}:{r['arm']}")
        if c["split"] != b["split"] or c["expected_stress"] != b["expected_stress"]:
            raise ValueError("PAIR_TARGET_MISMATCH")
        if c["split"] != "heldout":
            continue
        br, cr = b["ratings"], c["ratings"]
        for arm, r in (("baseline", b), ("candidate", c)):
            a = r["ratings"]
            if a["heard_stress"] != r["expected_stress"]:
                reasons.append(f"{cid}:{arm}:stress_not_confirmed")
            if a["lexical"] != "yes":
                reasons.append(f"{cid}:{arm}:lexical_not_confirmed")
        if cr["voice"] != "yes":
            reasons.append(f"{cid}:candidate:voice_not_confirmed")
        if (br["rhythm"] not in ("ok", "bad") or cr["rhythm"] not in ("ok", "bad")
                or (br["rhythm"] == "ok" and cr["rhythm"] != "ok")):
            reasons.append(f"{cid}:rhythm_nonregression_not_confirmed")
        if cr["label"] != "ok":
            reasons.append(f"{cid}:candidate:overall_not_ok")
    # An incomplete form never passes; clear heldout failure still takes priority.
    verdict = "NOT_PASSED" if reasons else "INCOMPLETE" if incomplete else "DIAGNOSTIC_PASS"
    return dict(policy=POLICY, verdict=verdict, counts=aggregates,
                reasons=reasons, incomplete=incomplete,
                production_authorized=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "review-dir", "private-key", "labels"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    rows = verify_review(a.source, a.review_dir, json.loads(a.private_key.read_bytes()),
                         json.loads(a.labels.read_bytes()))
    print(json.dumps(score(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
