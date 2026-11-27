"""ALG-07: local, read-only chapter quality inventory; never an acceptance gate."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

from audiobook.rhythm_acoustic_measure import frozen
from audiobook.stress_coverage import build_ledger
from audiobook.stress_acoustic_calibration import validate_controls
from audiobook.stress_ctc_calibration import calibrate
from audiobook.stress_ctc_evidence import decide, summarize_gold
from audiobook.pocket_preflight import sha

POLICY = "chapter-quality-inventory-v1"
DIMENSIONS = ("stress", "lexical", "rhythm", "voice", "artifacts")


def chapter_rows(data):
    rows = [json.loads(l) for l in data.splitlines() if l.strip()]
    idx = {r["id"]: r for r in rows}
    if not rows or len(idx) != len(rows) or any(
            not isinstance(r["id"], str) or not re.fullmatch(r"[0-9]+", r["id"])
            or not isinstance(r["hash"], str) or not r["hash"]
            or not isinstance(r["text"], str) for r in rows):
        raise ValueError("INVALID_MANIFEST")
    return idx


def verify_ctc(manifest_digest, rows, findings, controls, results, summary, audio, control_digest):
    if (summary.get("release_ready") is not False
            or summary.get("diagnostic_only") is not True
            or summary["input_sha256"]["manifest"] != manifest_digest
            or summary["input_sha256"]["controls"] != control_digest):
        raise ValueError("CTC_PROVENANCE_MISMATCH")
    selected = validate_controls(list(rows.values()), findings, controls)
    expected = {f"{c['id']}:{c['ordinal']}": c for c in selected.values()}
    idx = {r["id"]: r for r in results}
    if len(idx) != len(results) or set(idx) != set(expected):
        raise ValueError("CTC_INVENTORY_MISMATCH")
    # JSON object keys are strings; CTC ranks use integer vowel ordinals.
    # Normalize only canonical decimal ordinal keys, reject collisions.
    results = [dict(r, evidence=dict(r["evidence"])) for r in results]
    for r in results:
        e = r["evidence"]
        if e["status"] == "ranked":
            scores = e["scores"]
            normalized = {}
            for k, v in scores.items():
                if type(k) is int:
                    ordinal = k
                elif isinstance(k, str) and k in tuple(str(i) for i in range(1, 9)):
                    ordinal = int(k)
                else:
                    raise ValueError("INVALID_CTC_SCORE_KEY")
                if not 1 <= ordinal <= 8 or ordinal in normalized:
                    raise ValueError("INVALID_CTC_SCORE_KEY")
                normalized[ordinal] = v
            e["scores"] = normalized
    idx = {r["id"]: r for r in results}
    thresholds = calibrate(results)
    if thresholds != summary["thresholds"]:
        raise ValueError("CTC_THRESHOLD_MISMATCH")
    for key, c in expected.items():
        r = idx[key]
        from audiobook.stress_consensus import VOWELS
        ordinal = sum(v.lower() in VOWELS for v in c["word"][:c["expected_index"]+1])
        if (audio.get(c["id"]) != c["wav_sha256"] or rows[c["id"]]["status"] != "done"
                or r["gold"] != c["gold"] or r["split"] != c["split"]
                or r["expected_ordinal"] != ordinal):
            raise ValueError("CTC_CONTROL_MISMATCH")
        signal = decide(r["evidence"], expected_ordinal=ordinal, **thresholds) if thresholds else "uncertain"
        if r["signal"] != signal:
            raise ValueError("CTC_SIGNAL_MISMATCH")
    if summarize_gold(results)["splits"] != summary["splits"]:
        raise ValueError("CTC_SUMMARY_MISMATCH")
    return [(expected[k], r["signal"]) for k,r in idx.items()]


def verify_voice(manifest_digest, rows, audio, results, summary):
    from audiobook.voice_similarity import POLICY as VOICE_POLICY, MODEL_SHA
    if (summary["policy"] != VOICE_POLICY or summary["model_sha256"] != MODEL_SHA
            or summary["manifest_sha256"] != manifest_digest
            or summary.get("release_ready") is not False
            or summary["candidates"] != len(results)
            or len({r["id"] for r in results}) != len(results)):
        raise ValueError("VOICE_PROVENANCE_MISMATCH")
    measured = []
    for r in results:
        cid = r["id"]
        if (cid not in rows or rows[cid]["status"] != "done"
                or rows[cid]["hash"] != r["hash"] or cid not in audio
                or audio[cid] != r["wav_sha256"]
                or r["status"] not in ("measured", "uncertain")):
            raise ValueError("VOICE_IDENTITY_MISMATCH")
        if r["status"] == "measured":
            v = r["cosine"]
            if (type(v) not in (int,float) or not math.isfinite(v) or not -1 <= v <= 1
                    or r.get("diagnostic_only") is not True
                    or type(r.get("below_observed_reference_range")) is not bool):
                raise ValueError("INVALID_VOICE_METRIC")
            measured.append(r)
    import statistics
    if (summary["measured"] != len(measured)
            or summary["uncertain"] != len(results)-len(measured)
            or summary["median_cosine"] != (statistics.median(r["cosine"] for r in measured) if measured else None)
            or summary["below_observed_reference_range"] != sum(r["below_observed_reference_range"] for r in measured)):
        raise ValueError("VOICE_SUMMARY_MISMATCH")
    return results


def build(manifest_bytes, audio, *, findings=None, human=None, ctc=None, rhythm=None, voice=None):
    rows = chapter_rows(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if not set(audio) <= set(rows):
        raise ValueError("UNKNOWN_AUDIO")
    reports = {cid: dict(id=cid, hash=r["hash"], wav_sha256=audio.get(cid),
                         render_status=r.get("status", "unknown"), issues=[],
                         text_risks=0, measurements={}, human={})
               for cid,r in rows.items()}
    for cid,r in rows.items():
        item = reports[cid]
        if cid not in audio or r.get("status") != "done":
            item["issues"].append("render_incomplete")
        # Manifest QC fields lack exact WAV digest; historical hints only.
        if r.get("status") in ("manual", "qc_fail") or r.get("flag_words") or r.get("suspect"):
            item["issues"].append("historical_qc_flag")
        if type(r.get("cer")) in (float,int) and math.isfinite(r["cer"]) and 0 <= r["cer"] <= 1:
            item["measurements"]["historical_cer"] = r["cer"]
    text_summary = None
    if findings is not None:
        _,text_summary = build_ledger(list(rows.values()), findings)
        for f in findings:
            if f["status"] != "agree":
                reports[f["id"]]["text_risks"] += 1
        for item in reports.values():
            if item["text_risks"]:
                item["issues"].append("text_stress_risk")
    if human is not None:
        if human["manifest_sha256"] != digest:
            raise ValueError("HUMAN_MANIFEST_MISMATCH")
        seen = set()
        for h in human["rows"]:
            cid,dim = h["id"],h["dimension"]
            if ((cid,dim) in seen or cid not in rows or dim not in DIMENSIONS
                    or h["hash"] != rows[cid]["hash"] or cid not in audio
                    or h["wav_sha256"] != audio[cid]
                    or h["rating"] not in ("ok","bad","unsure")
                    or h.get("independently_reviewed") is not True):
                raise ValueError("HUMAN_IDENTITY_MISMATCH")
            seen.add((cid,dim))
            reports[cid]["human"][dim] = h["rating"]
            if h["rating"] != "ok":
                reports[cid]["issues"].append("human_"+dim+"_"+h["rating"])
    if ctc is not None:
        for c,signal in ctc:
            cid = c["id"]
            if cid not in rows or c["wav_sha256"] != audio.get(cid):
                raise ValueError("CTC_AUDIO_MISMATCH")
            item = reports[cid]
            counts = item["measurements"].setdefault("experimental_stress",{})
            counts[signal] = counts.get(signal,0)+1
            if signal == "stress_suspect":
                item["issues"].append("experimental_stress_suspect")
            if c["gold"] in ("wrong_stress","lexical_error"):
                item["issues"].append("human_occurrence_"+c["gold"])
    if rhythm is not None:
        for r in rhythm:
            cid = r["id"]
            if cid not in rows or rows[cid]["hash"] != r["hash"]:
                raise ValueError("RHYTHM_IDENTITY_MISMATCH")
            comp = r["comparison"]
            item = reports[cid]
            item["measurements"]["rhythm"] = comp
            if comp["status"] != "measured":
                item["issues"].append("rhythm_unmeasured")
    if voice is not None:
        for r in voice:
            item = reports[r["id"]]
            item["measurements"]["experimental_voice"] = {
                k:v for k,v in r.items() if k not in ("id","hash","wav_sha256")}
            if r["status"] == "measured" and r["below_observed_reference_range"]:
                item["issues"].append("experimental_voice_outside_reference_range")
    priorities = Counter()
    for item in reports.values():
        issues = sorted(set(item["issues"]))
        item["issues"] = issues
        if "render_incomplete" in issues:
            priority = "incomplete"
        elif any(s.startswith("human_occurrence_") or (s.startswith("human_") and s.endswith("_bad")) for s in issues):
            priority = "human_defect"
        elif issues:
            priority = "review"
        elif all(item["human"].get(dim) == "ok" for dim in DIMENSIONS):
            priority = "human_review_ok"
        else:
            priority = "unverified"
        item["priority"] = priority
        priorities[priority] += 1
    summary = dict(policy=POLICY,manifest_sha256=digest,chunks=len(rows),wav_present=len(audio),
                   priorities=dict(priorities),text_accounting=text_summary,
                   human_coverage={dim:dict(Counter(r["human"].get(dim,"unmeasured")
                                                   for r in reports.values()))
                                   for dim in DIMENSIONS},
                   experimental_stress_chunks=sum("experimental_stress" in r["measurements"] for r in reports.values()),
                   rhythm_measured_chunks=sum(r["measurements"].get("rhythm",{}).get("status")=="measured" for r in reports.values()),
                   voice_measured_chunks=sum(r["measurements"].get("experimental_voice",{}).get("status")=="measured" for r in reports.values()),
                   release_ready=False)
    return summary,list(reports.values())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","chunks-dir","out"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--manifest-sha256",required=True)
    # Optional evidence bundle paths must come with externally frozen digests.
    names = ("findings","human","ctc-controls","ctc-results","ctc-summary","rhythm-plan","voice-results","voice-summary")
    for name in names:
        p.add_argument("--"+name,type=Path)
        p.add_argument("--"+name+"-sha256")
    p.add_argument("--rhythm-audio-root",type=Path)
    a = p.parse_args()
    from audiobook import paths
    out = a.out.resolve()
    if out.exists() or any(out.is_relative_to(r) for r in
                           (paths.ROOT.resolve(), paths.OUT.resolve(), a.chunks_dir.resolve())):
        raise ValueError("NEW_ISOLATED_OUTPUT_REQUIRED")
    manifest = frozen(a.manifest,a.manifest_sha256)
    rows = chapter_rows(manifest)
    def read_evidence():
        result = {}
        for name in names:
            key = name.replace("-","_")
            path,d = getattr(a,key),getattr(a,key+"_sha256")
            if (path is None) != (d is None):
                raise ValueError("EVIDENCE_DIGEST_REQUIRED:"+name)
            if path is not None:
                result[key] = frozen(path,d)
        return result
    raw = read_evidence()
    def audio_inventory():
        result = {}
        for cid in rows:
            path = a.chunks_dir / f"{cid}.wav"
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ValueError("INVALID_WAV_PATH")
            if path.is_file():
                result[cid] = sha(path)
        return result
    audio = audio_inventory()
    findings = [json.loads(l) for l in raw["findings"].splitlines() if l.strip()] if "findings" in raw else None
    ctc = None
    if any(k.startswith("ctc_") for k in raw):
        if findings is None or not {"ctc_controls","ctc_results","ctc_summary"} <= raw.keys():
            raise ValueError("COMPLETE_CTC_BUNDLE_REQUIRED")
        summary = json.loads(raw["ctc_summary"])
        if summary["input_sha256"]["audit"] != a.findings_sha256:
            raise ValueError("CTC_AUDIT_MISMATCH")
        ctc = verify_ctc(a.manifest_sha256,rows,findings,json.loads(raw["ctc_controls"]),
                         json.loads(raw["ctc_results"]),summary,audio,a.ctc_controls_sha256)
    rhythm = None
    if "rhythm_plan" in raw:
        if a.rhythm_audio_root is None:
            raise ValueError("RHYTHM_AUDIO_ROOT_REQUIRED")
        plan = json.loads(raw["rhythm_plan"])
        for pair in plan["pairs"]:
            if audio.get(pair["id"]) != pair["candidate"]["wav_sha256"]:
                raise ValueError("RHYTHM_CANDIDATE_NOT_CANONICAL")
        from audiobook.rhythm_acoustic_measure import evaluate
        _,rhythm = evaluate(manifest,plan,a.rhythm_audio_root)
    elif a.rhythm_audio_root is not None:
        raise ValueError("RHYTHM_PLAN_REQUIRED")
    voice = None
    if "voice_results" in raw or "voice_summary" in raw:
        if not {"voice_results","voice_summary"} <= raw.keys():
            raise ValueError("COMPLETE_VOICE_BUNDLE_REQUIRED")
        voice = verify_voice(a.manifest_sha256,rows,audio,
                             json.loads(raw["voice_results"]),json.loads(raw["voice_summary"]))
    summary,report = build(manifest,audio,findings=findings,
                           human=json.loads(raw["human"]) if "human" in raw else None,
                           ctc=ctc,rhythm=rhythm,voice=voice)
    if frozen(a.manifest,a.manifest_sha256)!=manifest or read_evidence()!=raw or audio_inventory()!=audio:
        raise ValueError("INPUTS_CHANGED")
    summary["evidence_sha256"] = {k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}
    out.mkdir(mode=0o700,exist_ok=False)
    (out/"chapter_PRIVATE.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    lines = ["chunk\tpriority\ttext_risks\tissues"]
    order = {"incomplete":0,"human_defect":1,"review":2,"unverified":3,"human_review_ok":4}
    for r in sorted(report,key=lambda r:order[r["priority"]]):
        lines.append(f"{r['id']}\t{r['priority']}\t{r['text_risks']}\t{','.join(r['issues'])}")
    (out/"queue_PRIVATE.tsv").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
