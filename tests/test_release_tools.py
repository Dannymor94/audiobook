"""master padding/tags, sync map, impact, pace (no models, no ffmpeg runs)."""
import json
from pathlib import Path

from audiobook import impact, master, pace, sync


# ── master ──────────────────────────────────────────────────────────────────

def test_pad_filter():
    assert master.pad_filter({"master": {}}) == ""
    assert master.pad_filter({"master": {"head_ms": 1000, "tail_ms": 2500}}) == \
        "adelay=delays=1000:all=1,apad=pad_dur=2.5"


def test_encode_args_tags_cover_and_temp_target(tmp_path):
    cmd = master.encode_args("ff", tmp_path / "a.wav", tmp_path / "a.mp3.part", "AF", 44100,
                             {"title": "Глава 1", "track": "1/3"}, tmp_path / "c.jpg")
    assert cmd[-3:] == ["-f", "mp3", str(tmp_path / "a.mp3.part")]
    assert "title=Глава 1" in cmd and "track=1/3" in cmd
    assert cmd[cmd.index("-map") + 1] == "0:a" and "1:v" in cmd
    assert "-b:a" in cmd and cmd[cmd.index("-b:a") + 1] == "192k"


def test_book_tags(tmp_path, monkeypatch):
    blocks = tmp_path / "blocks"
    blocks.mkdir()
    for nn, slug, head in (("01", "a", "Введение"), ("02", "b", "Глава 1. Тест"), ("03", "c", "")):
        (blocks / f"{nn}_{slug}.blocks.json").write_text(
            json.dumps({"nn": nn, "slug": slug, "heading": head}), encoding="utf-8")
        (tmp_path / f"{nn}_{slug}.norm.txt").write_text("слово " * 20, encoding="utf-8")
    monkeypatch.setattr(master.paths, "TEXT", tmp_path)
    cfg = {"book": {"title": "Книга", "author": "Автор", "narrator": ""},
           "render": {"skip_sections": ["01_a"]}}
    t = master.book_tags(cfg, "02_b")
    assert t["title"] == "Глава 1. Тест" and t["album"] == "Книга" and t["artist"] == "Автор"
    assert t["track"] == "1/2" and "comment" not in t
    assert master.book_tags(cfg, "03_c")["title"] == "03_c"


# ── sync ────────────────────────────────────────────────────────────────────

def test_sync_build_offsets_and_paragraphs():
    rows = [{"id": "0001", "text": "Первая фраза.", "pause_after_ms": 350},
            {"id": "0002", "text": "Вторая.", "pause_after_ms": 900},
            {"id": "0003", "text": "Нет в индексе."}]
    index = {"0001": {"start_ms": 0, "lead_ms": 30, "dur_ms": 1200},
             "0002": {"start_ms": 1550, "lead_ms": 10, "dur_ms": 800}}
    out = sync.build(rows, index, head_ms=1000, para_ms=900)
    assert out == [
        {"id": "0001", "start_ms": 1000, "end_ms": 2200, "text": "Первая фраза.", "para_end": False},
        {"id": "0002", "start_ms": 2550, "end_ms": 3350, "text": "Вторая.", "para_end": True}]


def test_sync_write_section_refuses_stale_and_writes(tmp_path, monkeypatch):
    from audiobook import assemble
    monkeypatch.setattr(sync.paths, "OUT", tmp_path)
    monkeypatch.setattr(sync.paths, "TEXT", tmp_path / "text")
    sec = tmp_path / "sections" / "01_a"
    sec.mkdir(parents=True)
    rows = [{"id": "0001", "hash": "a" * 40, "seed": 1, "text": "Раз.", "pause_after_ms": 350}]
    (sec / "manifest.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    assemble.write_index(sec / "section.index.tsv", rows,
                         [{"id": "0001", "start_ms": 0, "lead_ms": 5, "trimmed_ms": 700}])
    out = sync.write_section({"master": {"head_ms": 1000}}, "01_a")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["chunks"][0]["start_ms"] == 1000 and data["chunks"][0]["end_ms"] == 1700
    rows[0]["seed"] = 2                                    # re-take after assemble
    (sec / "manifest.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    try:
        sync.write_section({}, "01_a")
        raise AssertionError("must refuse stale index")
    except SystemExit as e:
        assert "assemble" in str(e)


# ── impact ──────────────────────────────────────────────────────────────────

def test_impact_diff_rows_multiset_and_locked():
    old = [{"id": "1", "hash": "h1", "status": "done", "text": "aaaa"},
           {"id": "2", "hash": "h1", "status": "done", "text": "aaaa"},
           {"id": "3", "hash": "h3", "status": "done", "text": "bbbbbb", "locked": True},
           {"id": "4", "hash": "h4", "status": "pending", "text": "cc"}]
    new = [{"hash": "h1"}, {"hash": "h3x"}, {"hash": "h4x"}]
    d = impact.diff_rows(old, new)
    assert [r["id"] for r in d["lost"]] == ["2", "3"]       # one h1 survives; pending ignored
    assert d["chars"] == 10 and d["locked"] == ["3"] and d["rendered"] == 3


# ── pace ────────────────────────────────────────────────────────────────────

def test_pace_table_flags_outlier():
    long = "x" * 80
    a = pace.section_rates([{"status": "done", "ms_per_char": 70, "text": long}] * 5
                           + [{"status": "done", "ms_per_char": 300, "text": "Шаг."}])
    assert a == [70.0] * 5                                 # short chunk ignored
    book, rows = pace.table({"a": a, "b": [70.0] * 5, "c": [80.0] * 5, "d": []})
    assert book == 70.0
    flags = {r["section"]: r["flag"] for r in rows}
    assert flags == {"a": False, "b": False, "c": True}


def test_cli_wires_release_tools():
    from audiobook.__main__ import build_parser
    p = build_parser()
    assert p.parse_args(["sync", "--all"]).all is True
    assert p.parse_args(["impact", "--verbose"]).verbose is True
    assert p.parse_args(["pace"]).cmd == "pace"


def test_config_has_book_and_padding():
    import yaml
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert 1000 <= cfg["master"]["head_ms"] <= 5000 and 1000 <= cfg["master"]["tail_ms"] <= 5000
    assert cfg["book"]["title"]
