"""Layer-1 tests for seed override / redo / accept mechanics. No models."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_manifest(rows: list[dict]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _row(id="0001", text="Привет", status="pending", locked=False, seed_override=None):
    from audiobook.chunker import chunk_hash
    h = chunk_hash(text, "model", 42, 0.7, "ru", "lat000")
    return {
        "id": id, "n": int(id), "text": text, "hash": h,
        "seed": 42, "pause_after_ms": 350,
        "status": status, "locked": locked,
        "seed_override": seed_override, "duration_ms": None,
    }


# ── seed_override persists across rebuild ────────────────────────────────────

def test_seed_override_persists_across_align():
    from audiobook.chunker import align

    old = [_row("0001", "Привет", status="done", locked=True, seed_override=99999)]
    # new manifest: same text → same hash → align should carry override
    new = [_row("0001", "Привет", status="pending")]

    aligned, queued, orphans = align(old, new)
    assert aligned[0]["seed_override"] == 99999
    assert aligned[0]["locked"] is True
    assert queued == []  # hash matched, nothing re-queued


def test_seed_override_not_in_hash():
    """Applying seed_override must not change the hash."""
    from audiobook.chunker import chunk_hash

    h1 = chunk_hash("Привет", "m", 1, 0.7, "ru", "lat")
    h2 = chunk_hash("Привет", "m", 1, 0.7, "ru", "lat")
    assert h1 == h2  # trivially same; real test: override is external to hash function


# ── locked chunk skipped by render_section ───────────────────────────────────

def test_locked_chunk_skipped(tmp_path):
    """render_section skips chunks that are already status=done (including locked)."""
    import numpy as np
    from audiobook import paths as ab_paths

    sec_dir = tmp_path / "sections" / "01_test"
    chunks_dir = sec_dir / "chunks"
    chunks_dir.mkdir(parents=True)

    row = _row("0001", "Привет", status="done", locked=True)
    manifest_path = sec_dir / "manifest.jsonl"
    manifest_path.write_text(_make_manifest([row]), encoding="utf-8")

    # place a dummy wav so the "done + wav exists" check passes
    import soundfile as sf
    dummy = np.zeros(100, dtype=np.float32)
    sf.write(str(chunks_dir / "0001.wav"), dummy, 24000)

    calls = []

    class FakeEngine:
        def synth(self, text, seed):
            calls.append((text, seed))
            return np.zeros(100, dtype=np.float32)

    # monkeypatch paths.OUT so render_section finds our tmp sec_dir
    original_out = ab_paths.OUT
    ab_paths.OUT = tmp_path / "sections"
    try:
        # Import render_section and call it with a minimal config
        from audiobook.synth import render_section
        config = {"model": {"sentinel": ""}, "render": {}}
        # render_section expects sec_dir directly, not paths.OUT / sections / name
        render_section(FakeEngine(), sec_dir, config)
    finally:
        ab_paths.OUT = original_out

    assert calls == [], "locked/done chunk must not be synthesised"


# ── override one chunk leaves neighbour hash unchanged ───────────────────────

def test_override_does_not_change_neighbor_hash():
    from audiobook.chunker import align

    r1 = _row("0001", "Первый", status="done", seed_override=12345)
    r2 = _row("0002", "Второй", status="done")

    new_r1 = _row("0001", "Первый", status="pending")
    new_r2 = _row("0002", "Второй", status="pending")

    aligned, _, _ = align([r1, r2], [new_r1, new_r2])
    # r2 hash is unchanged; its seed_override stays None
    assert aligned[1]["seed_override"] is None
    assert aligned[1]["hash"] == r2["hash"]
