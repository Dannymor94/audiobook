"""./run.sh status: read-only book overview (tmp text/out, no models)."""
import json
import os
import time

from audiobook import status


def _setup(tmp_path, monkeypatch):
    text, out = tmp_path / "text", tmp_path / "out"
    (text / "blocks").mkdir(parents=True)
    for nn, slug in (("01", "a"), ("02", "b"), ("03", "c")):
        (text / "blocks" / f"{nn}_{slug}.blocks.json").write_text(
            json.dumps({"nn": nn, "slug": slug}), encoding="utf-8")
        (text / f"{nn}_{slug}.norm.txt").write_text("слово " * 50, encoding="utf-8")
    monkeypatch.setattr(status.paths, "TEXT", text)
    monkeypatch.setattr(status.paths, "OUT", out)
    sec = out / "sections" / "01_a"
    sec.mkdir(parents=True)
    rows = [{"id": "0001", "text": "x" * 100, "status": "done", "duration_ms": 8000},
            {"id": "0002", "text": "y" * 50, "status": "manual", "locked": True},
            {"id": "0003", "text": "z" * 50}]
    (sec / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                                        encoding="utf-8")
    (sec / "section.suspects.tsv").write_text("time\tchunk\n0:01\t0001\n0:02\t0001\n",
                                              encoding="utf-8")
    return sec


def test_section_status_counts(tmp_path, monkeypatch):
    sec = _setup(tmp_path, monkeypatch)
    st = status.section_status("01_a", set())
    assert (st.rows, st.done, st.manual, st.locked, st.chars, st.done_chars) == (3, 1, 1, 1, 200, 100)
    assert st.suspects == 2 and st.audio == "—" and st.remaining_chars == 100
    mp3 = sec / "section.mp3"
    mp3.write_bytes(b"")
    assert status.section_status("01_a", set()).audio == "собрано"
    old = time.time() - 100
    os.utime(mp3, (old, old))
    assert status.section_status("01_a", set()).audio == "устарело"


def test_unchunked_and_skipped(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    st = status.section_status("02_b", set())
    assert not st.chunked and st.chars > 0
    assert status.section_status("02_b", {"02_b"}).remaining_chars == 0
    assert status.book_sections() == ["01_a", "02_b", "03_c"]


def test_cps_and_eta():
    s = status.SectionStatus(name="x", done_chars=1000, done_ms=80000)
    assert status.measured_cps([s]) == status.DEFAULT_CPS          # too little data
    s2 = status.SectionStatus(name="y", done_chars=26000, done_ms=2000000)
    assert status.measured_cps([s2]) == 13.0
    assert status.eta_hours(13 * 3600, 13.0, 6.5) == 6.5


def test_run_prints_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch)
    before = sorted(p for p in tmp_path.rglob("*"))
    assert status.run({"render": {"skip_sections": ["03_c"]}}) == 0
    out = capsys.readouterr().out
    assert "пропуск" in out and "не начато" in out and "ждут человека" in out
    assert sorted(p for p in tmp_path.rglob("*")) == before
