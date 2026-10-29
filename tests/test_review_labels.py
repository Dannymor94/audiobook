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
    _wav(d / "chunks" / ("c" * 16 + ".wav"))                  # not in the index: still listed
    (d / "index.tsv").write_text(
        "start\tsection\tchunk\ttags\ttext\thash\n"
        f"0:00\t01_sec\t0002\thomograph:x\tПлейсхолдер два.\t{h2}\n"
        f"0:05\t01_sec\t0001\tlatin:PDF\tПлейсхолдер один.\t{h1}\n", encoding="utf-8")
    text = _page(review.build_review(d))
    files = [f"chunks/{h}.wav" for h in (h2, h1, "c" * 16)]
    _assert_selfcontained(text, files)
    data = _data(text)
    assert data["kind"] == "probe"
    assert [i["file"] for i in data["items"]] == files       # index (listening) order first
    assert data["items"][0]["meta"]["chunk"] == "0002" and "homograph:x" in text
    assert "Плейсхолдер один." in text and data["items"][2]["meta"].get("chunk") is None


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
