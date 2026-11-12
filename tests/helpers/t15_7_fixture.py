"""T15-7 baseline: capture existing TTS inputs for all SUs (no synthesis).

S2 output: out/t15_7/baseline/baseline.json  (ignored by git, never staged)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path("out/t15_7/baseline/baseline.json")

_CANONICAL_KW = dict(sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, **_CANONICAL_KW).encode("utf-8")


def _load_config() -> dict:
    import yaml
    from audiobook import paths
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _p1_guard(path: str) -> None:
    """Abort if path is not git-ignored or is tracked."""
    r1 = subprocess.run(["git", "check-ignore", "-q", "--", path], capture_output=True)
    if r1.returncode != 0:
        raise RuntimeError(f"P1 FAIL: {path} not git-ignored")
    r2 = subprocess.run(["git", "ls-files", "--error-unmatch", "--", path],
                        capture_output=True)
    if r2.returncode == 0:
        raise RuntimeError(f"P1 FAIL: {path} is tracked in git")


def _capture_section(section: str, config: dict, table: dict, sentinel: str) -> list[dict]:
    from audiobook import leadin as leadin_mod
    from audiobook import paths
    from audiobook.synth import prepare_synth_text, row_leadin

    rows = _read_manifest(paths.OUT / "sections" / section / "manifest.jsonl")
    records: list[dict] = []
    for row in rows:
        phrase_arg = row_leadin(row)
        open_end = row.get("open_end", False)
        final, phrase = prepare_synth_text(
            row["text"], config, table, sentinel, phrase_arg, open_end
        )
        final_sha256 = _sha256(final)
        if phrase is None:
            phrase_sha256 = None
        else:
            phrase_sha256 = _sha256(phrase)  # "" yields e3b0c44…, distinct from None
        records.append({
            "section": section,
            "chunk_id": row["id"],
            "fragment": None,
            "final_sha256": final_sha256,
            "phrase_sha256": phrase_sha256,
            "stored_hash": row["hash"],
            "analytic": {
                "n": row["n"],
                "id": row["id"],
                "text_sha256": _sha256(row["text"]),
                "pause_after_ms": row.get("pause_after_ms"),
                "open_end": row.get("open_end", False),
                "leadin": row.get("leadin"),
            },
        })
    return records


def _capture_ensure(config: dict, section: str) -> str:
    from audiobook.synth import ensure_manifest_current
    try:
        ensure_manifest_current(config, section)
        return "ok"
    except SystemExit:
        return "SystemExit"
    except Exception as exc:
        return type(exc).__name__


def _capture_impact(config: dict, section: str) -> dict | None:
    from audiobook.impact import section_impact
    d = section_impact(config, section)
    if d is None:
        return None
    return {
        "lost": len(d["lost"]),
        "chars": d["chars"],
        "locked_count": len(d["locked"]),
        "rendered": d["rendered"],
    }


def _build(config: dict) -> dict:
    from audiobook import paths
    from audiobook.pronounce import load_table
    table = load_table()
    sentinel: str = config["model"].get("sentinel", "")
    sections = sorted(
        p.parent.name for p in (paths.OUT / "sections").glob("*/manifest.jsonl")
    )
    su_records: list[dict] = []
    ensure_results: dict[str, str] = {}
    impact_results: dict[str, dict | None] = {}
    for sec in sections:
        su_records.extend(_capture_section(sec, config, table, sentinel))
        ensure_results[sec] = _capture_ensure(config, sec)
        impact_results[sec] = _capture_impact(config, sec)
    return {
        "version": "t15-7-baseline/1",
        "sections": sections,
        "su_records": su_records,
        "ensure_manifest_current": ensure_results,
        "impact": impact_results,
    }


def generate(config: dict | None = None) -> tuple[str, dict]:
    """Generate baseline and save to S2 path. Returns (D, counts)."""
    if config is None:
        config = _load_config()
    _p1_guard(str(BASELINE_PATH))
    baseline = _build(config)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical(baseline)
    tmp = BASELINE_PATH.with_suffix(".json.tmp")
    tmp.write_bytes(data)
    tmp.replace(BASELINE_PATH)
    D = hashlib.sha256(data).hexdigest()
    counts = {
        "sections": len(baseline["sections"]),
        "su_count": len(baseline["su_records"]),
    }
    return D, counts


def check(config: dict | None = None) -> tuple[bool, str, str]:
    """Compare fresh computation to stored baseline. Returns (match, stored_D, fresh_D)."""
    if config is None:
        config = _load_config()
    if not BASELINE_PATH.exists():
        return False, "", ""
    stored_bytes = BASELINE_PATH.read_bytes()
    stored_D = hashlib.sha256(stored_bytes).hexdigest()
    fresh = _build(config)
    fresh_bytes = _canonical(fresh)
    fresh_D = hashlib.sha256(fresh_bytes).hexdigest()
    return stored_D == fresh_D, stored_D, fresh_D


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["generate", "check"])
    args = p.parse_args(argv)
    cfg = _load_config()
    if args.mode == "check":
        match, stored_D, fresh_D = check(cfg)
        print(f"BASELINE_CHECK: {'PASS' if match else 'FAIL'}")
        print(f"STORED_D: {stored_D}")
        print(f"FRESH_D:  {fresh_D}")
        bl = json.loads(BASELINE_PATH.read_bytes()) if BASELINE_PATH.exists() else {}
        print(f"SU_COUNT: {len(bl.get('su_records', []))}")
        return 0 if match else 1
    else:
        D, counts = generate(cfg)
        print(f"BASELINE_GENERATED: sections={counts['sections']} su_count={counts['su_count']}")
        print(f"D: {D}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
