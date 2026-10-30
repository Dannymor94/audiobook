"""Layer 1: pronounce audit — counting with respell's regex, flags, atomic tsv.
All text is placeholder (no manuscript)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiobook import paths, pron_audit as pa
from audiobook.pronounce import build_pattern, respell


# ------------------------------------------------------------------ pure parts

@pytest.mark.parametrize("key,value,expected", [
    ("альфа", "альфА", []),                       # capital stressed vowel
    ("Омега", "Оомега", []),                      # doubled initial vowel
    ("бета", "бёта", []),                         # ё/е only
    ("гамма", "гамма", [pa.FLAG_NOOP]),
    ("дельта", "дельтта", [pa.FLAG_LETTERS]),     # an extra consonant
    ("сигма", "сигна", [pa.FLAG_LETTERS]),        # a typo fix: still visible
    ("Раз. Два", "Раз, два", [pa.FLAG_PUNCT, pa.FLAG_CONSONANT]),
    ("каппа", "каПпа", [pa.FLAG_CONSONANT]),
])
def test_change_flags(key, value, expected):
    assert pa.change_flags(key, value) == expected


def test_count_matches_respell_single_pass():
    table = {"раз два": "раз двА", "два": "двА", "Три": "ТрИ"}
    texts = ["раз два и два, три.", "Три два-три двадцать"]
    pat = build_pattern(table)
    got = pa.count_fires(texts, pat)
    # The phrase wins over the word inside it; lowercase "три" does not match
    # "Три"; "два" fires inside "два-три" (\b at the hyphen) but not in "двадцать".
    assert got == {"раз два": 1, "два": 2, "Три": 1}
    # Identical to what respell actually replaces.
    assert respell(texts[0], table) == "раз двА и двА, три."


def test_build_pattern_empty_and_respell_identity():
    assert build_pattern({}) is None
    assert respell("альфа", {}) == "альфа"


def test_audit_rows_flags_and_sections():
    table = {"альфа": "альфА", "бета": "бетА", "сигма": "сигна", "омега": "омегА"}
    chunks = {"01_a": ["альфа бета", "альфа"], "02_b": ["альфа"]}
    norms = {"01_a": "альфа бета\nальфа\n", "02_b": "альфа\n«омега»\n"}
    rows = {r["key"]: r for r in pa.audit_rows(table, {"бета"}, chunks, norms)}
    assert rows["альфа"]["fires"] == 3
    assert rows["альфа"]["sections"] == [("01_a", 2), ("02_b", 1)]
    assert rows["альфа"]["flags"] == []
    assert pa.FLAG_WATCH in rows["бета"]["flags"]
    assert rows["сигма"]["flags"][:2] == [pa.FLAG_DEAD, pa.FLAG_LETTERS]
    # in the raw text but not in any chunk → dead + mismatch
    assert rows["омега"]["fires"] == 0 and rows["омега"]["text_hits"] == 1
    assert pa.FLAG_TEXT_DIFF in rows["омега"]["flags"]
    report = pa.format_report(list(rows.values()))
    assert "мёртвая запись: 2" in report and "01×2, 02×1" in report


def test_write_tsv_atomic(tmp_path):
    rows = [{"key": "альфа", "value": "альфА", "fires": 2, "text_hits": 2,
             "sections": [("01_a", 2)], "flags": []},
            {"key": "сигма", "value": "сиг\tна", "fires": 0, "text_hits": 0,
             "sections": [], "flags": [pa.FLAG_DEAD, pa.FLAG_LETTERS]}]
    out = tmp_path / "o" / "pron_audit.tsv"
    pa.write_tsv(rows, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t")[:3] == ["key", "value", "fires"]
    assert lines[1].split("\t") == ["альфа", "альфА", "2", "2", "01_a:2", ""]
    assert lines[2].split("\t")[1] == "сиг на"
    assert [p.name for p in out.parent.iterdir()] == ["pron_audit.tsv"]  # no tmp left


# ------------------------------------------------------------- tmp book, end to end

def _section(text_dir: Path, nn: str, slug: str, paras: list[str]) -> None:
    blocks = {"nn": nn, "slug": slug,
              "blocks": [{"type": "paragraph", "text": p} for p in paras]}
    (text_dir / "blocks" / f"{nn}_{slug}.blocks.json").write_text(
        json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    (text_dir / f"{nn}_{slug}.norm.txt").write_text("\n".join(paras) + "\n", encoding="utf-8")


def test_audit_end_to_end_tmp_book(tmp_path, monkeypatch, capsys):
    text = tmp_path / "text"
    (text / "blocks").mkdir(parents=True)
    _section(text, "01", "a", ["Альфа идёт к бета. Альфа снова здесь.", "«Гамма» и бета."])
    _section(text, "02", "b", ["Здесь бета, бета и дельта."])
    (text / "pronounce.yaml").write_text(
        '"Альфа": "АльфА"\n"бета": "бетА"\n"Гамма бета": "ГаммА бетА"\n'
        '"дзета": "дзетА"\n"дельта": "дельтта"\n', encoding="utf-8")
    (text / "stress_watch.yaml").write_text("homographs:\n  - бета\n", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    config = {"text_prep": {"strip_quotes": True}}

    rows = {r["key"]: r for r in pa.audit(config)}
    assert rows["Альфа"]["fires"] == 2 and rows["Альфа"]["sections"] == [("01_a", 2)]
    assert rows["бета"]["fires"] == 4
    assert rows["бета"]["sections"] == [("01_a", 2), ("02_b", 2)]
    assert pa.FLAG_WATCH in rows["бета"]["flags"]
    assert rows["дзета"]["flags"][0] == pa.FLAG_DEAD
    assert pa.FLAG_LETTERS in rows["дельта"]["flags"]
    # «Гамма» и бета: quotes stop the phrase in the raw text; strip_quotes does
    # not join "Гамма" and "бета" either (an "и" stands between) → dead.
    assert rows["Гамма бета"]["fires"] == 0

    assert pa.run(config) == 0
    printed = capsys.readouterr().out
    assert "мёртвая запись" in printed and "меняет буквы — проверить" in printed
    tsv = (out / "pron_audit.tsv").read_text(encoding="utf-8").splitlines()
    assert len(tsv) == 1 + 5


def test_audit_counts_after_prepare_text(tmp_path, monkeypatch):
    """A key that only exists once the quotes are stripped fires in chunks, not in text."""
    text = tmp_path / "text"
    (text / "blocks").mkdir(parents=True)
    _section(text, "01", "a", ["Слово «Альфа» бета здесь."])
    (text / "pronounce.yaml").write_text('"Альфа бета": "АльфА бетА"\n', encoding="utf-8")
    monkeypatch.setattr(paths, "TEXT", text)
    (row,) = pa.audit({"text_prep": {"strip_quotes": True}})
    assert row["fires"] == 1 and row["text_hits"] == 0
    assert pa.FLAG_TEXT_DIFF in row["flags"]
