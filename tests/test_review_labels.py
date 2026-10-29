"""Layer 1: review page (review.py), pron-test meta.tsv, labels journal (labels.py).
No models; placeholder text only (no book quotes)."""
from __future__ import annotations

import json
import re

import numpy as np
import pytest
import soundfile as sf

from audiobook import labels, paths, review
from audiobook.pron_test import render_variants, variant_tables, write_results

_CFG = {"model": {"name": "qwen3_tts", "seed": 42, "temperature": 1.0, "language": "ru"},
        "reference": {"path": "ref/ref1.wav"}}


def _wav(path, n=2400):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.full(n, 0.1, dtype=np.float32), 24000, subtype="FLOAT")


def _data(page_text: str) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page_text, re.S)
    return json.loads(m.group(1))


def _page(path):
    return path.read_text(encoding="utf-8")


def _assert_selfcontained(text: str, files: list[str]):
    assert "http://" not in text and "https://" not in text
    for f in files:
        assert f'src="{f}"' in text                      # relative, next to the page
    assert 'preload="none"' in text and "<audio controls" in text
    for word in ("хорошо", "плохо", "Скачать разметку", "Копировать JSON", "Blob",
                 "localStorage", "prefers-color-scheme", 'name="viewport"'):
        assert word in text
    assert re.search(r"try\s*\{[^}]*localStorage", text)  # storage access is guarded
    assert "labels_" in text


# ── pron-test: meta.tsv ───────────────────────────────────────────────────────

class _Eng:
    def synth(self, text, seed, **kw):
        return np.zeros(240, dtype=np.float32)


def _pron_dir(tmp_path):
    row = {"id": "0007", "text": "Плейсхолдер один. Слово стоит тут.", "hash": "b" * 40,
           "seed_override": None}
    res = render_variants(_Eng(), row, _CFG, variant_tables({}, "Слово", ["-", "СлОво"]), seeds=2)
    out = tmp_path / "pron"
    out.mkdir()
    parts = write_results(out, [(row, res)])
    return out, parts


def test_pron_test_writes_meta_tsv(tmp_path):
    out, parts = _pron_dir(tmp_path)
    assert len(parts) == 8                                   # 4 takes × (wav + gap)
    lines = (out / "meta.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t") == ["n", "chunk", "variant", "take", "start", "synth_text"]
    rows = [l.split("\t") for l in lines[1:]]
    assert [r[0] for r in rows] == ["1", "2", "3", "4"]
    assert [(r[2], r[3]) for r in rows] == [("-", "1"), ("-", "2"), ("СлОво", "1"), ("СлОво", "2")]
    assert all(r[1] == "0007" and len(r) == 6 for r in rows)
    assert rows[0][4] == "0:00" and rows[1][4] == "0:01"      # 1.2 s gap + 0.01 s wav
    assert "СлОво" in rows[2][5]
    assert all((out / f"{n}.wav").exists() for n in range(1, 5))
    assert not (out / "meta.tsv.part").exists()


def test_pron_test_failed_variant_has_no_meta_row(tmp_path):
    out = tmp_path / "p"
    out.mkdir()
    row = {"id": "0001", "text": "Плейсхолдер."}
    res = [("-", 1, "Плейсхолдер.", np.zeros(240, dtype=np.float32)),
           ("А", 1, "Плейсхолдер.", None)]
    write_results(out, [(row, res)])
    lines = (out / "meta.tsv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and (out / "1.wav").exists() and not (out / "2.wav").exists()


def test_review_pron_test_dir(tmp_path):
    out, _ = _pron_dir(tmp_path)
    html_path = review.build_review(out, "pron_слово")
    text = _page(html_path)
    assert html_path == out / "review.html"
    files = [f"{n}.wav" for n in range(1, 5)]
    _assert_selfcontained(text, files)
    data = _data(text)
    assert data["kind"] == "pron-test" and [i["file"] for i in data["items"]] == files
    assert data["items"][2]["meta"]["variant"] == "СлОво" and data["items"][2]["meta"]["chunk"] == "0007"
    assert text.count('class="item"') == 4 and "СлОво" in text and "дубль 2" in text
    assert data["safe"] == "pron_слово"


# ── other folder kinds ────────────────────────────────────────────────────────

def test_review_redo_dir_with_manifest(tmp_path):
    out_root = tmp_path / "out"
    d = out_root / "redo" / "01_sec" / "0003"
    names = ["variant_01__seed+100.wav", "variant_02__seed+200.wav", "variant_10__seed+1000.wav"]
    for n in names:
        _wav(d / n)
    sec = out_root / "sections" / "01_sec"
    sec.mkdir(parents=True)
    (sec / "manifest.jsonl").write_text(
        json.dumps({"id": "0003", "text": "Плейсхолдер чанка.", "hash": "c" * 40},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    text = _page(review.build_review(d))
    _assert_selfcontained(text, names)
    data = _data(text)
    assert data["kind"] == "redo" and data["title"] == "0003"
    assert [i["meta"]["variant"] for i in data["items"]] == ["01", "02", "10"]  # natural order
    m = data["items"][0]["meta"]
    assert m["section"] == "01_sec" and m["chunk"] == "0003" and m["seed_offset"] == "100"
    assert "Плейсхолдер чанка." in text


def test_review_redo_dir_without_manifest(tmp_path):
    d = tmp_path / "loose"
    _wav(d / "variant_01__seed+100.wav")
    data = _data(_page(review.build_review(d)))
    assert data["kind"] == "redo" and data["items"][0]["meta"]["variant"] == "01"


def test_review_probe_dir_with_hash_column(tmp_path):
    d = tmp_path / "probe"
    h1, h2 = "a" * 16, "b" * 16
    for h in (h1, h2):
        _wav(d / "chunks" / f"{h}.wav")
    _wav(d / "chunks" / ("c" * 16 + ".wav"))                  # not in the index: ignored
    (d / "index.tsv").write_text(
        "start\tsection\tchunk\ttags\ttext\thash\n"
        f"0:00\t01_sec\t0002\thomograph:x\tПлейсхолдер два.\t{h2}\n"
        f"0:05\t01_sec\t0001\tlatin:PDF\tПлейсхолдер один.\t{h1}\n", encoding="utf-8")
    text = _page(review.build_review(d))
    files = [f"chunks/{h}.wav" for h in (h2, h1)]
    _assert_selfcontained(text, files)
    data = _data(text)
    assert data["kind"] == "probe"
    assert [i["file"] for i in data["items"]] == files       # index (listening) order, index only
    assert "c" * 16 not in text
    assert data["items"][0]["meta"]["chunk"] == "0002" and "homograph:x" in text
    assert "Плейсхолдер один." in text


def test_review_probe_maps_hash_via_manifests(tmp_path):
    out_root = tmp_path / "out"
    d = out_root / "probe"
    h = "d" * 16
    _wav(d / "chunks" / f"{h}.wav")
    (d / "index.tsv").write_text(                              # old format: no hash column
        "start\tsection\tchunk\ttags\ttext\n0:00\t02_sec\t0009\tcaps_word\tПлейсхолдер.\n",
        encoding="utf-8")
    sec = out_root / "sections" / "02_sec"
    sec.mkdir(parents=True)
    (sec / "manifest.jsonl").write_text(
        json.dumps({"id": "0009", "text": "Плейсхолдер.", "hash": "d" * 40}) + "\n", encoding="utf-8")
    data = _data(_page(review.build_review(d)))
    assert data["items"][0]["meta"]["chunk"] == "0009" and data["items"][0]["meta"]["tags"] == "caps_word"


def test_review_golden_pairs_side_by_side(tmp_path):
    d = tmp_path / "golden"
    names = ["01_A.wav", "01_B.wav", "02_A.wav", "02_B.wav"]
    for n in names:
        _wav(d / n)
    text = _page(review.build_review(d, "golden"))
    _assert_selfcontained(text, names)
    assert text.count('class="grp pair"') == 2
    data = _data(text)
    assert data["kind"] == "golden"
    assert [(i["meta"]["pair"], i["meta"]["side"]) for i in data["items"]] == [
        ("01", "A"), ("01", "B"), ("02", "A"), ("02", "B")]


def test_review_ref_compare_subfolders(tmp_path):
    d = tmp_path / "out" / "ref_compare" / "01_sec"
    for cand in ("alpha_1", "beta_2"):
        for cid in ("0001", "0002"):
            _wav(d / cand / f"{cid}.wav")
    text = _page(review.build_review(d))
    _assert_selfcontained(text, ["alpha_1/0001.wav", "beta_2/0002.wav"])
    data = _data(text)
    assert data["kind"] == "ref-compare" and text.count('class="grp pair"') == 2
    assert data["items"][1]["meta"]["candidate"] == "beta_2" and data["items"][1]["meta"]["chunk"] == "0001"


def test_review_generic_with_explicit_meta(tmp_path):
    d = tmp_path / "misc"
    for n in ("b2.wav", "b10.wav", "a.wav"):
        _wav(d / n)
    rows = [{"file": "b10.wav", "text": "Плейсхолдер десять.", "tags": "x"}]
    text = _page(review.build_review(d, "Мои пробы", rows))
    _assert_selfcontained(text, ["a.wav", "b2.wav", "b10.wav"])
    data = _data(text)
    assert data["kind"] == "generic" and [i["file"] for i in data["items"]] == ["a.wav", "b2.wav", "b10.wav"]
    assert "Плейсхолдер десять." in text and data["safe"] == "Мои_пробы"


def test_review_escapes_markup_in_text(tmp_path):
    d = tmp_path / "x"
    _wav(d / "1.wav")
    rows = [{"n": "1", "text": "<script>alert(1)</script> & </script>"}]
    text = _page(review.build_review(d, "t", rows))
    assert "<script>alert" not in text and "&lt;script&gt;" in text
    assert _data(text)["items"][0]["meta"]["text"].startswith("<script>")  # JSON survives round trip


def test_review_wav_names_with_spaces_and_plus_are_relative_urls(tmp_path):
    d = tmp_path / "x"
    _wav(d / "a b.wav")
    text = _page(review.build_review(d))
    assert 'src="a%20b.wav"' in text


def test_review_errors(tmp_path):
    with pytest.raises(SystemExit, match="нет папки"):
        review.build_review(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="нет \\*.wav"):
        review.build_review(tmp_path / "empty")


# ── labels journal ────────────────────────────────────────────────────────────

def _labels_json(tmp_path, items=None, title="pron_слово"):
    items = items if items is not None else [
        {"file": "1.wav", "label": "ok", "issue": "", "comment": "",
         "meta": {"chunk": "0007", "variant": "-", "take": "1", "item": "- / дубль 1"}},
        {"file": "2.wav", "label": "bad", "issue": "ударение", "comment": "ударение на первом",
         "meta": {"chunk": "0007", "section": "01_sec", "hash": "abcdef0123456789", "item": "- / дубль 2"}},
        {"file": "3.wav", "label": "", "issue": "", "comment": "", "meta": {}},
        {"file": "4.wav", "label": "", "issue": "", "comment": "только заметка", "meta": {}},
    ]
    p = tmp_path / "labels_x.json"
    p.write_text(json.dumps({"title": title, "items": items}, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def journal(tmp_path, monkeypatch):
    text_dir = tmp_path / "text"
    monkeypatch.setattr(paths, "TEXT", text_dir)
    return text_dir / "labels.yaml"


def test_labels_import_creates_journal(tmp_path, journal):
    assert labels.import_json(_labels_json(tmp_path), "03_sec", today="2026-01-02") == (3, 0, 1)
    raw = journal.read_text(encoding="utf-8")
    assert raw.startswith("# Журнал решений") and "hash_prefix" in raw.split("\n\n")[0]
    entries = labels.load()
    assert [e["file"] for e in entries] == ["1.wav", "2.wav", "4.wav"]
    e1, e2, e4 = entries
    assert list(e1) == list(labels.FIELDS)
    assert (e1["date"], e1["title"], e1["section"], e1["chunk"], e1["label"]) == (
        "2026-01-02", "pron_слово", "03_sec", "0007", "ok")
    assert e1["hash_prefix"] == "" and e1["item"] == "- / дубль 1"
    assert (e2["label"], e2["issue"], e2["note"], e2["hash_prefix"]) == (
        "bad", "ударение", "ударение на первом", "abcdef01")
    assert e4["label"] == "unsure" and e4["note"] == "только заметка"   # comment without a mark
    assert "ударение" in raw                                             # allow_unicode, no escapes


def test_labels_import_idempotent(tmp_path, journal):
    src = _labels_json(tmp_path)
    labels.import_json(src, None, today="2026-01-02")
    before = journal.read_text(encoding="utf-8")
    assert labels.import_json(src, None, today="2026-02-03") == (0, 3, 1)
    assert journal.read_text(encoding="utf-8") == before
    assert len(labels.load()) == 3


def test_labels_import_dedupes_on_title_and_file_only(tmp_path, journal):
    labels.import_json(_labels_json(tmp_path), None, today="2026-01-02")
    other = _labels_json(tmp_path, title="другой набор")      # same files, other title: new entries
    assert labels.import_json(other, None, today="2026-01-03")[0] == 3
    assert len(labels.load()) == 6


def test_labels_section_from_meta_and_cli_override(tmp_path, journal):
    labels.import_json(_labels_json(tmp_path), None, today="2026-01-02")
    assert [e["section"] for e in labels.load()] == ["", "01_sec", ""]  # meta only where present


def test_labels_import_rejects_garbage(tmp_path, journal):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="не читается JSON"):
        labels.import_json(bad)
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(SystemExit, match="нет списка items"):
        labels.import_json(bad)
    with pytest.raises(SystemExit, match="нет файла"):
        labels.import_json(tmp_path / "missing.json")
    assert not journal.exists()


def test_labels_unknown_issue_becomes_other(tmp_path, journal):
    src = _labels_json(tmp_path, [{"file": "1.wav", "label": "bad", "issue": "что-то", "comment": "", "meta": {}}])
    labels.import_json(src, None, today="2026-01-02")
    assert labels.load()[0]["issue"] == "другое"


def test_labels_hash_prefix_from_probe_filename(tmp_path, journal):
    src = _labels_json(tmp_path, [{"file": "chunks/0123456789abcdef.wav", "label": "ok", "meta": {}}])
    labels.import_json(src, None, today="2026-01-02")
    assert labels.load()[0]["hash_prefix"] == "01234567"


def test_labels_show_filters_by_section(tmp_path, journal, capsys):
    labels.import_json(_labels_json(tmp_path), None, today="2026-01-02")
    labels.show()
    out = capsys.readouterr().out
    assert "2.wav" not in out and "ударение" in out and "всего 3: ok 1, bad 1, unsure 1" in out
    labels.show("01_sec")
    out = capsys.readouterr().out
    assert "всего 1: ok 0, bad 1, unsure 0" in out
    labels.show("nope")
    assert "журнал пуст для секции nope" in capsys.readouterr().out


def test_labels_show_empty_journal(journal, capsys):
    labels.show()
    assert "журнал пуст" in capsys.readouterr().out


def test_cli_review_and_labels(tmp_path, journal, capsys):
    from audiobook.__main__ import main
    d = tmp_path / "g"
    _wav(d / "1_A.wav")
    assert main(["review", "--dir", str(d), "--title", "t"]) == 0
    assert (d / "review.html").exists() and "страница прослушки" in capsys.readouterr().out
    assert main(["labels", "import", str(_labels_json(tmp_path)), "--section", "S"]) == 0
    assert "добавлено 3" in capsys.readouterr().out
    assert main(["labels", "show", "--section", "S"]) == 0
    assert "всего 3" in capsys.readouterr().out


# ── page identity (labels must not collide across pages / runs) ──────────────

def test_review_page_id_differs_for_same_title_and_is_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    d1 = tmp_path / "out" / "pron_test" / "run1"
    d2 = tmp_path / "out" / "pron_test" / "run2"
    for d in (d1, d2):
        _wav(d / "1.wav")
    t1 = _page(review.build_review(d1, "одно имя"))
    t2 = _page(review.build_review(d2, "одно имя"))
    p1, p2 = _data(t1)["page_id"], _data(t2)["page_id"]
    assert p1 and p2 and p1 != p2 and len(p1) == 10
    assert _data(_page(review.build_review(d1, "одно имя")))["page_id"] == p1   # rebuilt page
    assert 'DATA.title + ":" + (DATA.page_id' in t1                # storage key = title + page_id
    assert "page_id: DATA.page_id" in t1                            # exported JSON carries it
    assert '"_" + DATA.page_id' in t1                               # download name too
    # same folder, same name, other audio (a re-run) → another page
    _wav(d1 / "1.wav", n=4800)
    assert _data(_page(review.build_review(d1, "одно имя")))["page_id"] != p1


def test_review_items_carry_section_chunk_hash(tmp_path):
    d = tmp_path / "probe"
    h = "e" * 16
    _wav(d / "chunks" / f"{h}.wav")
    (d / "index.tsv").write_text("start\tsection\tchunk\ttags\ttext\thash\n"
                                 f"0:00\t03_sec\t0004\tx\tПлейсхолдер.\t{h}\n", encoding="utf-8")
    it = _data(_page(review.build_review(d)))["items"][0]
    assert (it["section"], it["chunk"], it["hash"]) == ("03_sec", "0004", h)
    t = _page(d / "review.html")
    assert "hash: it.hash" in t and "section: it.section" in t and "chunk: it.chunk" in t


def test_review_probe_without_index_is_generic(tmp_path):
    d = tmp_path / "probe"
    _wav(d / "chunks" / ("a" * 16 + ".wav"))
    kind, groups = review.collect(d)                         # no index → not "probe", wav still listed
    assert kind != "probe" and [it["file"] for g in groups for it in g] == ["chunks/" + "a" * 16 + ".wav"]


def test_review_probe_old_index_ignores_unmapped_wavs(tmp_path):
    out_root = tmp_path / "out"
    d = out_root / "probe"
    _wav(d / "chunks" / ("d" * 16 + ".wav"))
    _wav(d / "chunks" / ("f" * 16 + ".wav"))                  # in no manifest, not in index
    (d / "index.tsv").write_text(
        "start\tsection\tchunk\ttags\ttext\n0:00\t02_sec\t0009\tcaps_word\tПлейсхолдер.\n",
        encoding="utf-8")
    sec = out_root / "sections" / "02_sec"
    sec.mkdir(parents=True)
    (sec / "manifest.jsonl").write_text(
        json.dumps({"id": "0009", "text": "Плейсхолдер.", "hash": "d" * 40}) + "\n", encoding="utf-8")
    data = _data(_page(review.build_review(d)))
    assert [i["file"] for i in data["items"]] == ["chunks/" + "d" * 16 + ".wav"]


def test_review_ref_compare_hash16_names_map_to_chunks(tmp_path):
    out_root = tmp_path / "out"
    d = out_root / "ref_compare" / "01_sec"
    sec = out_root / "sections" / "01_sec"
    sec.mkdir(parents=True)
    rows = [{"id": "0001", "text": "Плейсхолдер один.", "hash": "1" * 40},
            {"id": "0002", "text": "Плейсхолдер два.", "hash": "2" * 40}]
    (sec / "manifest.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    for cand in ("alpha_1", "beta_2"):
        for r in rows:
            _wav(d / cand / f"{r['hash'][:16]}.wav")
    _wav(d / "_old_20260101-000000" / ("9" * 16 + ".wav"))   # archived: not a candidate
    data = _data(_page(review.build_review(d)))
    assert data["kind"] == "ref-compare"
    assert [(i["meta"]["candidate"], i["meta"]["chunk"]) for i in data["items"]] == [
        ("alpha_1", "0001"), ("beta_2", "0001"), ("alpha_1", "0002"), ("beta_2", "0002")]
    assert data["items"][0]["meta"]["text"] == "Плейсхолдер один."
    assert data["items"][0]["hash"] == "1" * 16


def test_labels_same_file_on_other_page_is_kept(tmp_path, journal):
    items = [{"file": "1.wav", "label": "ok", "meta": {}}]
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"title": "t", "page_id": "p1", "items": items}), encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"title": "t", "page_id": "p2", "items": items}), encoding="utf-8")
    assert labels.import_json(a, None, today="2026-01-02") == (1, 0, 0)
    assert labels.import_json(b, None, today="2026-01-02") == (1, 0, 0)   # same title+file, other page
    assert labels.import_json(a, None, today="2026-01-03") == (0, 1, 0)   # same page: duplicate
    assert [e["page_id"] for e in labels.load()] == ["p1", "p2"]


def test_labels_same_file_other_hash_is_kept(tmp_path, journal):
    def page(h):
        return [{"file": "chunks/x.wav", "hash": h, "section": "05_sec", "chunk": "0003",
                 "label": "bad", "meta": {}}]
    src = tmp_path / "h.json"
    src.write_text(json.dumps({"title": "t", "page_id": "p", "items": page("a" * 16)}), encoding="utf-8")
    labels.import_json(src, None, today="2026-01-02")
    src.write_text(json.dumps({"title": "t", "page_id": "p", "items": page("b" * 16)}), encoding="utf-8")
    assert labels.import_json(src, None, today="2026-01-02")[0] == 1
    e1, e2 = labels.load()
    assert (e1["hash_prefix"], e2["hash_prefix"]) == ("a" * 8, "b" * 8)
    assert e1["section"] == "05_sec" and e1["chunk"] == "0003"          # item-level fields


def test_labels_old_json_without_page_id_still_dedupes_on_title(tmp_path, journal):
    src = _labels_json(tmp_path)                                         # no page_id
    assert labels.import_json(src, None, today="2026-01-02")[0] == 3
    assert all(e["page_id"] == "" for e in labels.load())
    assert labels.import_json(src, None, today="2026-01-03")[:2] == (0, 3)
    # an old journal written before page_id existed loads and dedupes too
    entries = labels.load()
    for e in entries:
        e.pop("page_id")
    labels._write(entries, journal)
    assert labels.import_json(src, None, today="2026-01-04")[:2] == (0, 3)


def test_labels_import_of_real_page_export(tmp_path, journal):
    """JSON shaped exactly like the page's build(): page_id + item fields."""
    d = tmp_path / "p"
    _wav(d / "1.wav")
    data = _data(_page(review.build_review(d, "страница")))
    export = {"title": data["title"], "page_id": data["page_id"], "kind": data["kind"],
              "items": [{"file": it["file"], "section": it.get("section", ""),
                         "chunk": it.get("chunk", ""), "hash": it.get("hash", ""),
                         "label": "ok", "issue": "", "comment": "", "meta": it["meta"]}
                        for it in data["items"]]}
    src = tmp_path / "e.json"
    src.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
    assert labels.import_json(src, None, today="2026-01-02") == (1, 0, 0)
    assert labels.load()[0]["page_id"] == data["page_id"]


# ── pron-test: a previous run is moved aside, never deleted ──────────────────

def test_pron_test_previous_run_moved_to_old(tmp_path, capsys):
    from audiobook.pron_test import archive_previous_run
    out, _ = _pron_dir(tmp_path)                             # 1..4.wav + meta.tsv
    (out / "all.mp3").write_bytes(b"mp3")
    (out / "review.html").write_text("page", encoding="utf-8")
    (out / "notes.txt").write_text("keep", encoding="utf-8")
    old = archive_previous_run(out)
    assert old is not None and old.parent == out and old.name.startswith("_old_")
    assert sorted(p.name for p in old.iterdir()) == [
        "1.wav", "2.wav", "3.wav", "4.wav", "all.mp3", "meta.tsv", "review.html"]
    assert sorted(p.name for p in out.iterdir() if p.is_file()) == ["notes.txt"]
    assert "перенесены" in capsys.readouterr().out
    assert archive_previous_run(out) is None                 # nothing left to move
    # new run with fewer takes: no stale 3.wav/4.wav next to the new ones
    row = {"id": "0007", "text": "Плейсхолдер.", "hash": "b" * 40, "seed_override": None}
    res = render_variants(_Eng(), row, _CFG, variant_tables({}, "Слово", ["-"]), seeds=2)
    write_results(out, [(row, res)])
    assert sorted(p.name for p in out.glob("*.wav")) == ["1.wav", "2.wav"]
    kind, groups = review.collect(out)
    assert kind == "pron-test" and len(groups) == 2


def test_pron_test_run_archives_before_rendering(tmp_path, monkeypatch):
    import audiobook.master as master_mod
    import audiobook.pronounce as pron_mod
    import audiobook.synth as synth_mod
    import audiobook.worker as worker_mod
    from audiobook import pron_test
    from audiobook.synth import _write_manifest
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    sec = tmp_path / "out" / "sections" / "01_sec"
    sec.mkdir(parents=True)
    _write_manifest(sec / "manifest.jsonl",
                    [{"id": "0001", "text": "Плейсхолдер Слово тут.", "hash": "a" * 40}])
    out = tmp_path / "out" / "pron_test" / "01_sec_0001_Слово"
    _wav(out / "9.wav")                                       # leftover of an older, longer run

    class Ctx:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            assert not (out / "9.wav").exists()               # moved before the engine starts
            return _Eng()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(worker_mod, "TimeoutSynth", Ctx)
    monkeypatch.setattr(synth_mod, "worker_config", lambda c, w: {})
    monkeypatch.setattr(pron_mod, "load_table", lambda: {})
    monkeypatch.setattr(master_mod, "master_wav", lambda src, dst, cfg: dst.write_bytes(b"m"))
    cfg = dict(_CFG, render={"chunk_timeout_s": 5})
    assert pron_test.run(cfg, "01_sec", "Слово", ["-"], seeds=1) == 0
    (old,) = [p for p in out.iterdir() if p.is_dir()]
    assert (old / "9.wav").exists() and sorted(p.name for p in out.glob("*.wav")) == ["1.wav"]
