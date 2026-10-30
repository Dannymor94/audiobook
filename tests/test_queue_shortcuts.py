"""queue section / queue redo: one command → validated job list."""
import json

from audiobook import jobqueue as jq


def test_section_jobs_order_and_first():
    jobs = jq.section_jobs("20_x", 2)
    assert [j[0] for j in jobs] == ["chunk", "synth", "qc", "assemble", "master", "suspects", "sync",
                                    "listen-plan"]
    assert jobs[-1][-1] == "--notify" and "20_x" in jobs[-1]
    assert "sync" not in [j[0] for j in jq.section_jobs("20_x", 2, first=3)]
    assert all("--section" in j and "20_x" in j for j in jobs)
    assert "--first" not in sum(jobs, [])
    pj = jq.section_jobs("20_x", 1, first=10)
    assert pj[1][-2:] == ["--first", "10"] and "--first" not in pj[0] and "--first" not in pj[2]


def test_section_jobs_all_pass_validation():
    for args in jq.section_jobs("20_x", 2, first=5) + jq.redo_jobs("20_x", ["0001", "0002"]):
        assert jq.validate_args(args, jq.DEFAULT_CONFIG) is None, args


def test_add_many_all_or_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("AUDIOBOOK_CONFIG", raising=False)
    q = tmp_path / "q"
    try:
        jq.add_many([["probe", "--max", "1"], ["synth"]], q)   # synth w/o section
        raise AssertionError("must refuse")
    except ValueError:
        pass
    assert jq.list_jobs(q) == []
    added = jq.add_many(jq.redo_jobs("20_x", ["0001", "0002"]), q)
    assert [j["args"][2] for j in added] == ["0001", "0002"]


def test_section_exists(tmp_path, monkeypatch):
    blocks = tmp_path / "blocks"
    blocks.mkdir()
    (blocks / "20_x.blocks.json").write_text(json.dumps({"nn": "20", "slug": "x"}), encoding="utf-8")
    monkeypatch.setattr(jq.paths, "TEXT", tmp_path)
    assert jq.section_exists("20_x")
    assert not jq.section_exists("20_y")


def test_cli_parses_shortcuts():
    from audiobook.__main__ import build_parser
    a = build_parser().parse_args(["queue", "section", "20_x", "--first", "3"])
    assert (a.queue_cmd, a.section, a.workers, a.first) == ("section", "20_x", 2, 3)
    a = build_parser().parse_args(["queue", "redo", "20_x", "0001", "0002"])
    assert a.chunk_ids == ["0001", "0002"] and a.candidates == 3
