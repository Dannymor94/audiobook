"""Compare private syntax proposals to explicit, frozen human annotations.

Unknown offsets never count as false positives; unresolved parses are reported
separately and count as misses for known positive boundaries. No TTS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audiobook.rhythm_syntax import protected_commas


def _index(rows):
    by_id = {r["id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError("DUPLICATE_CHUNK")
    return by_id


def _offsets(values, text):
    if (not isinstance(values, list)
            or any(type(i) is not int or not 0 <= i < len(text) or text[i] != ","
                   for i in values)
            or len(values) != len(set(values))):
        raise ValueError("INVALID_COMMA_OFFSETS")
    return set(values)


def evaluate(manifest_bytes: bytes, predictions: dict, gold: dict) -> dict:
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if any(d.get("manifest_sha256") != digest for d in (predictions, gold)):
        raise ValueError("MANIFEST_DIGEST_MISMATCH")
    source = _index([json.loads(l) for l in manifest_bytes.decode("utf-8").splitlines()
                     if l.strip()])
    pred, labels = _index(predictions["rows"]), _index(gold["rows"])
    if set(pred) != set(source) or not labels or not set(labels) <= set(source):
        raise ValueError("INVENTORY_MISMATCH")
    totals = {s: dict(chunks=0, unresolved=0, tp=0, fp=0, fn=0,
                      unknown_proposals=0, protected_proposals=0)
              for s in ("development", "heldout")}
    for cid, p in pred.items():
        row = source[cid]
        if p["hash"] != row["hash"] or p["status"] not in ("parsed", "unresolved"):
            raise ValueError("PREDICTION_IDENTITY_MISMATCH")
        text = row["text"]
        proposed = _offsets(p.get("candidate_offsets", []), text)
        if p["status"] == "unresolved" and proposed:
            raise ValueError("UNRESOLVED_HAS_PROPOSALS")
        protected = protected_commas(text)
        if cid not in labels:
            continue
        g = labels[cid]
        if g["hash"] != row["hash"] or g["split"] not in totals:
            raise ValueError("GOLD_IDENTITY_MISMATCH")
        positive = _offsets(g["positive"], text)
        negative = _offsets(g["negative"], text)
        if positive & (negative | protected):
            raise ValueError("GOLD_CONFLICT")
        negative |= protected
        t = totals[g["split"]]
        t["chunks"] += 1
        t["unresolved"] += p["status"] == "unresolved"
        t["tp"] += len(proposed & positive)
        t["fp"] += len(proposed & negative)
        t["fn"] += len(positive - proposed)
        t["unknown_proposals"] += len(proposed - positive - negative)
        t["protected_proposals"] += len(proposed & protected)
    for t in totals.values():
        tp, fp, fn = t["tp"], t["fp"], t["fn"]
        t["precision_on_labeled_proposals"] = tp / (tp+fp) if tp+fp else None
        t["recall_on_known_positive"] = tp / (tp+fn) if tp+fn else None
    return {"manifest_sha256": digest, "splits": totals,
            "all_manifest_protected_proposals": sum(
                len(set(p.get("candidate_offsets", [])) & protected_commas(source[c]["text"]))
                for c, p in pred.items()),
            "unlabeled_chunks": len(source)-len(labels)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("predictions", type=Path)
    p.add_argument("gold", type=Path)
    a = p.parse_args()
    print(json.dumps(evaluate(a.manifest.read_bytes(),
                              json.loads(a.predictions.read_bytes()),
                              json.loads(a.gold.read_bytes())), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
