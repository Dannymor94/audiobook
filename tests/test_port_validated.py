"""Layer 1: settings validated by ear in throwaway scripts, ported into the
pipeline — model variant (1.7B), chunk length cap, text_prep (quotes / final
period), heading split, preview render (--first). No models, placeholder text
only (no book quotes)."""
from __future__ import annotations

import json

import numpy as np
import pytest
import soundfile as sf

from audiobook import paths, voicecfg

_BASE = {
    "model": {"name": "qwen3_tts", "seed": 42, "temperature": 1.0, "language": "ru"},
    "reference": {"path": "ref/ref1.wav"},
}


def _cfg(**extra) -> dict:
    cfg = json.loads(json.dumps(_BASE))
    for k, v in extra.items():
        if k == "variant":
            cfg["model"]["variant"] = v
        else:
            cfg[k] = v
    return cfg


# ── variant: model id, hub dir, latents file ─────────────────────────────────

def test_model_id_06b_keeps_old_name():
    """0.6B (explicit or default) hashes exactly as before the variant key."""
    assert voicecfg.model_id(_cfg()) == "qwen3_tts"
    assert voicecfg.model_id(_cfg(variant="0.6B")) == "qwen3_tts"
    assert voicecfg.model_id(_cfg(variant="1.7B")) == "qwen3_tts-1.7B"


def test_latents_path_per_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    assert voicecfg.latents_path(_cfg()) == tmp_path / "ref" / "ref1.latents.pt"
    assert voicecfg.latents_path(_cfg(variant="1.7B")) == tmp_path / "ref" / "ref1.latents_1.7b.pt"


def test_hub_dir_per_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "MODELS", tmp_path)
    assert voicecfg.hub_dir("1.7B").name == "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base"
    assert voicecfg.hub_dir("0.6B").parent == tmp_path / "hf" / "hub"


def test_load_model_1_7b_missing_weights_offline(monkeypatch, tmp_path):
    import audiobook.synth as synth_mod
    monkeypatch.setattr(synth_mod, "_model", None)
    monkeypatch.setattr(paths, "MODELS", tmp_path / "models")
    with pytest.raises(FileNotFoundError, match="1.7B-Base"):
        synth_mod.load_model("cpu", "1.7B")


# ── text_prep ─────────────────────────────────────────────────────────────────

_PREP = {"strip_quotes": True, "ensure_terminal": True}


def test_prepare_text_off_by_default():
    assert voicecfg.prepare_text("«Тест» без точки", _cfg()) == "«Тест» без точки"


@pytest.mark.parametrize("src,want", [
    ("«Тестовая фраза»", "Тестовая фраза."),
    ("Слово „один“ и “два”", "Слово один и два."),
    ("Уже есть точка.", "Уже есть точка."),
    ("Вопрос?", "Вопрос?"),
    ("Двоеточие:", "Двоеточие:"),
    ("Многоточие…", "Многоточие…"),
    ("«Фраза с точкой.»", "Фраза с точкой."),
    ("", ""),
])
def test_prepare_text_strip_and_terminal(src, want):
    assert voicecfg.prepare_text(src, _cfg(text_prep=_PREP)) == want


def test_prepare_text_keeps_quote_as_terminal_when_not_stripping():
    cfg = _cfg(text_prep={"ensure_terminal": True})
    assert voicecfg.prepare_text("«Тест»", cfg) == "«Тест»"
    assert voicecfg.prepare_text("Тест", cfg) == "Тест."


def test_prepare_synth_text_applies_prep_before_leadin():
    from audiobook.synth import prepare_synth_text
    cfg = _cfg(text_prep=_PREP,
               render={"leadin": {"phrase": "Несущая фраза.", "max_chars": 55}})
    synth_text, phrase = prepare_synth_text("«Тест»", cfg, {}, " .")
    assert phrase == "Несущая фраза."
    assert synth_text == "Несущая фраза. Тест."  # no quotes, period, no sentinel


# ── hash consistency ──────────────────────────────────────────────────────────

def _one_hash(text: str, cfg: dict) -> str:
    from audiobook.chunker import build_manifest
    return build_manifest([{"type": "paragraph", "text": text}], cfg)[0]["hash"]


def test_hash_unchanged_without_new_keys():
    """An untouched 0.6B config must keep every existing hash."""
    from audiobook.chunker import chunk_hash, latents_hash
    text = "Обычное предложение для проверки хеша без изменений."
    cfg = _cfg()
    m = cfg["model"]
    want = chunk_hash(text, "qwen3_tts", m["seed"], m["temperature"], m["language"],
                      latents_hash(cfg))
    assert _one_hash(text, cfg) == want


def test_variant_changes_every_hash():
    text = "Обычное предложение для проверки хеша без изменений."
    assert _one_hash(text, _cfg()) != _one_hash(text, _cfg(variant="1.7B"))


def test_text_prep_rehashes_only_affected_chunks():
    plain = "Обычное предложение, которое уже заканчивается точкой."
    quoted = "Предложение со словом «цитата» внутри и точкой в конце."
    prep = _cfg(text_prep=_PREP)
    assert _one_hash(plain, _cfg()) == _one_hash(plain, prep)
    assert _one_hash(quoted, _cfg()) != _one_hash(quoted, prep)


# ── chunk length limits ───────────────────────────────────────────────────────

_LONG = " ".join(
    f"Это тестовое предложение номер {w}, в нём есть запятая и немного слов."
    for w in ("один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь")
)


def test_chunking_cap_from_config():
    from audiobook.chunker import build_chunks
    units = [{"type": "paragraph", "text": _LONG}]
    cfg = _cfg(chunking={"target": 180, "cap": 180, "min_len": 40})
    chunks = build_chunks(units, cfg)
    assert all(len(c["text"]) <= 180 for c in chunks)
    assert " ".join(c["text"] for c in chunks).split() == _LONG.split()


def test_chunking_defaults_unchanged():
    from audiobook.chunker import CAP, build_chunks
    units = [{"type": "paragraph", "text": _LONG}]
    assert build_chunks(units) == build_chunks(units, _cfg())
    assert any(len(c["text"]) > 180 for c in build_chunks(units))
    assert all(len(c["text"]) <= CAP for c in build_chunks(units))


def test_long_sentence_split_under_cap():
    from audiobook.chunker import Limits, chunk_prose
    sent = ("Очень длинное тестовое предложение, которое тянется, и тянется, "
            "и снова тянется, потому что в нём много частей, разделённых запятыми, "
            "и никакой точки до самого конца нет, а слова всё идут и идут дальше.")
    assert len(sent) > 180
    parts = chunk_prose(sent, Limits(180, 180, 40))
    assert len(parts) > 1 and all(len(p) <= 180 for p in parts)


# ── heading split ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,want", [
    ("Глава седьмая. Простой пример: «Тестовая цитата»",
     ("Глава седьмая.", "Простой пример:", "«Тестовая цитата»")),
    ("Глава пятая. Схема: путь вглубь", ("Глава пятая.", "Схема:", "путь вглубь")),
    ("Глава вторая. Просто название", ("Глава вторая.", None, "Просто название")),
    ("Упражнение: найди своё", (None, "Упражнение:", "найди своё")),
    ("Обычный заголовок", (None, None, "Обычный заголовок")),
    ("Фраза «внутри: кавычек» тут", (None, None, "Фраза «внутри: кавычек» тут")),
    ("Время 10:30 утра", (None, None, "Время 10:30 утра")),
])
def test_split_heading(text, want):
    from audiobook.chunker import split_heading
    assert split_heading(text) == want


def test_heading_chunks_with_pauses():
    from audiobook.chunker import build_chunks
    units = [{"type": "heading", "level": 1,
              "text": "Глава седьмая. Простой пример: «Тестовая цитата»"},
             {"type": "paragraph", "text": "Короткий абзац после заголовка для проверки."}]
    cfg = _cfg(pauses_ms={"heading_number": 900, "heading_colon": 400})
    got = [(c["text"], c["pause_after_ms"]) for c in build_chunks(units, cfg)][:3]
    assert got == [("Глава седьмая.", 900), ("Простой пример:", 400),
                   ("«Тестовая цитата»", 1500)]


def test_heading_whole_without_config_keys():
    from audiobook.chunker import build_chunks
    text = "Глава седьмая. Простой пример: «Тестовая цитата»"
    units = [{"type": "heading", "level": 1, "text": text}]
    assert build_chunks(units, _cfg())[0]["text"] == text
    assert build_chunks(units)[0]["text"] == text


def test_heading_only_number_split():
    from audiobook.chunker import build_chunks
    units = [{"type": "heading", "level": 2,
              "text": "Глава седьмая. Простой пример: «Тестовая цитата»"}]
    cfg = _cfg(pauses_ms={"heading_number": 900})
    got = [(c["text"], c["pause_after_ms"]) for c in build_chunks(units, cfg)]
    assert got[0] == ("Глава седьмая.", 900)
    assert got[1][0] == "Простой пример: «Тестовая цитата»"


# ── worker config guard ───────────────────────────────────────────────────────

def test_worker_config_variant_and_latents(monkeypatch, tmp_path):
    from audiobook.synth import worker_config
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    cfg = _cfg(variant="1.7B")
    with pytest.raises(SystemExit, match="латентов"):
        worker_config(cfg)
    (tmp_path / "ref").mkdir()
    (tmp_path / "ref" / "ref1.latents_1.7b.pt").write_bytes(b"x")
    w = worker_config(cfg, 2)
    assert w["variant"] == "1.7B"
    assert w["latents_path"].endswith("ref1.latents_1.7b.pt")
    with pytest.raises(SystemExit, match="1.7B"):
        worker_config(cfg, 3)


def test_worker_config_06b_unlimited_workers(monkeypatch, tmp_path):
    from audiobook.synth import worker_config
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    (tmp_path / "ref").mkdir()
    (tmp_path / "ref" / "ref1.latents.pt").write_bytes(b"x")
    assert worker_config(_cfg(), 4)["variant"] == "0.6B"


# ── preview: --first N ────────────────────────────────────────────────────────

class _FakeEngine:
    def __init__(self):
        self.calls = 0

    def synth(self, text, seed, **kw):
        self.calls += 1
        return np.full(2400, 0.1, dtype=np.float32)


def _section(tmp_path, n=5):
    from audiobook.synth import _write_manifest
    sec = tmp_path / "sec"
    sec.mkdir()
    rows = [{"id": f"{i:04d}", "n": i, "text": f"Тестовый чанк номер {i}.",
             "hash": f"{i:040x}", "seed": 42, "pause_after_ms": 100,
             "status": "pending", "locked": False, "seed_override": None,
             "duration_ms": None} for i in range(1, n + 1)]
    _write_manifest(sec / "manifest.jsonl", rows)
    return sec


def test_render_first_n_only(tmp_path):
    from audiobook.synth import _read_manifest, render_section
    sec = _section(tmp_path)
    eng = _FakeEngine()
    done, skipped, timed_out, _ = render_section(eng, sec, _cfg(), first=2)
    assert (done, skipped, timed_out) == (2, 0, 0)
    status = [r["status"] for r in _read_manifest(sec / "manifest.jsonl")]
    assert status == ["done", "done", "pending", "pending", "pending"]


def test_plan_parallel_respects_first(tmp_path):
    from audiobook.synth import _plan_parallel, _read_manifest
    sec = _section(tmp_path)
    rows = _read_manifest(sec / "manifest.jsonl")
    groups, _ = _plan_parallel(rows[:3], sec / "chunks", 2)
    assert sorted(r["id"] for g in groups for r in g) == ["0001", "0002", "0003"]


def test_assemble_preview_separate_file(tmp_path):
    from audiobook.assemble import assemble_section
    from audiobook.synth import render_section
    sec = _section(tmp_path)
    render_section(_FakeEngine(), sec, _cfg(), first=2)
    cfg = _cfg(pauses_ms={"crossfade": 0})
    out, stats = assemble_section(sec, cfg, first=2)
    assert out.name == "preview_first2.wav" and len(stats) == 2
    assert not (sec / "section.wav").exists()
    with pytest.raises(SystemExit, match="pending"):
        assemble_section(sec, cfg)  # whole section still refuses
    data, sr = sf.read(str(out))
    assert sr == 24000 and len(data) > 0


# ── chunk --section ───────────────────────────────────────────────────────────

def _write_section(text_dir, nn, slug, para):
    (text_dir / "blocks").mkdir(parents=True, exist_ok=True)
    blocks = {"nn": nn, "slug": slug, "blocks": [{"type": "paragraph", "text": para}]}
    (text_dir / "blocks" / f"{nn}_{slug}.blocks.json").write_text(
        json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    (text_dir / f"{nn}_{slug}.norm.txt").write_text(para + "\n", encoding="utf-8")


def test_chunk_single_section(monkeypatch, tmp_path):
    from audiobook import chunker
    monkeypatch.setattr(paths, "TEXT", tmp_path / "text")
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    para = "Тестовый абзац достаточной длины, чтобы секция не считалась пустой."
    _write_section(tmp_path / "text", "01", "odin", para)
    _write_section(tmp_path / "text", "02", "dva", para)
    assert chunker.run(_cfg(), "02_dva") == 0
    secs = tmp_path / "out" / "sections"
    assert (secs / "02_dva" / "manifest.jsonl").exists()
    assert not (secs / "01_odin").exists()
    with pytest.raises(SystemExit):
        chunker.run(_cfg(), "99_net")
