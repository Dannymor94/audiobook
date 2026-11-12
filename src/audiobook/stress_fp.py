"""Shared parameters and generation management for stress analysis (T15 / T17).

Public API consumed by T17 (stress-sheet):
  INVENTORY_ALGO_VERSION  — bump when output format or classification logic changes
  stress_params(cfg)      — extract typed stress config from full config dict
  load_current(stress_dir) — read current.json, verify SHA, return summary dict

T15-7.3 additions (re-exported from wordprov):
  source_fp   — §5 SHA-256 of canonical source units representation
  manifest_fp — §5 SHA-256 of canonical analytic manifest fields
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Bump when: paragraph separator logic changes, scoring changes, new risk
# categories added, TSV columns added/removed, summary.json schema changes.
# See CLAUDE.md → "INVENTORY_ALGO_VERSION bump rules".
# v4: exact atom provenance; multi-unit joins use adjoining source atoms.
INVENTORY_ALGO_VERSION: int = 4


def stress_params(cfg: dict) -> dict:
    """Return full stress config subtree plus derived pauses parameters.

    All keys under cfg['stress'] are included automatically; new nested keys
    are picked up without code changes.  paragraph_ms is always derived from
    cfg['pauses_ms']['paragraph'], not from the stress subtree.
    """
    s = dict((cfg or {}).get("stress") or {})
    pauses = (cfg or {}).get("pauses_ms") or {}
    s.setdefault("top_n", 300)
    s["paragraph_ms"] = int(pauses.get("paragraph", 900))
    return s


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


# T15-7.3: fingerprint functions — implemented in wordprov, re-exported here.
from audiobook.wordprov import source_fp, manifest_fp  # noqa: E402, F401
