"""Single-stream prosody actuator probe: dry-run only, no model calls.

Separate from failed automatic boundary discovery. An independently reviewed
comma can be probed with one stronger punctuation mark, never a waveform edit.
This is an experimental input pair, not a prescription for production text.
"""
from __future__ import annotations

import hashlib

from audiobook.rhythm_syntax import protected_commas

POLICY = "single-stream-comma-semicolon-v1"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan(row: dict, annotation: dict, offset: int, config: dict, table: dict) -> dict:
    """Require exact positive boundary identity and prove the one-character edit.

    Both full inputs pass the existing preparation with the same carrier,
    dictionary, open-end flag and sentinel. Any collateral edit is rejected.
    No production state or hash is modified. The caller must independently
    verify manifest freshness, annotation provenance and pilot scope.
    """
    from audiobook import synth

    if row.get("locked"):
        return {"status": "locked"}
    if config.get("pauses_ms", {}).get("enum_pause_ms"):
        raise ValueError("LEGACY_ENUM_FORBIDDEN")
    if (annotation["id"] != row["id"] or annotation["hash"] != row["hash"]
            or annotation["split"] not in ("development", "heldout")
            or type(offset) is not int or offset not in annotation["positive"]
            or offset in annotation["negative"]):
        raise ValueError("BOUNDARY_IDENTITY_MISMATCH")
    raw = row["text"]
    if (not 0 < offset < len(raw)-1 or raw[offset] != ","
            or not raw[offset+1].isspace()
            or offset in protected_commas(raw)
            or not raw[:offset].strip() or not raw[offset+1:].strip()):
        raise ValueError("UNSAFE_BOUNDARY")
    alternate = raw[:offset] + ";" + raw[offset+1:]
    sentinel = config["model"].get("sentinel", "")
    open_end = row.get("open_end", False)
    body, _ = synth.prepare_synth_text(raw, config, table, sentinel, None, open_end)
    alt_body, _ = synth.prepare_synth_text(alternate, config, table, sentinel, None, open_end)
    baseline, carrier = synth.prepare_synth_text(
        raw, config, table, sentinel, synth.row_leadin(row), open_end)
    candidate, alt_carrier = synth.prepare_synth_text(
        alternate, config, table, sentinel, carrier, open_end)
    if (carrier != alt_carrier or not baseline.endswith(body)
            or not candidate.endswith(alt_body)
            or len(body) != len(alt_body)
            or len(baseline) != len(candidate)
            or baseline[:-len(body)] != candidate[:-len(alt_body)]):
        return {"status": "prepared_alignment_unproven"}
    differences = [i for i, (a, b) in enumerate(zip(body, alt_body)) if a != b]
    if (len(differences) != 1 or body[differences[0]] != ","
            or alt_body[differences[0]] != ";"):
        return {"status": "prepared_collateral_change"}
    if (body.count(",") != raw.count(",")
            or body[:differences[0]].count(",") != raw[:offset].count(",")):
        return {"status": "prepared_alignment_unproven"}
    position = len(baseline)-len(body)+differences[0]
    if candidate != baseline[:position] + ";" + baseline[position+1:]:
        return {"status": "prepared_collateral_change"}
    seed = row.get("seed_override")
    if seed is None:
        seed = synth.seed_for_chunk(row["hash"])
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("INVALID_SEED")
    return {"status": "planned", "policy": POLICY, "chunk_id": row["id"],
            "chunk_hash": row["hash"], "source_sha256": digest(raw),
            "source_offset": offset, "prepared_offset": position,
            "split": annotation["split"], "seed": seed, "carrier": carrier,
            "baseline": baseline, "candidate": candidate,
            "baseline_sha256": digest(baseline), "candidate_sha256": digest(candidate)}
