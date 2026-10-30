"""Identical chunks rendered once, reused everywhere (no models)."""
import json

import numpy as np
import soundfile as sf

from audiobook import reuse


def _wav(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(p), np.full(240, v, dtype=np.float32), 24000, subtype="FLOAT")


def _sec(out, name, rows):
    d = out / "sections" / name
    (d / "chunks").mkdir(parents=True, exist_ok=True)
    (d / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return d


def test_before_render_copies_cross_section_and_parks_duplicates(tmp_path):
    out = tmp_path / "out"
    a = _sec(out, "01_a", [{"id": "0001", "hash": "H", "status": "done", "seed": 7, "takes": 3,
                            "take_base": 5, "cer": 0.0}])
    _wav(a / "chunks" / "0001.wav", 0.5)
    b = out / "sections" / "02_b"
    rows = [{"id": "0001", "hash": "H", "status": "pending"},
            {"id": "0002", "hash": "X", "status": "pending"},
            {"id": "0003", "hash": "X", "status": "pending"},
            {"id": "0004", "hash": "Y", "status": "pending", "locked": True}]
    _sec(out, "02_b", rows)
    copied, parked = reuse.before_render(b, rows, out)
    assert (copied, parked) == (1, 1)
    assert rows[0]["status"] == "done" and rows[0]["reused_from"] == "01_a/0001"
    assert rows[0]["seed"] == 7 and rows[0]["takes"] == 3          # qc will not re-take it
    assert (b / "chunks" / "0001.wav").read_bytes() == (a / "chunks" / "0001.wav").read_bytes()
    assert rows[1]["status"] == "pending" and rows[2]["status"] == "dup"
    assert rows[3]["status"] == "pending"                           # locked untouched
    from audiobook.synth import needs_render
    assert not needs_render(rows[2], False)                         # dup never rendered


def test_after_render_fills_dups_or_returns_them(tmp_path):
    out = tmp_path / "out"
    rows = [{"id": "0001", "hash": "X", "status": "done", "seed": 3},
            {"id": "0002", "hash": "X", "status": "dup"},
            {"id": "0003", "hash": "Z", "status": "dup"}]
    d = _sec(out, "01_a", rows)
    _wav(d / "chunks" / "0001.wav", 0.2)
    assert reuse.after_render(d, rows) == 1
    assert rows[1]["status"] == "done" and rows[1]["reused_from"] == "01_a/0001" and rows[1]["seed"] == 3
    assert rows[2]["status"] == "pending"                           # its leader failed


def test_resync_follows_leader_new_take_and_status(tmp_path):
    out = tmp_path / "out"
    a_rows = [{"id": "0001", "hash": "H", "status": "done", "seed": 99, "takes": 3}]
    a = _sec(out, "01_a", a_rows)
    _wav(a / "chunks" / "0001.wav", 0.9)                            # leader's better take
    b_rows = [{"id": "0005", "hash": "H", "status": "qc_fail", "seed": 7, "reused_from": "01_a/0001"},
              {"id": "0006", "hash": "H", "status": "done", "seed": 7, "reused_from": "01_a/0001",
               "locked": True}]
    b = _sec(out, "02_b", b_rows)
    _wav(b / "chunks" / "0005.wav", 0.1)
    _wav(b / "chunks" / "0006.wav", 0.1)
    assert reuse.resync(b, b_rows, out) == 1
    assert b_rows[0]["seed"] == 99 and b_rows[0]["status"] == "done"
    assert (b / "chunks" / "0005.wav").read_bytes() == (a / "chunks" / "0001.wav").read_bytes()
    assert b_rows[1]["seed"] == 7                                   # accepted by ear: stands alone
    assert reuse.resync(b, b_rows, out) == 0                        # idempotent


def test_resync_drops_link_when_leader_changed(tmp_path):
    out = tmp_path / "out"
    a = _sec(out, "01_a", [{"id": "0001", "hash": "NEW", "status": "done"}])
    _wav(a / "chunks" / "0001.wav", 0.3)
    rows = [{"id": "0001", "hash": "H", "status": "done", "reused_from": "01_a/0001"}]
    b = _sec(out, "02_b", rows)
    _wav(b / "chunks" / "0001.wav", 0.1)
    reuse.resync(b, rows, out)
    assert "reused_from" not in rows[0]


def test_config_enables_reuse_and_carry():
    from pathlib import Path
    import yaml
    from audiobook.chunker import _CARRY
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert reuse.enabled(cfg) and "reused_from" in _CARRY
