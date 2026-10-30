"""Layer 1: fix plan / queue / review (fix.py) and review.build_combined.
No models, tmp_path only; texts are placeholders, not book quotes."""
from __future__ import annotations

import json
import re

import numpy as np
import pytest
import soundfile as sf

from audiobook import fix, jobqueue, labels, review

S1, S2 = "01_sec", "02_sec"


def _h(c: str) -> str:
    return c * 40


def _manifest(out_root, section, rows):
    d = out_root / "sections" / section
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _row(cid, hc, text=None, locked=False):
    return {"id": cid, "text": text or f"Плейсхолдер чанка {cid}.", "hash": _h(hc),
            "status": "done", "locked": locked}


@pytest.fixture
def out_root(tmp_path):
    root = tmp_path / "out"
    _manifest(root, S1, [_row("0001", "1"), _row("0002", "2"), _row("0003", "3", locked=True)])
    _manifest(root, S2, [_row("0001", "a"), _row("0002", "b")])
    return root


def _item(file, label, section="", chunk="", hash_="", comment="", issue="", meta=None):
    return {"file": file, "section": section, "chunk": chunk, "hash": hash_, "label": label,
            "issue": issue, "comment": comment, "meta": meta or {}}


def _json(tmp_path, name, items, kind="probe", title="t", page_id="p1"):
    p = tmp_path / name
    p.write_text(json.dumps({"title": title, "page_id": page_id, "kind": kind, "items": items},
                            ensure_ascii=False), encoding="utf-8")
    return p


def _wav(path, n=2400):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.full(n, 0.1, dtype=np.float32), 24000, subtype="FLOAT")


def _ids(p):
    return {s: [c["id"] for c in cs] for s, cs in p.sections.items()}


# ── plan ──────────────────────────────────────────────────────────────────────

def test_plan_dedupes_and_keeps_manifest_order(tmp_path, out_root):
    a = _json(tmp_path, "a.json", [
        _item("chunks/x2.wav", "bad", S1, "0002", "2" * 16, comment="каша в конце"),
        _item("chunks/x1.wav", "bad", S1, "0001", "1" * 16, issue="ударение"),
        _item("chunks/y1.wav", "ok", S2, "0001", "a" * 16),
        _item("chunks/y2.wav", "плохо", S2, "0002", "b" * 16),
    ])
    b = _json(tmp_path, "b.json", [                       # another page, same chunk again
        _item("chunks/z.wav", "bad", S1, "0002", "2" * 16, issue="темп", comment="быстро"),
    ], page_id="p2")
    p = fix.plan([b, a, a], out_root)                     # a twice: deduped
    assert _ids(p) == {S1: ["0001", "0002"], S2: ["0002"]}
    c2 = p.sections[S1][1]
    assert c2["issues"] == ["темп"] and set(c2["notes"]) == {"быстро", "каша в конце"}
    assert c2["verified"] and c2["text"] == "Плейсхолдер чанка 0002." and not c2["locked"]
    assert p.stale == [] and p.skipped == []


def test_plan_stale_hash_is_reported_not_planned(tmp_path, out_root):
    a = _json(tmp_path, "a.json", [
        _item("chunks/old.wav", "bad", S1, "0001", "f" * 16, comment="старое"),
        _item("chunks/new.wav", "bad", S1, "0002", "2" * 16),
    ])
    p = fix.plan([a], out_root)
    assert _ids(p) == {S1: ["0002"]}
    assert len(p.stale) == 1 and p.stale[0]["chunk"] == "0001"
    assert p.stale[0]["reason"] == fix.R_STALE


def test_plan_hash_follows_rechunked_text(tmp_path, out_root):
    # marked as 0005 when listening; the same text (hash) is now id 0002
    a = _json(tmp_path, "a.json", [_item("chunks/q.wav", "bad", S1, "0005", "2" * 16)])
    p = fix.plan([a], out_root)
    assert _ids(p) == {S1: ["0002"]} and p.sections[S1][0]["marked_as"] == ["0005"]


def test_plan_unknown_section_and_chunk(tmp_path, out_root):
    a = _json(tmp_path, "a.json", [
        _item("a.wav", "bad", "99_none", "0001"),
        _item("b.wav", "bad", S1, "0042"),
        _item("c.wav", "bad", "", ""),
    ], kind="generic")
    p = fix.plan([a], out_root)
    assert p.sections == {}
    reasons = [s["reason"] for s in p.skipped]
    assert reasons == ["нет манифеста секции 99_none", f"нет чанка 0042 в секции {S1}",
                       "нет секции — импортируй с --section"]


def test_plan_without_hash_is_unverified(tmp_path, out_root, capsys):
    a = _json(tmp_path, "a.json", [_item("0002.wav", "bad", S1, "")], kind="generic")
    p = fix.plan([a], out_root)                          # chunk id from the file stem
    assert _ids(p) == {S1: ["0002"]} and not p.sections[S1][0]["verified"]
    fix.print_plan(p)
    assert "не проверено на устаревание" in capsys.readouterr().out


def test_plan_locked_chunk_is_planned_and_flagged(tmp_path, out_root, capsys):
    a = _json(tmp_path, "a.json", [_item("chunks/l.wav", "bad", S1, "0003", "3" * 16)])
    p = fix.plan([a], out_root)
    assert _ids(p) == {S1: ["0003"]} and p.sections[S1][0]["locked"]
    fix.print_plan(p)
    assert fix.R_LOCKED in capsys.readouterr().out


def test_plan_pron_test_redo_refcmp_skipped(tmp_path, out_root):
    pron = _json(tmp_path, "pron.json", [
        _item("1.wav", "bad", "", "0001", meta={"chunk": "0001", "variant": "СлОво",
                                                "take": "1", "item": "СлОво / дубль 1"}),
    ], kind="pron-test")
    redo = _json(tmp_path, "redo.json", [
        _item("variant_01__seed+100.wav", "bad", S1, "0001", "1" * 16)], kind="redo",
        page_id="p3")
    p = fix.plan([pron, redo], out_root)
    assert p.sections == {}
    assert [s["reason"] for s in p.skipped] == [fix.R_PRON, fix.R_REDO]
    assert p.skipped[0]["item"] == "СлОво / дубль 1"


def test_plan_golden_maps_by_hash_only(tmp_path, out_root):
    g = _json(tmp_path, "g.json", [
        _item("01_A.wav", "bad", S2, "0001", "a" * 16),           # current config: maps
        _item("01_B.wav", "bad", S2, "0001", "e" * 16),           # other tag: not the book
    ], kind="golden")
    p = fix.plan([g], out_root)
    assert _ids(p) == {S2: ["0001"]}
    assert [s["reason"] for s in p.skipped] == [fix.R_GOLDEN] and p.stale == []


def test_plan_from_journal_infers_kind_and_since(tmp_path, out_root):
    jp = tmp_path / "text" / "labels.yaml"
    entries = [
        {"date": "2026-01-01", "title": "t", "page_id": "p", "file": "chunks/a.wav",
         "section": S1, "chunk": "0001", "hash_prefix": "1" * 8, "item": "", "label": "bad",
         "issue": "", "note": ""},
        {"date": "2026-02-01", "title": "t", "page_id": "p", "file": "chunks/b.wav",
         "section": S1, "chunk": "0002", "hash_prefix": "2" * 8, "item": "", "label": "bad",
         "issue": "", "note": "заметка"},
        {"date": "2026-02-01", "title": "pron", "page_id": "q", "file": "2.wav",
         "section": "", "chunk": "0001", "hash_prefix": "", "item": "- / дубль 2",
         "label": "bad", "issue": "ударение", "note": ""},
        {"date": "2026-02-01", "title": "t", "page_id": "p", "file": "chunks/c.wav",
         "section": S2, "chunk": "0001", "hash_prefix": "a" * 8, "item": "", "label": "unsure",
         "issue": "", "note": ""},
    ]
    labels._write(entries, jp)
    p = fix.plan([jp], out_root)
    assert _ids(p) == {S1: ["0001", "0002"]}
    assert [s["reason"] for s in p.skipped] == [fix.R_PRON] and len(p.unsure) == 1
    assert _ids(fix.plan([jp], out_root, since="2026-02-01")) == {S1: ["0002"]}


def test_cmd_plan_writes_plan_json_and_prints(tmp_path, out_root, capsys):
    a = _json(tmp_path, "a.json", [
        _item("chunks/x.wav", "bad", S1, "0002", "2" * 16, comment="заметка"),
        _item("chunks/o.wav", "bad", S1, "0001", "f" * 16)])
    assert fix.cmd_plan([str(a)], out_root=out_root) == 0
    out = capsys.readouterr().out
    assert S1 in out and "0002" in out and "Плейсхолдер чанка 0002." in out and "заметка" in out
    assert "устарело" in out and "./run.sh fix queue" in out
    data = json.loads(fix.plan_path(out_root).read_text(encoding="utf-8"))
    assert data["sections"][0]["section"] == S1 and data["sections"][0]["chunks"][0]["id"] == "0002"
    assert len(data["stale"]) == 1
    assert not list(fix.fix_dir(out_root).glob("*.part"))
    assert fix.Plan.from_json(data).chunk_count() == 1


def test_cmd_plan_defaults_to_journal(tmp_path, out_root):
    with pytest.raises(SystemExit, match="нет журнала"):
        fix.cmd_plan([], out_root=out_root, journal=tmp_path / "none.yaml")


# ── queue ─────────────────────────────────────────────────────────────────────

def _planned(tmp_path, out_root):
    a = _json(tmp_path, "a.json", [
        _item("chunks/1.wav", "bad", S1, "0001", "1" * 16),
        _item("chunks/3.wav", "bad", S1, "0003", "3" * 16),
        _item("chunks/b.wav", "bad", S2, "0002", "b" * 16)])
    fix.cmd_plan([str(a)], out_root=out_root)


def test_cmd_queue_adds_redo_jobs(tmp_path, out_root, monkeypatch, capsys):
    monkeypatch.delenv("AUDIOBOOK_CONFIG", raising=False)
    _planned(tmp_path, out_root)
    # 0001 already has two candidates for this text: the new job asks for 2 + 3
    d = fix.redo_dir(S1, "0001", out_root)
    for i in (1, 2):
        _wav(d / f"variant_{i:02d}__seed+{i * 100}.wav")
    (d / "meta.json").write_text(json.dumps({"hash": _h("1"), "text": "x"}), encoding="utf-8")
    q = tmp_path / "q"
    capsys.readouterr()
    assert fix.cmd_queue(3, out_root, q) == 0
    jobs = jobqueue.list_jobs(q)
    assert [j["args"] for j in jobs] == [["redo", S1, "0001", "--candidates", "5"],
                                         ["redo", S1, "0003", "--candidates", "3"],
                                         ["redo", S2, "0002", "--candidates", "3"]]
    out = capsys.readouterr().out
    assert "./run.sh queue run, затем ./run.sh fix review" in out and "уже есть кандидаты 1, 2" in out


def test_cmd_queue_all_or_nothing(tmp_path, out_root, monkeypatch, capsys):
    _planned(tmp_path, out_root)
    q = tmp_path / "q"
    monkeypatch.setenv("AUDIOBOOK_CONFIG", "trial.yaml")   # redo refuses a trial config
    assert fix.cmd_queue(3, out_root, q) == 2
    assert jobqueue.list_jobs(q) == []
    assert "ничего не поставлено" in capsys.readouterr().out


def test_cmd_queue_refuses_outdated_plan(tmp_path, out_root, monkeypatch, capsys):
    monkeypatch.delenv("AUDIOBOOK_CONFIG", raising=False)
    _planned(tmp_path, out_root)
    _manifest(out_root, S2, [_row("0001", "a"), _row("0002", "c")])   # text of 0002 changed
    q = tmp_path / "q"
    assert fix.cmd_queue(3, out_root, q) == 2
    assert jobqueue.list_jobs(q) == []
    assert "план устарел" in capsys.readouterr().out


def test_cmd_queue_without_plan(tmp_path, out_root):
    with pytest.raises(SystemExit, match="fix plan"):
        fix.cmd_queue(3, out_root, tmp_path / "q")


# ── review ────────────────────────────────────────────────────────────────────

def _data(text):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', text, re.S)
    return json.loads(m.group(1))


def test_cmd_review_combined_page(tmp_path, out_root, capsys):
    _planned(tmp_path, out_root)
    for section, cid, hc, n in ((S1, "0001", "1", 3), (S2, "0002", "b", 2)):
        d = fix.redo_dir(section, cid, out_root)
        for i in range(1, n + 1):
            _wav(d / f"variant_{i:02d}__seed+{i * 100}.wav")
        (d / "meta.json").write_text(json.dumps({"hash": _h(hc), "text": "x"}),
                                     encoding="utf-8")
        _wav(d / "_old_aaaaaaaaaaaa" / "variant_09__seed+900.wav")   # archived: ignored
    # 0003: folder with candidates of another text → not shown
    d3 = fix.redo_dir(S1, "0003", out_root)
    _wav(d3 / "variant_01__seed+100.wav")
    (d3 / "meta.json").write_text(json.dumps({"hash": _h("9")}), encoding="utf-8")
    capsys.readouterr()
    assert fix.cmd_review(out_root) == 0
    page = fix.fix_dir(out_root) / "review.html"
    text = page.read_text(encoding="utf-8")
    data = _data(text)
    files = [i["file"] for i in data["items"]]
    assert files == [f"../redo/{S1}/0001/variant_0{i}__seed+{i}00.wav" for i in (1, 2, 3)] + \
                    [f"../redo/{S2}/0002/variant_0{i}__seed+{i}00.wav" for i in (1, 2)]
    assert "_old_" not in text and "variant_09" not in text
    assert text.count('class="grp pair"') == 2                 # one row per chunk
    assert f"{S1} · 0001 · вариант 2" in text
    assert data["items"][0]["section"] == S1 and data["items"][0]["chunk"] == "0001"
    for f in files:                                            # links resolve from the page
        assert (page.parent / f).resolve().is_file()
    out = capsys.readouterr().out
    assert f"./run.sh accept {S1} 0001 <N>    варианты: 1, 2, 3" in out
    assert f"./run.sh accept {S2} 0002 <N>" in out
    assert "кандидаты от другого текста" in out and f"{S1} 0003" in out
    # marks exported from this page are redo candidates: skipped by the next plan
    export = _json(tmp_path, "fixpage.json",
                   [dict(_item(f, "bad"), meta=i["meta"], section=i.get("section", ""),
                         chunk=i.get("chunk", ""), hash=i.get("hash", ""))
                    for f, i in zip(files, data["items"])], kind=data["kind"],
                   page_id=data["page_id"])
    p = fix.plan([export], out_root)
    assert p.sections == {} and {s["reason"] for s in p.skipped} == {fix.R_REDO}


def test_cmd_review_nothing_rendered(tmp_path, out_root, capsys):
    _planned(tmp_path, out_root)
    assert fix.cmd_review(out_root) == 1
    out = capsys.readouterr().out
    assert "ещё не отрендерено: 3" in out and not (fix.fix_dir(out_root) / "review.html").exists()


def test_build_combined_keeps_single_review_behaviour(tmp_path):
    d = tmp_path / "out" / "redo" / S1 / "0001"
    _wav(d / "variant_01__seed+100.wav")
    page, empty = review.build_combined([(d, "p"), (tmp_path / "nope", "x")],
                                        tmp_path / "out" / "fix" / "review.html", "t")
    assert page and empty == [tmp_path / "nope"]
    assert review.rel_url(tmp_path / "a" / "b", tmp_path / "c" / "d.wav") == "../../c/d.wav"
    # the plain one-folder page is unchanged
    assert _data(review.build_review(d).read_text(encoding="utf-8"))["items"][0]["file"] == \
        "variant_01__seed+100.wav"


def test_infer_kind():
    assert fix.infer_kind("variant_01__seed+100.wav") == "redo"
    assert fix.infer_kind("../redo/S/0001/variant_01__seed+100.wav") == "redo"
    assert fix.infer_kind("03_B.wav") == "golden"
    assert fix.infer_kind("3.wav", "СлОво / дубль 1") == "pron-test"
    assert fix.infer_kind("chunks/" + "a" * 16 + ".wav") == "probe"
    assert fix.infer_kind("alpha/" + "a" * 16 + ".wav") == "ref-compare"
    assert fix.infer_kind("0003.wav") == "generic"
