"""Decisions page discovery/build and apply (no models, tmp files only)."""
import json
from pathlib import Path

import yaml

from audiobook import decisions

CFG_TEXT = """model:
  name: qwen3_tts
  temperature: 1.0               # comment kept
render:
  leadin:
    context: {mode: "off", max_chars: 60}
pauses_ms:
  sentence: 350
  by_end: {"?": 550, "…": 700}   # trial
qc:
  takes:
    count: 3
"""
PRON_TEXT = """# header comment
"тебя": "тебЯ"   # keep
"сознание": "соЗнание"     # old
"сознания": "соЗнания"     # old
"Сознание": "СоЗнание"     # old
"найди": "найДи"
"Найди": "НайДи"
"""


def _apply(dec):
    cfg = yaml.safe_load(CFG_TEXT)
    table = {k: v for k, v in yaml.safe_load(PRON_TEXT).items()}
    return decisions.apply(dec, CFG_TEXT, PRON_TEXT, cfg, table)


def test_apply_config_keys_keep_comments():
    c, p, ch = _apply({"temperature": "0.9", "context": "previous", "takes": "off", "by_end": "longer"})
    y = yaml.safe_load(c)
    assert y["model"]["temperature"] == 0.9 and "# comment kept" in c
    assert y["render"]["leadin"]["context"]["mode"] == "previous"
    assert y["qc"]["takes"]["count"] == 1
    assert y["pauses_ms"]["by_end"] == {"?": 700, "…": 850}
    assert p == PRON_TEXT and len(ch) == 4


def test_apply_noop_when_same():
    c, p, ch = _apply({"temperature": "1.0", "context": "off", "takes": "on", "by_end": "keep"})
    assert (c, p, ch) == (CFG_TEXT, PRON_TEXT, [])


def test_by_end_off_and_shorter_floor():
    c, _p, _ = _apply({"by_end": "off"})
    assert yaml.safe_load(c)["pauses_ms"]["by_end"] == {}
    c, _p, _ = _apply({"by_end": "shorter"})
    assert yaml.safe_load(c)["pauses_ms"]["by_end"] == {"?": 450, "…": 600}


def test_pron_vowel_choice_propagates_to_forms():
    _c, p, ch = _apply({"pron": {"сознание": "сознАние"}})
    t = yaml.safe_load(p)
    assert t["сознание"] == "сознАние" and t["сознания"] == "сознАния" and t["Сознание"] == "СознАние"
    assert t["тебя"] == "тебЯ" and "# header comment" in p and "# keep" in p
    assert len(ch) == 3


def test_pron_remove_family_and_single():
    _c, p, ch = _apply({"pron": {"Найди": "-"}})
    t = yaml.safe_load(p)
    assert "Найди" not in t and "найди" not in t and t["сознание"] == "соЗнание"
    _c, p, _ = _apply({"pron": {"Найди": "НайдИ"}})
    t = yaml.safe_load(p)
    assert t["Найди"] == "НайдИ" and t["найди"] == "найдИ"


def test_stress_index():
    assert decisions.stress_index("сознание", "сознАние") == 4
    assert decisions.stress_index("сознание", "соЗнание") is None      # consonant → no family
    assert decisions.stress_index("Отзывы", "Оотзывы") is None


def test_apply_refuses_unknown_place():
    cfg = yaml.safe_load(CFG_TEXT)
    try:
        decisions.apply({"temperature": "0.9"}, "model: {}\n", "", cfg, {})
        raise AssertionError("must refuse")
    except SystemExit as e:
        assert "temperature" in str(e)


def test_build_page_copies_media(tmp_path, monkeypatch):
    out = tmp_path / "out"
    g = out / "golden"
    (g / "compare_a_b").mkdir(parents=True)
    for tag, t in (("a", 1.0), ("b", 0.9)):
        (g / tag).mkdir()
        (g / tag / "settings.json").write_text(json.dumps({"temperature": t}), encoding="utf-8")
    for n in ("01", "02"):
        for s in "AB":
            (g / "compare_a_b" / f"{n}_{s}.wav").write_bytes(b"RIFF")
    pt = out / "pron_test" / "07_x_0032_сознание"
    pt.mkdir(parents=True)
    (pt / "meta.tsv").write_text("n\tchunk\tvariant\ttake\tstart\tsynth_text\n"
                                 "1\t0032\t-\t1\t0:00\tт\n2\t0032\tсознАние\t1\t0:05\tт\n", encoding="utf-8")
    for n in (1, 2):
        (pt / f"{n}.wav").write_bytes(b"RIFF")
    ps = out / "passage"
    for tag, mode in (("base", "off"), ("ctx", "previous")):
        (ps / tag).mkdir(parents=True)
        (ps / tag / "passage.mp3").write_bytes(b"ID3")
        (ps / tag / "settings.json").write_text(
            json.dumps({"leadin": {"context": {"mode": mode}}}), encoding="utf-8")
    from audiobook import pronounce
    monkeypatch.setattr(pronounce, "load_table", lambda *a, **k: {"сознание": "соЗнание"})
    page = decisions.build({"model": {"temperature": 1.0}}, out)
    h = page.read_text(encoding="utf-8")
    assert 'data-key="temperature"' in h and 'data-key="pron:сознание"' in h and 'data-key="context"' in h
    assert "(сейчас)" in h
    assert (out / "decisions" / "media" / "temperature" / "01_A.wav").exists()
    assert (out / "decisions" / "media" / "context" / "B_context.mp3").exists()
    assert (g / "compare_a_b" / "01_A.wav").exists()                     # copied, not moved


def test_cli_wires_decisions():
    from audiobook.__main__ import build_parser
    a = build_parser().parse_args(["decisions", "apply", "d.json", "--dry-run"])
    assert (a.decisions_cmd, a.file, a.dry_run) == ("apply", "d.json", True)
