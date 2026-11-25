"""ALG-02: bounded, occurrence-specific uppercase stress trial (NOT production).

Use a frozen map and exact positional linkage, preserve the actual prepared
baseline and change just one vowel. No global pronounce rules, no cache writes,
no new seed search. An experiment is not an approved pronunciation policy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audiobook.stress_consensus import WORD, book_rows
from audiobook.stress_map import canonical, digest, read_jsonl, valid_stress
from audiobook.stress_map_link import link

POLICY = "uppercase-occurrence-pilot-v1"
# Historical negative result; conservative exclusion for this pilot only.
EXCLUDED_FORMS = frozenset({"тебя"})
MAX_TARGETS = 8
CH1 = "08_glava_1_zver_vnutri_nas_instinkty_eto_ne"


def candidate(raw: str, body: str, baseline: str, occurrence: dict) -> dict:
    """Only map a source span if all Cyrillic tokens align exactly in order.

    body is the same preparation without carrier. baseline includes the
    carrier. Require body to be an exact suffix; never change carrier words.
    If normal respelling/ё restoration prevents proof, leave baseline alone.
    """
    start, end = occurrence["chunk_start"], occurrence["chunk_end"]
    word, index = occurrence["word"], occurrence["stress_index"]
    if (type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(raw) or raw[start:end] != word):
        raise ValueError("SOURCE_SPAN_MISMATCH")
    if occurrence["status"] not in ("auto", "confirmed"):
        return {"status": "unresolved_stress"}
    if not valid_stress(word, index):
        raise ValueError("INVALID_STRESS_INDEX")
    if word.lower() in EXCLUDED_FORMS:
        return {"status": "historical_negative_form"}
    if not word.islower() or word[index] == "ё":
        return {"status": "unsupported_case_or_yo"}
    source = list(WORD.finditer(raw))
    target = [i for i, m in enumerate(source) if (m.start(), m.end()) == (start, end)]
    if len(target) != 1:
        return {"status": "not_whole_word"}
    # Exclude compounds and adjacent digits/Latin letters/underscore.
    if (start and (raw[start - 1].isalnum() or raw[start - 1] in "_-‑–"))
            or (end < len(raw) and (raw[end].isalnum() or raw[end] in "_-‑–")):
        return {"status": "compound_or_mixed"}
    words = list(WORD.finditer(body))
    if ([m.group() for m in source] != [m.group() for m in words]
            or not baseline.endswith(body)):
        return {"status": "prepared_alignment_unproven"}
    pos = len(baseline) - len(body) + words[target[0]].start() + index
    if baseline[pos] != word[index]:
        raise ValueError("PREPARED_SPAN_MISMATCH")
    transformed = baseline[:pos] + baseline[pos].upper() + baseline[pos + 1:]
    if transformed == baseline or len(transformed) != len(baseline):
        raise ValueError("INVALID_TRANSFORMATION")
    return {"status": "planned", "policy": POLICY, "baseline": baseline,
            "candidate": transformed, "prepared_offset": pos,
            "baseline_sha256": digest(baseline.encode("utf-8")),
            "candidate_sha256": digest(transformed.encode("utf-8"))}


def plan(row: dict, occurrence: dict, config: dict, table: dict) -> dict:
    from audiobook import synth

    if row.get("locked"):
        return {"status": "locked"}
    sentinel = config["model"].get("sentinel", "")
    raw = row["text"]
    body, _ = synth.prepare_synth_text(raw, config, table, sentinel, None,
                                     row.get("open_end", False))
    baseline, carrier = synth.prepare_synth_text(
        raw, config, table, sentinel, synth.row_leadin(row), row.get("open_end", False))
    result = candidate(raw, body, baseline, occurrence)
    if result["status"] == "planned":
        result.update(carrier=carrier, seed=synth.seed_for_chunk(row["hash"]),
                      chunk_id=row["id"], chunk_hash=row["hash"],
                      occurrence=occurrence)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--book-text-dir", type=Path, required=True)
    p.add_argument("--map-dir", type=Path, required=True)
    p.add_argument("--map-sha256", required=True)
    p.add_argument("--targets", type=Path, required=True,
                   help="Private JSON list: chunk_id, chunk_start, split=development/heldout")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--execute", action="store_true", help="explicit bounded paired TTS")
    args = p.parse_args()

    from audiobook import paths, synth, chunker
    from audiobook.__main__ import load_config
    from audiobook.pronounce import load_table
    from audiobook.jobqueue import heavy_command_lock
    from audiobook.reviewed_stage import generation_identity, file_digest

    paths.apply_env_defaults()
    # Main config only; run in the verified historical CH1 environment.
    import os
    if os.environ.get("AUDIOBOOK_CONFIG"):
        raise ValueError("HISTORICAL_MAIN_CONFIG_REQUIRED")
    if args.book_text_dir.resolve() != paths.TEXT.resolve():
        raise ValueError("TEXT_ROOT_MISMATCH")
    with heavy_command_lock("stress-uppercase-pilot"):
        config = chunker.section_config(load_config(), CH1)
        table = load_table()
        synth.ensure_manifest_current(config, CH1)
        manifest_path = paths.OUT / "sections" / CH1 / "manifest.jsonl"
        manifest_bytes = manifest_path.read_bytes()
        manifest = read_jsonl(manifest_bytes)
        by_id = {r["id"]: r for r in manifest}
        data = (args.map_dir / "stress_map.jsonl").read_bytes()
        meta = json.loads((args.map_dir / "manifest_PRIVATE.json").read_bytes())
        rows, hashes = book_rows(args.book_text_dir)
        if (digest(data) != args.map_sha256 or meta.get("map_sha256") != args.map_sha256
                or meta.get("source_sha256") != {k.name: v for k, v in hashes.items()}):
            raise ValueError("STALE_OR_UNPINNED_MAP")
        queue, _, _ = link(rows, read_jsonl(data), {CH1: manifest})
        occurrences = {(g["chunk_id"], r["chunk_start"]): r
                       for g in queue for r in g["occurrences"]}
        targets = json.loads(args.targets.read_bytes())
        if not isinstance(targets, list) or not 1 <= len(targets) <= MAX_TARGETS:
            raise ValueError("INVALID_TARGET_COUNT")
        trials = []
        seen = set()
        for t in targets:
            key = (t["chunk_id"], t["chunk_start"])
            if (key[0] in seen or key not in occurrences
                    or t["split"] not in ("development", "heldout")):
                raise ValueError("INVALID_OR_DUPLICATE_TARGET")
            seen.add(key[0])
            r = plan(by_id[key[0]], occurrences[key], config, table)
            trials.append(dict(r, target=t))
        usable = [r for r in trials if r["status"] == "planned"]
        args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
        plan_bytes = canonical(dict(policy=POLICY, map_sha256=args.map_sha256,
                                   manifest_sha256=digest(manifest_bytes), trials=trials))
        (args.out / "plan_PRIVATE.json").write_bytes(plan_bytes)
        print(json.dumps({"requested": len(targets), "planned": len(usable),
                          "execute": args.execute}))
        if not args.execute or not usable:
            return 0
        # No retries. Fixed seed per pair, same worker and carrier.
        import numpy as np
        import soundfile as sf
        from audiobook.worker import TimeoutSynth
        from time import perf_counter

        generation = generation_identity(config)
        wcfg = synth.worker_config(config, 1)
        wcfg["device"] = "cpu"
        timeout = config.get("render", {}).get("chunk_timeout_s", 600)
        with (args.out / "receipts_PRIVATE.jsonl").open("x", encoding="utf-8") as log:
            with TimeoutSynth(wcfg, timeout) as engine:
                for r in usable:
                    for arm in ("baseline", "candidate"):
                        t0 = perf_counter()
                        wav = engine.synth(r[arm], r["seed"], leadin=r["carrier"])
                        receipt = dict(chunk_id=r["chunk_id"], arm=arm, seed=r["seed"],
                                       input_sha256=r[arm + "_sha256"], carrier=r["carrier"],
                                       generation=generation, elapsed_s=perf_counter()-t0,
                                       status="failed", plan_sha256=digest(plan_bytes))
                        if wav is not None and len(wav) and np.isfinite(wav).all():
                            out = args.out / f"{r['chunk_id']}_{arm}.wav"
                            sf.write(str(out), wav, 24000, subtype="FLOAT")
                            receipt.update(status="generated", wav=out.name,
                                           wav_sha256=file_digest(out), samples=len(wav))
                        log.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
                        log.flush()
        if manifest_path.read_bytes() != manifest_bytes:
            raise ValueError("MANIFEST_CHANGED")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
