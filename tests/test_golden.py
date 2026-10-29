"""Layer 1: golden set — init / render (fake engine, resume) / compare.
Placeholder text only (no book quotes); everything under tmp_path."""
from __future__ import annotations

import json

import numpy as np
import pytest
import soundfile as sf

from audiobook import golden, paths

SEC = "01_odin"
PARAS = [
    "Первый тестовый абзац достаточной длины, чтобы стать отдельным чанком.",
    "Второй тестовый абзац с меткой АБВ внутри, тоже достаточно длинный для чанка.",
    "Третий тестовый абзац, содержащий слово ЗАГЛУШКА в конце предложения здесь.",
]


def _cfg() -> dict:
    return {
        "model": {"name": "qwen3_tts", "seed": 42, "temperature": 1.0, "language": "ru",
                  "variant": "1.7B"},
        "reference": {"path": "ref/ref1.wav"},
        "chunking": {"target": 80, "cap": 80, "min_len": 10},
        "text_prep": {"strip_quotes": True},
        "pauses_ms": {"sentence": 350, "paragraph": 900, "chapter": 2000, "crossfade": 0},
        "master": {},
    }


class _FakeEngine:
    def __init__(self):
        self.calls = 0

    def synth(self, text, seed, **kw):
        self.calls += 1
        return np.full(2400, 0.1, dtype=np.float32)


@pytest.fixture
def env(monkeypatch, tmp_path):
    text, out = tmp_path / "text", tmp_path / "out"
    (text / "blocks").mkdir(parents=True)
    blocks = {"nn": "01", "slug": "odin",
              "blocks": [{"type": "paragraph", "text": p} for p in PARAS]}
    (text / "blocks" / "01_odin.blocks.json").write_text(
        json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    (text / "01_odin.norm.txt").write_text("\n".join(PARAS) + "\n", encoding="utf-8")
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    mastered = []

    def fake_master(src, dst, config):
        mastered.append((src.name, dst.name))
        dst.write_bytes(b"mp3")
        return {}

    monkeypatch.setattr(golden, "master_wav", fake_master)
    return mastered


def _write_set(entries):
    golden.save_entries(entries)


ENTRIES = [
    {"section": SEC, "match": "Первый тестовый", "why": "one"},
    {"section": SEC, "match": "ЗАГЛУШКА", "why": "two"},
    {"section": SEC, "match": "нет такого текста", "why": "missing"},
]


def test_init_writes_yaml_and_refuses_overwrite(env, capsys):
    assert golden.run_init(_cfg()) == 0
    entries = golden.load_entries()
    # fixed entries come first, probe picks (АБВ / ЗАГЛУШКА tags) follow
    assert [e["match"] for e in entries[:len(golden.FIXED)]] == [e["match"] for e in golden.FIXED]
    picked = entries[len(golden.FIXED):]
    assert picked and all(e["section"] == SEC and e["why"] for e in picked)
    resolved = golden.resolve(picked, _cfg())
    assert len(resolved) == len(picked)  # every generated match finds its chunk

    golden.golden_path().write_text("- {section: x, match: y, why: z}\n", encoding="utf-8")
    assert golden.run_init(_cfg()) == 1
    assert golden.load_entries() == [{"section": "x", "match": "y", "why": "z"}]
    assert golden.run_init(_cfg(), force=True) == 0
    assert len(golden.load_entries()) > 1


def test_render_with_fake_engine_and_resume(env, capsys):
    _write_set(ENTRIES)
    assert golden.run_render(_cfg(), "base", engine=_FakeEngine()) == 0
    d = paths.OUT / "golden" / "base"
    wavs = sorted(d.glob("*.wav"))
    assert len(wavs) == 2 and all(len(w.stem) == 16 for w in wavs)
    data, sr = sf.read(str(wavs[0]))
    assert sr == 24000 and len(data) == 2400
    assert not list(d.glob("*.part"))

    rows = (d / "index.tsv").read_text(encoding="utf-8").splitlines()
    assert rows[0].split("\t") == ["n", "section", "chunk", "hash16", "why", "start", "text"]
    assert len(rows) == 3
    first = rows[1].split("\t")
    assert first[0] == "1" and first[1] == SEC and first[4] == "one" and first[5] == "0:00"
    assert rows[2].split("\t")[5] == "0:01"  # 0.1 s + 1 s gap, rounded

    snap = json.loads((d / "settings.json").read_text(encoding="utf-8"))
    assert snap["model"]["variant"] == "1.7B" and snap["temperature"] == 1.0
    assert snap["chunking"]["cap"] == 80 and snap["text_prep"]["strip_quotes"] is True
    assert snap["pauses_ms"]["paragraph"] == 900 and snap["reference"]["path"] == "ref/ref1.wav"
    assert [e["match"] for e in snap["entries"]] == ["Первый тестовый", "ЗАГЛУШКА"]

    assert (d / "golden.mp3").exists() and not (d / "golden.wav").exists()
    assert env == [("golden.wav", "golden.mp3")]

    # resume: a second run synthesises nothing
    eng = _FakeEngine()
    assert golden.run_render(_cfg(), "base", engine=eng) == 0
    assert eng.calls == 0
    # a config change (temperature) changes the hash → new files, old ones stay
    cfg = _cfg()
    cfg["model"]["temperature"] = 0.8
    assert golden.run_render(cfg, "base", engine=eng) == 0
    assert eng.calls == 2 and len(list(d.glob("*.wav"))) == 4


def test_render_failed_chunk_stays_uncached(env):
    _write_set(ENTRIES[:1])

    class Failing:
        def synth(self, text, seed, **kw):
            return None

    assert golden.run_render(_cfg(), "bad", engine=Failing()) == 1
    assert not list((paths.OUT / "golden" / "bad").glob("*.wav"))


def test_render_rejects_bad_tag(env):
    _write_set(ENTRIES)
    with pytest.raises(SystemExit):
        golden.run_render(_cfg(), "../evil", engine=_FakeEngine())


def test_compare_pairs_files(env, capsys):
    _write_set(ENTRIES)
    golden.run_render(_cfg(), "a", engine=_FakeEngine())
    cfg_b = _cfg()
    cfg_b["model"]["temperature"] = 0.7
    golden.run_render(cfg_b, "b", engine=_FakeEngine())
    assert golden.run_compare(_cfg(), "a", "b") == 0
    d = paths.OUT / "golden" / "compare_a_b"
    # review.py pairs NN_A / NN_B: the files are named by side, not by tag
    assert sorted(p.name for p in d.glob("*.wav")) == ["01_A.wav", "01_B.wav", "02_A.wav", "02_B.wav"]
    assert (d / "compare.mp3").exists() and not (d / "compare.wav").exists()
    rows = [r.split("\t") for r in (d / "index.tsv").read_text(encoding="utf-8").splitlines()]
    assert rows[0][:9] == ["n", "file_a", "file_b", "section", "chunk", "why", "text",
                           "tag_a", "tag_b"]
    assert len(rows) == 3
    r1 = dict(zip(rows[0], rows[1]))
    assert (r1["n"], r1["file_a"], r1["file_b"], r1["tag_a"], r1["tag_b"]) == (
        "1", "01_A.wav", "01_B.wav", "a", "b")
    assert r1["section"] == SEC and r1["why"] == "one" and r1["chunk"]
    assert r1["text"].startswith("Первый тестовый") and len(r1["hash_a"]) == 16
    assert r1["hash_a"] != r1["hash_b"]                        # temperature differs
    # A, 0.6 s, B, 1.5 s per item: second item starts at 0.1+0.6+0.1+1.5 = 2.3 s
    assert dict(zip(rows[0], rows[2]))["start"] == "0:02"


def test_compare_skips_entry_without_wav(env, capsys):
    _write_set(ENTRIES)
    golden.run_render(_cfg(), "a", engine=_FakeEngine())
    golden.run_render(_cfg(), "b", engine=_FakeEngine())
    snap = json.loads((paths.OUT / "golden" / "b" / "settings.json").read_text(encoding="utf-8"))
    (paths.OUT / "golden" / "b" / f"{snap['entries'][0]['hash16']}.wav").unlink()
    assert golden.run_compare(_cfg(), "a", "b") == 0
    assert "ПРОПУСК" in capsys.readouterr().out
    d = paths.OUT / "golden" / "compare_a_b"
    assert sorted(p.name for p in d.glob("*.wav")) == ["01_A.wav", "01_B.wav"]


def test_compare_needs_rendered_tags(env):
    with pytest.raises(SystemExit):
        golden.run_compare(_cfg(), "nope", "nada")


def test_compare_review_page_shows_tag_captions(env):
    from audiobook import review
    _write_set(ENTRIES)
    golden.run_render(_cfg(), "a", engine=_FakeEngine())
    cfg_b = _cfg()
    cfg_b["model"]["temperature"] = 0.7
    golden.run_render(cfg_b, "b", engine=_FakeEngine())
    golden.run_compare(_cfg(), "a", "b")
    d = paths.OUT / "golden" / "compare_a_b"
    kind, groups = review.collect(d)
    assert kind == "golden" and [len(g) for g in groups] == [2, 2]
    a, b = groups[0]
    assert (a["file"], b["file"]) == ("01_A.wav", "01_B.wav")
    assert a["name"] == "01 · A · a" and b["name"] == "01 · B · b"
    assert a["meta"]["tag"] == "a" and a["meta"]["why"] == "one" and a["meta"]["section"] == SEC
    assert a["meta"]["text"].startswith("Первый тестовый") and len(a["meta"]["hash"]) == 16


def test_compare_moves_previous_files_to_old_never_deletes(env, capsys):
    _write_set(ENTRIES)
    golden.run_render(_cfg(), "a", engine=_FakeEngine())
    golden.run_render(_cfg(), "b", engine=_FakeEngine())
    d = paths.OUT / "golden" / "compare_a_b"
    d.mkdir(parents=True)
    for n in ("01_a.wav", "01_b.wav", "07_A.wav"):              # old naming + a 7th pair
        sf.write(str(d / n), np.zeros(240, dtype=np.float32), 24000)
    (d / "index.tsv").write_text("old\n", encoding="utf-8")
    (d / "review.html").write_text("old page", encoding="utf-8")
    (d / "notes.txt").write_text("keep", encoding="utf-8")   # not ours: stays put
    assert golden.run_compare(_cfg(), "a", "b") == 0
    (old,) = [p for p in d.iterdir() if p.is_dir()]
    assert old.name.startswith("_old_")
    assert sorted(p.name for p in old.iterdir()) == [
        "01_a.wav", "01_b.wav", "07_A.wav", "index.tsv", "review.html"]
    assert (old / "review.html").read_text(encoding="utf-8") == "old page"
    assert sorted(p.name for p in d.glob("*.wav")) == ["01_A.wav", "01_B.wav", "02_A.wav", "02_B.wav"]
    assert (d / "notes.txt").exists() and "перенесены" in capsys.readouterr().out
    # a second compare archives the first one into another _old_ folder
    assert golden.run_compare(_cfg(), "a", "b") == 0
    olds = sorted(p for p in d.iterdir() if p.is_dir())
    assert len(olds) == 2 and all(p.name.startswith("_old_") for p in olds)
    from audiobook import review
    kind, groups = review.collect(d)                          # _old_ never shows on the page
    assert kind == "golden" and len(groups) == 2


def test_render_workers_option_has_no_effect(env, capsys, monkeypatch):
    _write_set(ENTRIES[:1])
    eng = _FakeEngine()
    assert golden.run_render(_cfg(), "w", workers=4, engine=eng) == 0
    out = capsys.readouterr().out
    assert "--workers 4 игнорируется" in out and eng.calls == 1
    # the real engine path builds ONE worker whatever --workers says
    seen = {}
    import audiobook.synth as synth_mod
    import audiobook.worker as worker_mod

    def fake_worker_config(config, workers):
        seen["workers"] = workers
        return {}

    class FakeTimeout:
        def __init__(self, wcfg, timeout_s, start_timeout_s=None):
            pass

        def __enter__(self):
            return _FakeEngine()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(synth_mod, "worker_config", fake_worker_config)
    monkeypatch.setattr(worker_mod, "TimeoutSynth", FakeTimeout)
    cfg = _cfg()
    cfg["model"]["temperature"] = 0.5                          # new hash → something to render
    assert golden.run_render(cfg, "w", workers=3) == 0
    assert seen["workers"] == 1 and "--workers 3 игнорируется" in capsys.readouterr().out
    assert golden.run_render(cfg, "w", workers=1) == 0
    assert "игнорируется" not in capsys.readouterr().out
