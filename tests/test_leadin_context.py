"""Context lead-in (previous sentence as carrier): off by default, hash-neutral
when off, headings never get/give context, rows carry the phrase to synth."""
from audiobook import chunker, leadin, pronounce
from audiobook import synth

BASE = {"model": {"name": "qwen3_tts", "variant": "1.7B", "seed": 42,
                  "temperature": 1.0, "language": "ru"},
        "chunking": {"target": 60, "cap": 80, "min_len": 10},
        "pauses_ms": {"sentence": 350, "paragraph": 900, "chapter": 2000},
        "render": {"leadin": {"phrase": "Вот что важно понять.", "max_chars": 30}}}
CTX = {**BASE, "render": {"leadin": {**BASE["render"]["leadin"],
                                     "context": {"mode": "previous", "max_chars": 40}}}}
UNITS = [{"type": "heading", "level": 1, "text": "Заголовок раздела"},
         {"type": "paragraph", "text": "Первое длинное предложение для проверки. "
                                       "Второе длинное предложение здесь стоит. "
                                       "Третье короткое. Четвёртое тоже короткое."}]


def _fake(monkeypatch):
    monkeypatch.setattr(chunker, "latents_hash", lambda c: "lat")
    monkeypatch.setattr(pronounce, "load_table", lambda *a, **k: {})


def test_context_tail():
    assert leadin.context_tail("Раз два. Три четыре.", 40) == "Раз два. Три четыре."
    assert leadin.context_tail("Раз два. Три четыре.", 12) == "Три четыре."
    assert leadin.context_tail("одно очень длинное предложение без точки", 15) == "без точки"
    assert leadin.context_tail("", 40) is None


def test_off_mode_is_fires_and_hash_neutral(monkeypatch):
    _fake(monkeypatch)
    rows = chunker.build_manifest(UNITS, BASE)
    for r in rows:
        assert r["leadin"] == leadin.fires(r["text"], BASE)
        want = chunker.chunk_hash(r["text"], "qwen3_tts-1.7B", 42, 1.0, "ru", "lat",
                                  r["text"], r["leadin"], 0)
        assert r["hash"] == want


def test_context_mode_previous_text_not_headings(monkeypatch):
    _fake(monkeypatch)
    rows = chunker.build_manifest(UNITS, CTX)
    texts = [r["text"] for r in rows]
    assert texts[0] == "Заголовок раздела"
    assert rows[0]["leadin"] == "Вот что важно понять."      # short heading: fixed carrier
    assert rows[1]["leadin"] != texts[0]                       # never borrows from a heading
    for prev, r in zip(rows[1:], rows[2:]):
        assert r["leadin"] and r["leadin"] in " ".join(prev["text"].split())
    base_rows = chunker.build_manifest(UNITS, BASE)
    assert [r["hash"] for r in rows][2:] != [r["hash"] for r in base_rows][2:]


def test_editing_previous_text_requeues_only_next(monkeypatch):
    _fake(monkeypatch)
    a = chunker.build_manifest(UNITS, CTX)
    edited = [UNITS[0], {"type": "paragraph",
                         "text": UNITS[1]["text"].replace("Первое", "Изменённое первое")}]
    b = chunker.build_manifest(edited, CTX)
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x["hash"] != y["hash"]]
    assert changed and max(changed) <= changed[0] + 1


def test_prepare_synth_text_uses_row_leadin():
    row = {"text": "Короткая фраза.", "leadin": "Предыдущая фраза."}
    st, ph = synth.prepare_synth_text(row["text"], BASE, {}, "", synth.row_leadin(row))
    assert ph == "Предыдущая фраза." and st.startswith("Предыдущая фраза. Короткая")
    old_row = {"text": "Короткая фраза."}                       # manifest before this change
    st2, ph2 = synth.prepare_synth_text(old_row["text"], BASE, {}, "", synth.row_leadin(old_row))
    assert ph2 == "Вот что важно понять."
    none_row = {"text": "x" * 100, "leadin": None}
    assert synth.prepare_synth_text(none_row["text"], BASE, {}, "", synth.row_leadin(none_row))[1] is None


def test_passage_select_and_cli():
    from audiobook import passage
    from audiobook.__main__ import _HEAVY, _MAIN_CONFIG_ONLY, build_parser
    rows = [{"n": i, "id": f"{i:04d}"} for i in range(1, 21)]
    assert [r["n"] for r in passage.select(rows, 5, 3)] == [5, 6, 7]
    a = build_parser().parse_args(["passage", "--section", "s", "--tag", "ctx"])
    assert (a.start, a.count, a.tag) == (1, 15, "ctx")
    assert "passage" in _HEAVY and "passage" not in _MAIN_CONFIG_ONLY   # trial configs allowed


def test_config_context_matches_decision():
    from pathlib import Path
    import yaml
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert leadin.context_settings(cfg) == {"max_chars": 60}
