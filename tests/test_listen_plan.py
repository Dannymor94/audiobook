"""listen-plan: picks, random fill, output in probe format (no ffmpeg)."""
import json

import numpy as np

from audiobook import listen


def test_pick_intro_and_suspects():
    rows = [{"id": "0001", "hash": "a" * 40, "text": "Глава."},
            {"id": "0002", "hash": "b" * 40, "text": "x", "flag_words": [["тебья", 1.0, 0.1, "conf"]]},
            {"id": "0003", "hash": "c" * 40, "text": "y"}]
    index = {"0001": {"start_ms": 1000, "dur_ms": 900}, "0002": {"start_ms": 40000, "dur_ms": 500},
             "0003": {"start_ms": 50000, "dur_ms": 500}}
    got = listen.pick(rows, index, intro_ms=30000)
    assert [(r["id"], t) for r, t in got] == [("0001", ["начало"]), ("0002", ["подозр: тебья"])]


def test_add_random_deterministic_and_skips_short_and_picked():
    pool = [("s", {"id": str(i), "hash": f"h{i}", "text": "т" * 50}) for i in range(10)]
    pool.append(("s", {"id": "short", "hash": "hs", "text": "кор"}))
    picked = [("s", pool[0][1], ["начало"])]
    a = listen.add_random(picked, pool, 3)
    b = listen.add_random(picked, pool, 3)
    assert a == b and len(a) == 4
    assert all(r["hash"] not in ("h0", "hs") for _s, r, _t in a[1:])


def test_run_writes_probe_format(tmp_path, monkeypatch):
    from audiobook import assemble, review
    out = tmp_path / "out"
    sec = out / "sections" / "01_a"
    sec.mkdir(parents=True)
    rows = [{"id": "0001", "n": 1, "hash": "a" * 40, "seed": 1, "text": "Первая фраза."},
            {"id": "0002", "n": 2, "hash": "b" * 40, "seed": 2, "text": "Вторая фраза.",
             "flag_words": [["слово", 0.1, 0.2, "conf"]]}]
    (sec / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assemble.write_index(sec / "section.index.tsv", rows,
                         [{"id": "0001", "start_ms": 0, "lead_ms": 0, "trimmed_ms": 1000},
                          {"id": "0002", "start_ms": 1500, "lead_ms": 0, "trimmed_ms": 1000}])
    (sec / "section.mp3").write_bytes(b"fake")
    monkeypatch.setattr(listen.paths, "OUT", out)
    monkeypatch.setattr(listen.paths, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(listen, "_decode", lambda mp3, sr: np.ones(sr * 5, dtype=np.float32) * 0.1)

    def fake_run(cmd, **kw):
        from pathlib import Path
        Path(cmd[-1]).write_bytes(b"mp3")

    monkeypatch.setattr(listen.subprocess, "run", fake_run)
    assert listen.run({"master": {"head_ms": 1000, "sample_rate": 8000}}, intro_s=2, n_random=0) == 0
    lines = (out / "listen" / "index.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "start\tsection\tchunk\ttags\ttext\thash"
    assert [ln.split("\t")[2] for ln in lines[1:]] == ["0001", "0002"]
    assert (out / "listen" / "chunks" / ("a" * 16 + ".wav")).exists()
    assert (out / "listen" / "plan.mp3").exists()
    assert not list((out / "listen").glob("*.part"))
    kind, groups = review.collect(out / "listen")          # marking page → fix by hash
    assert kind == "probe" and len(groups) == 2


def test_cli_wires_listen_plan():
    from audiobook.__main__ import build_parser
    a = build_parser().parse_args(["listen-plan", "--random", "5"])
    assert a.random == 5 and a.intro_s == 30 and a.section is None
