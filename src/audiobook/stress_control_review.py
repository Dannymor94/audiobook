"""Blind local evaluation of S4a takes; no models, synthesis or release approval."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

from audiobook.stress_consensus import VOWELS
from audiobook.stress_control_baseline import ACUTE, trial_plan, sha256

FIELDS = ("clip", "sentence", "target", "lexical", "heard_vowel", "naturalness")


def read_run(path: Path, *, expected_plan: list[dict] | None = None) -> tuple[list[dict], dict[str, bytes], str]:
    files = [path / n for n in ("plan_PRIVATE.json", "takes_PRIVATE.jsonl",
                                "summary.json", "provenance_PRIVATE.json")]
    raw = [p.read_bytes() for p in files]
    plan, summary, provenance = (json.loads(raw[i]) for i in (0, 2, 3))
    if expected_plan is None:
        seeds = {r["seed"] for r in plan if r["case"] == "fuel"}
        if len(seeds) != 1:
            raise ValueError("INVALID_TRIAL_PLAN")
        expected_plan = trial_plan(next(iter(seeds)))
    if plan != expected_plan:
        raise ValueError("INVALID_TRIAL_PLAN")
    takes = [json.loads(line) for line in raw[1].decode("utf-8").splitlines() if line.strip()]
    if [r["id"] for r in takes] != [r["id"] for r in plan]:
        raise ValueError("INCOMPLETE_OR_REORDERED_TAKES")
    if any(r["status"] not in ("generated", "failed") for r in takes):
        raise ValueError("INVALID_TAKE_STATUS")
    if (summary.get("planned") != len(plan)
            or summary.get("generated") != sum(t["status"] == "generated" for t in takes)
            or summary.get("failed") != sum(t["status"] == "failed" for t in takes)
            or summary.get("release_ready") is not False):
        raise ValueError("INCOMPLETE_RUN")
    if not provenance.get("snapshot_sha256") or not provenance.get("reference_sha256"):
        raise ValueError("MISSING_PROVENANCE")
    records, audio = [], {}
    for p, t in zip(plan, takes):
        wav = path / (p["id"] + ".wav")
        if t["status"] == "generated":
            data = wav.read_bytes()
            if hashlib.sha256(data).hexdigest() != t["sha256"]:
                raise ValueError("WAV_DIGEST_MISMATCH")
            if any(type(t[k]) not in (int, float) or not math.isfinite(t[k]) or t[k] <= 0
                   for k in ("seconds", "elapsed_seconds", "rtf")):
                raise ValueError("INVALID_TAKE_TIMING")
            audio[p["id"]] = data
        elif wav.exists():
            raise ValueError("FAILED_TAKE_HAS_AUDIO")
        records.append({**p, **t})
    if any(p.read_bytes() != b for p, b in zip(files, raw)):
        raise ValueError("RUN_CHANGED")
    h = hashlib.sha256()
    for data in raw:
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return records, audio, h.hexdigest()


def read_voicy_comparison(stock: Path, candidate: Path) -> tuple[list[dict], dict[str, bytes], str]:
    from audiobook.stress_voicy import ADAPTER_PIN, ADAPTER_SHA256, BASE_PIN

    old, stock_audio, stock_digest = read_run(stock)
    seed = next(r["seed"] for r in old if r["case"] == "fuel")
    expected = [r for r in trial_plan(seed) if r["condition"] == "acute"]
    new, candidate_audio, candidate_digest = read_run(candidate, expected_plan=expected)
    base = json.loads((stock / "provenance_PRIVATE.json").read_text(encoding="utf-8"))
    adapted = json.loads((candidate / "provenance_PRIVATE.json").read_text(encoding="utf-8"))
    if (adapted.get("baseline_run_digest") != stock_digest
            or adapted.get("variant") != "voicy_v3"
            or adapted.get("adapter_revision") != ADAPTER_PIN
            or adapted.get("adapter_sha256") != ADAPTER_SHA256
            or adapted.get("base_revision") != BASE_PIN
            or adapted.get("matrices") != 196
            or adapted.get("checkpoint_written") is not False
            or any(adapted.get(k) != v for k, v in base.items() if k != "limitation")):
        raise ValueError("COMPARISON_PROVENANCE_MISMATCH")
    plain = [r for r in old if r["condition"] == "plain"]
    records = plain + new
    ids = {r["id"] for r in plain}
    audio = {**{k: v for k, v in stock_audio.items() if k in ids}, **candidate_audio}
    digest = hashlib.sha256((stock_digest + candidate_digest).encode("ascii")).hexdigest()
    return records, audio, digest


def make_key(records: list[dict], seed: int) -> list[dict]:
    generated = [r for r in records if r["status"] == "generated"]
    random.Random(seed).shuffle(generated)
    return [dict(clip=f"clip-{i:03d}.wav", **r) for i, r in enumerate(generated, 1)]


def public_rows(key: list[dict]) -> list[dict]:
    return [dict(clip=r["clip"], sentence=r["text"].replace(ACUTE, ""),
                 target=r["expected_word"], lexical="", heard_vowel="", naturalness="")
            for r in key]


def evaluate(records: list[dict], key: list[dict], ratings: list[dict]) -> dict:
    expected = {r["clip"]: r for r in public_rows(key)}
    by_id = {}
    for r in ratings:
        clip = r["clip"]
        if clip in by_id or clip not in expected:
            raise ValueError("RATING_IDENTITY")
        if (r["sentence"], r["target"]) != (expected[clip]["sentence"], expected[clip]["target"]):
            raise ValueError("RATING_IDENTITY")
        if r["lexical"] not in ("ok", "error", "uncertain"):
            raise ValueError("INVALID_LEXICAL_LABEL")
        n = sum(c.lower() in VOWELS for c in r["target"])
        if r["heard_vowel"] not in {"unknown", *(str(i) for i in range(1, n + 1))}:
            raise ValueError("INVALID_HEARD_VOWEL")
        if r["lexical"] != "ok" and r["heard_vowel"] != "unknown":
            raise ValueError("STRESS_LABEL_WITH_LEXICAL_ERROR")
        if r["naturalness"] not in ("good", "poor", "uncertain"):
            raise ValueError("INVALID_NATURALNESS_LABEL")
        by_id[clip] = r
    if by_id.keys() != expected.keys():
        raise ValueError("MISSING_RATINGS")
    outcomes = {r["id"]: "generation_failed" for r in records if r["status"] == "failed"}
    quality = {"plain": Counter(), "acute": Counter()}
    for r in key:
        rating = by_id[r["clip"]]
        expected_vowel = sum(c.lower() in VOWELS for c in r["expected_word"][:r["expected_index"] + 1])
        if rating["lexical"] == "error":
            outcome = "lexical_error"
        elif rating["lexical"] != "ok" or rating["heard_vowel"] == "unknown":
            outcome = "uncertain"
        else:
            outcome = "correct" if int(rating["heard_vowel"]) == expected_vowel else "wrong_stress"
        outcomes[r["id"]] = outcome
        quality[r["condition"]][rating["naturalness"]] += 1
    counts = {"plain": Counter(), "acute": Counter()}
    pairs = {}
    for r in records:
        outcome = outcomes[r["id"]]
        counts[r["condition"]][outcome] += 1
        pairs.setdefault(r["case"], {})[r["condition"]] = outcome
    changes = Counter()
    for p in pairs.values():
        a, b = p["plain"], p["acute"]
        if a not in ("correct", "wrong_stress") or b not in ("correct", "wrong_stress"):
            changes["not_comparable"] += 1
        elif a == b:
            changes["both_" + a] += 1
        elif b == "correct":
            changes["improved"] += 1
        else:
            changes["regressed"] += 1
    return dict(planned=len(records), rated=len(key),
                outcomes={k: dict(v) for k, v in counts.items()},
                naturalness={k: dict(v) for k, v in quality.items()},
                paired_changes=dict(changes), release_ready=False,
                limitation="Small synthetic sample; human ratings not independently authenticated by this tool.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="mode", required=True)
    for mode in ("prepare", "score"):
        q = subs.add_parser(mode)
        q.add_argument("--run", type=Path, required=True)
        q.add_argument("--review", type=Path, required=True)
        q.add_argument("--voicy-run", type=Path, help="Compare stock plain with the Voicy marked arm")
        if mode == "prepare":
            q.add_argument("--shuffle-seed", type=int, required=True)
        else:
            q.add_argument("--ratings", type=Path, required=True)
            q.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    records, audio, digest = (read_voicy_comparison(a.run, a.voicy_run)
                              if a.voicy_run is not None else read_run(a.run))
    if a.mode == "prepare":
        key = make_key(records, a.shuffle_seed)
        a.review.mkdir(parents=True, exist_ok=False, mode=0o700)
        blind = a.review / "blind"
        blind.mkdir(mode=0o700)
        for r in key:
            (blind / r["clip"]).write_bytes(audio[r["id"]])
        with (blind / "ratings.tsv").open("x", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
            writer.writeheader()
            writer.writerows(public_rows(key))
        (a.review / "key_PRIVATE.json").write_text(json.dumps(
            dict(run_digest=digest, seed=a.shuffle_seed, key=key), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(dict(clips=len(key), generation_failed=len(records)-len(key), stress_rated=0)))
    else:
        saved = json.loads((a.review / "key_PRIVATE.json").read_text(encoding="utf-8"))
        key = make_key(records, saved["seed"])
        if saved["run_digest"] != digest or saved["key"] != key:
            raise ValueError("REVIEW_KEY_MISMATCH")
        if any(sha256(a.review / "blind" / r["clip"]) != r["sha256"] for r in key):
            raise ValueError("REVIEW_AUDIO_CHANGED")
        with a.ratings.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise ValueError("RATING_SCHEMA")
            summary = evaluate(records, key, list(reader))
        if a.voicy_run is not None:
            summary["comparison"] = {"plain": "stock Qwen", "acute": "Voicy v3"}
        with a.out.open("x", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
