"""Layer 1: review-round fixes in ref_scout (decode cache, no overwrite, hard
cut bounds), ref_compare (render tag, hash16 chunk names) and suspects (stale
index refused). No models, no ffmpeg; placeholder text only."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest
import soundfile as sf

from audiobook import paths


def _cfg(**over) -> dict:
    cfg = {"model": {"name": "qwen3_tts", "seed": 42, "temperature": 1.0, "language": "ru",
                     "variant": "1.7B"},
           "reference": {"path": "ref/ref1.wav", "ref_text_path": "ref/ref1.txt"},
           "pauses_ms": {"crossfade": 0}, "render": {"timeout_retries": 0}, "master": {}}
    cfg.update(over)
    return cfg


# ── ref_scout ─────────────────────────────────────────────────────────────────

def test_scout_source_key_tracks_path_size_mtime(tmp_path):
    from audiobook.ref_scout import source_key
    a, b = tmp_path / "a.m4a", tmp_path / "b.m4a"
    a.write_bytes(b"one")
    b.write_bytes(b"one")
    k = source_key(a)
    assert len(k) == 10 and source_key(a) == k
    assert source_key(b) != k                                 # another recording
    os.utime(a, ns=(10**18, 10**18))
    assert source_key(a) != k                                 # re-exported in place
    k2 = source_key(a)
    a.write_bytes(b"longer")
    os.utime(a, ns=(10**18, 10**18))
    assert source_key(a) != k2                                # size differs


def test_scout_free_name_never_reuses_a_candidate(tmp_path):
    from audiobook.ref_scout import free_name
    assert free_name(tmp_path, "scout_0130") == "scout_0130"
    (tmp_path / "scout_0130.wav").write_bytes(b"x")
    assert free_name(tmp_path, "scout_0130") == "scout_0130_2"
    (tmp_path / "scout_0130_2.txt").write_text("подтверждён", encoding="utf-8")
    assert free_name(tmp_path, "scout_0130") == "scout_0130_3"
    (tmp_path / "scout_0200.draft.txt").write_text("черновик", encoding="utf-8")
    assert free_name(tmp_path, "scout_0200") == "scout_0200_2"


def test_scout_snap_never_crosses_neighbour_segment():
    from audiobook.ref_scout import snap_to_silence
    sr = 1000
    rng = np.random.default_rng(1)
    y = rng.normal(0, 0.3, 4 * sr).astype(np.float32)
    y[1000:1100] = 0.0                    # pause inside the PREVIOUS segment (ends 1.2)
    y[2600:2700] = 0.0                    # pause inside the NEXT segment (starts 2.5)
    t, _ = snap_to_silence(y, sr, 1.5, "start")
    assert t < 1.2                                            # unbounded: reaches back
    t, _ = snap_to_silence(y, sr, 1.5, "start", bound=1.2)
    assert t >= 1.2
    t, _ = snap_to_silence(y, sr, 2.3, "end")
    assert t > 2.5
    t, _ = snap_to_silence(y, sr, 2.3, "end", bound=2.5)
    assert t <= 2.5
    t, _ = snap_to_silence(y, sr, 1.5, "start", bound=float("inf"))   # empty window: stay
    assert t == 1.5


def test_scout_run_bounds_names_and_cache(tmp_path, monkeypatch):
    from audiobook import ref_scout
    from audiobook.ref_scout import Seg
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    ref = tmp_path / "ref"
    ref.mkdir()
    sf.write(str(ref / "ref1.wav"), np.zeros(48000, dtype=np.float32), 24000)   # 2 s
    (ref / "ref1.txt").write_text("абвг", encoding="utf-8")                      # 2 chars/s
    src = tmp_path / "live.m4a"
    src.write_bytes(b"placeholder recording")

    decoded = []

    def fake_decode(s, out, sr):
        decoded.append(out.name)
        rng = np.random.default_rng(2)
        y = rng.normal(0, 0.3, 20 * sr).astype(np.float32)
        y[int(15.3 * sr):int(15.5 * sr)] = 0.0  # deep pause INSIDE the next segment
        sf.write(str(out), y, sr)

    segs = [Seg(i * 5.0, i * 5.0 + 5.0, "абвгдабвгд") for i in range(4)]       # 2 chars/s
    monkeypatch.setattr(ref_scout, "_decode", fake_decode)
    monkeypatch.setattr(ref_scout, "_segments", lambda wav: segs)
    monkeypatch.setattr(ref_scout, "_f0", lambda y: np.full(100, 120.0))
    monkeypatch.setattr(ref_scout, "_ff", lambda: "ffmpeg-stub")
    monkeypatch.setattr(ref_scout.subprocess, "run", lambda *a, **k: None)      # mp3 encode

    assert ref_scout.run(_cfg(), str(src), k=1) == 0
    key = ref_scout.source_key(src)
    assert sorted(decoded) == [f"source_{key}_16k.wav", f"source_{key}_24k.wav"]
    cdir = tmp_path / "ref" / "candidates"
    first = cdir / "scout_0000.wav"
    clip, sr = sf.read(str(first))
    assert len(clip) <= 15 * sr          # the cut stops at the next segment's start (15 s)
    original = first.read_bytes()

    assert ref_scout.run(_cfg(), str(src), k=1) == 0
    assert len(decoded) == 2                                  # cached decode reused
    assert first.read_bytes() == original                     # never overwritten
    assert (cdir / "scout_0000_2.wav").exists() and (cdir / "scout_0000_2.draft.txt").exists()
    assert not list(cdir.glob("*.part"))

    os.utime(src, ns=(10**18, 10**18))                        # the recording changed
    ref_scout.run(_cfg(), str(src), k=1)
    assert len(decoded) == 4 and ref_scout.source_key(src) != key


# ── ref_compare ───────────────────────────────────────────────────────────────

def _cand(tmp_path):
    wav, txt = tmp_path / "a.wav", tmp_path / "a.txt"
    wav.write_bytes(b"audio")
    txt.write_text("текст-заглушка", encoding="utf-8")
    return wav, txt


def test_ref_compare_render_tag_covers_model_temperature_rows(tmp_path):
    from audiobook.ref_compare import render_tag
    wav, txt = _cand(tmp_path)
    rows = [{"id": "0001", "hash": "1" * 40}, {"id": "0002", "hash": "2" * 40}]
    base = render_tag(wav, txt, _cfg(), rows)
    assert len(base) == 8 and render_tag(wav, txt, _cfg(), rows) == base
    other_model = _cfg()
    other_model["model"] = dict(other_model["model"], quantize="int8")
    assert render_tag(wav, txt, other_model, rows) != base
    variant = _cfg()
    variant["model"] = dict(variant["model"], variant="0.6B")
    assert render_tag(wav, txt, variant, rows) != base
    temp = _cfg()
    temp["model"] = dict(temp["model"], temperature=0.7)
    assert render_tag(wav, txt, temp, rows) != base
    rechunked = [{"id": "0001", "hash": "3" * 40}, rows[1]]
    assert render_tag(wav, txt, _cfg(), rechunked) != base   # same ids, other text
    txt.write_text("исправленная заглушка", encoding="utf-8")
    assert render_tag(wav, txt, _cfg(), rows) != base


def test_ref_compare_chunk_wavs_named_by_hash(tmp_path):
    from audiobook.ref_compare import render_candidate

    class Eng:
        def synth(self, text, seed, **kw):
            return np.full(2400, 0.1, dtype=np.float32)

    out = tmp_path / "cand"
    old = [{"id": "0001", "text": "Плейсхолдер старый.", "hash": "a" * 40, "seed_override": None}]
    new = [{"id": "0001", "text": "Плейсхолдер новый.", "hash": "b" * 40, "seed_override": None}]
    assert render_candidate(Eng(), old, _cfg(), out) == 0
    assert render_candidate(Eng(), new, _cfg(), out) == 0    # same id, new text: not reused
    assert sorted(p.name for p in out.glob("*.wav")) == ["a" * 16 + ".wav", "b" * 16 + ".wav"]


def test_ref_compare_run_assembles_from_hash_named_wavs(tmp_path, monkeypatch):
    from audiobook import ref_compare
    from audiobook.synth import _write_manifest
    import audiobook.master as master_mod
    import audiobook.synth as synth_mod
    import audiobook.worker as worker_mod
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    cdir = tmp_path / "ref" / "candidates"
    cdir.mkdir(parents=True)
    wav, txt = _cand(cdir)
    sec = tmp_path / "out" / "sections" / "01_sec"
    sec.mkdir(parents=True)
    rows = [{"id": "0001", "text": "Плейсхолдер один.", "hash": "1" * 40, "pause_after_ms": 300},
            {"id": "0002", "text": "Плейсхолдер два.", "hash": "2" * 40, "pause_after_ms": 300}]
    _write_manifest(sec / "manifest.jsonl", rows)

    class Eng:
        def synth(self, text, seed, **kw):
            return np.full(2400, 0.1, dtype=np.float32)

    class Ctx:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return Eng()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ref_compare, "ensure_latents", lambda w, t, v: cdir / "a.latents.pt")
    monkeypatch.setattr(synth_mod, "worker_config", lambda c, w: {})
    monkeypatch.setattr(worker_mod, "TimeoutSynth", Ctx)
    def fake_master(src, dst, cfg):
        dst.write_bytes(b"mp3")
        return {"input_i": -20}

    monkeypatch.setattr(master_mod, "master_wav", fake_master)
    import audiobook.pronounce as pron_mod
    monkeypatch.setattr(pron_mod, "load_table", lambda: {})
    assert ref_compare.run(_cfg(), "01_sec", 2) == 0
    tag = ref_compare.render_tag(wav, txt, _cfg(), synth_mod._read_manifest(sec / "manifest.jsonl"))
    out = tmp_path / "out" / "ref_compare" / "01_sec"
    assert (out / f"a_{tag}.mp3").exists() and not (out / f"a_{tag}.wav").exists()
    assert sorted(p.name for p in (out / f"a_{tag}").glob("*.wav")) == [
        "1" * 16 + ".wav", "2" * 16 + ".wav"]


# ── suspects ──────────────────────────────────────────────────────────────────

def _section(tmp_path, ids=("0001", "0002"), index_ids=None):
    from audiobook.synth import _write_manifest
    sec = tmp_path / "out" / "sections" / "01_sec"
    sec.mkdir(parents=True, exist_ok=True)
    rows = [{"id": i, "text": "Плейсхолдер.", "hash": f"{n}" * 40, "status": "done",
             "flag_words": [["Плейсхолдер", 0.1, 0.3, "conf"]]} for n, i in enumerate(ids, 1)]
    _write_manifest(sec / "manifest.jsonl", rows)
    idx = sec / "section.index.tsv"
    idx.write_text("id\tstart_ms\tlead_ms\n" + "".join(
        f"{i}\t{k * 1000}\t0\n" for k, i in enumerate(index_ids or ids)), encoding="utf-8")
    return sec, idx


def test_suspects_check_index_pure():
    from audiobook.suspects import check_index
    rows = [{"id": "0001"}, {"id": "0002"}, {"id": "0003"}]
    assert check_index(["0001", "0002", "0003"], rows, None, 2.0, 1.0) is None
    assert check_index(["0001", "0002"], rows, 2, 2.0, 1.0) is None      # preview_first2
    assert "старше" in check_index(["0001", "0002", "0003"], rows, None, 1.0, 2.0)
    why = check_index(["0001", "0009"], rows, 2, 2.0, 1.0)
    assert "не совпадают" in why and "0009" in why and "0002" in why
    assert "порядок" in check_index(["0002", "0001"], rows, 2, 2.0, 1.0)


def test_suspects_refuses_index_older_than_manifest(tmp_path, monkeypatch):
    from audiobook import suspects
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    sec, idx = _section(tmp_path)
    os.utime(idx, (1_000_000, 1_000_000))
    os.utime(sec / "manifest.jsonl", (2_000_000, 2_000_000))
    with pytest.raises(SystemExit, match="старше manifest.jsonl.*assemble"):
        suspects.run({}, "01_sec")
    assert not (sec / "section.suspects.tsv").exists()


def test_suspects_refuses_index_of_other_chunking(tmp_path, monkeypatch):
    from audiobook import suspects
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    sec, idx = _section(tmp_path, index_ids=("0001", "0005"))
    os.utime(sec / "manifest.jsonl", (1_000_000, 1_000_000))
    with pytest.raises(SystemExit, match="не совпадают"):
        suspects.run({}, "01_sec")


def test_suspects_runs_on_matching_index(tmp_path, monkeypatch, capsys):
    from audiobook import suspects
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    sec, idx = _section(tmp_path)
    os.utime(sec / "manifest.jsonl", (1_000_000, 1_000_000))
    assert suspects.run({}, "01_sec") == 0
    lines = (sec / "section.suspects.tsv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and "подозрительных мест 2" in capsys.readouterr().out
