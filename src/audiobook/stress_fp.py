"""Shared parameters and generation management for stress analysis (T15 / T17).

Public API consumed by T17 (stress-sheet):
  INVENTORY_ALGO_VERSION  — bump when output format or classification logic changes
  stress_params(cfg)      — extract typed stress config from full config dict
  load_current(stress_dir) — read current.json, verify SHA, return summary dict
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Bump when: paragraph separator logic changes, scoring changes, new risk
# categories added, TSV columns added/removed, summary.json schema changes.
# See CLAUDE.md → "INVENTORY_ALGO_VERSION bump rules".
INVENTORY_ALGO_VERSION: int = 2


def stress_params(cfg: dict) -> dict:
    """Extract stress analysis parameters from full config dict.

    Returns {"top_n": int, "paragraph_ms": int}.
    """
    s = (cfg or {}).get("stress") or {}
    pauses = (cfg or {}).get("pauses_ms") or {}
    return {
        "top_n": int(s.get("top_n", 300)),
        "paragraph_ms": int(pauses.get("paragraph", 900)),
    }


def load_current(stress_dir: Path) -> dict | None:
    """Return current inventory summary dict, or None if none published.

    Reads stress_dir/inventory/current.json, finds gen/<gen_id>/summary.json,
    verifies its SHA-256 against stored value.  Raises RuntimeError on mismatch.
    """
    cur = stress_dir / "inventory" / "current.json"
    if not cur.exists():
        return None
    meta = json.loads(cur.read_text(encoding="utf-8"))
    gen_id = meta.get("gen_id", "")
    gen_dir = stress_dir / "gen" / gen_id
    summary_path = gen_dir / "summary.json"
    if not summary_path.exists():
        return None
    actual_sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    expected_sha = meta.get("summary_sha256", "")
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"stress inventory: summary.json SHA mismatch for gen {gen_id!r}\n"
            f"  expected: {expected_sha}\n"
            f"  actual:   {actual_sha}"
        )
    return json.loads(summary_path.read_text(encoding="utf-8"))
