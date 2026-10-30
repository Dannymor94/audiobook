"""Pauses by final punctuation and per-section pause overrides (no models)."""
from audiobook import chunker


def test_end_mark():
    assert chunker.end_mark("Правда?") == "?"
    assert chunker.end_mark("Он сказал «стоп!»") == "!"
    assert chunker.end_mark("И тогда...") == "…"
    assert chunker.end_mark("И тогда…)") == "…"
    assert chunker.end_mark("Вот так:") == ":"
    assert chunker.end_mark("Обычная фраза.") == "."
    assert chunker.end_mark("без знака") == ""


def test_sentence_pause():
    by_end = {"?": 550, "…": 700}
    assert chunker.sentence_pause("Правда?", 350, by_end) == 550
    assert chunker.sentence_pause("Точка.", 350, by_end) == 350
    assert chunker.sentence_pause("Многоточие...", 350, by_end) == 700
    assert chunker.sentence_pause("Правда?", 350, {}) == 350


def test_section_config_merges_only_for_that_section():
    cfg = {"pauses_ms": {"sentence": 350, "paragraph": 900,
                         "sections": {"22_x": {"sentence": 600}}}}
    assert chunker.section_config(cfg, "22_x")["pauses_ms"]["sentence"] == 600
    assert chunker.section_config(cfg, "22_x")["pauses_ms"]["paragraph"] == 900
    assert chunker.section_config(cfg, "23_y") is cfg
    assert chunker.section_config(cfg, None) is cfg
    assert cfg["pauses_ms"]["sentence"] == 350                # original untouched


def test_build_chunks_uses_by_end_inside_paragraph_only():
    text = ("Первая фраза здесь стоит? " * 6 + "Вторая фраза здесь стоит. " * 6).strip()
    units = [{"type": "paragraph", "text": text}]
    cfg = {"chunking": {"target": 60, "cap": 80, "min_len": 10},
           "pauses_ms": {"sentence": 350, "paragraph": 900, "chapter": 2000,
                         "by_end": {"?": 550}}}
    chunks = chunker.build_chunks(units, cfg)
    assert len(chunks) > 2
    inner = chunks[:-1]
    for c in inner:
        want = 550 if chunker.end_mark(c["text"]) == "?" else 350
        assert c["pause_after_ms"] == want
    assert chunks[-1]["pause_after_ms"] == 2000              # section end wins
    assert any(c["pause_after_ms"] == 550 for c in inner)


def test_pauses_not_in_hash(monkeypatch):
    """Changing pauses must never re-render: same hashes with and without by_end."""
    from audiobook import pronounce
    monkeypatch.setattr(chunker, "latents_hash", lambda c: "lat")
    monkeypatch.setattr(pronounce, "load_table", lambda *a, **k: {})
    text = ("Первая фраза здесь стоит? " * 6 + "Вторая фраза здесь стоит. " * 6).strip()
    units = [{"type": "paragraph", "text": text}]
    base = {"model": {"name": "qwen3_tts", "variant": "1.7B", "seed": 42,
                      "temperature": 1.0, "language": "ru"},
            "chunking": {"target": 60, "cap": 80, "min_len": 10},
            "pauses_ms": {"sentence": 350, "paragraph": 900, "chapter": 2000}}
    alt = {**base, "pauses_ms": {**base["pauses_ms"], "by_end": {"?": 900}, "sentence": 500}}
    a = chunker.build_manifest(units, base)
    b = chunker.build_manifest(units, alt)
    assert [r["hash"] for r in a] == [r["hash"] for r in b]
    assert [r["pause_after_ms"] for r in a] != [r["pause_after_ms"] for r in b]
