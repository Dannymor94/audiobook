"""qc best-of-N takes: selection rules (no models)."""
from pathlib import Path

from audiobook import takes
from audiobook.qc import _norm_word

S = {"count": 3, "short_chars": 40, "low_conf": 0.15, "clip_peak": 0.999}


def test_settings_off_by_default_and_on_with_count():
    assert takes.settings({}) is None
    assert takes.settings({"qc": {"takes": {"count": 1}}}) is None
    assert takes.settings({"qc": {"takes": {"count": 3}}}) == S


def test_reason_rules():
    short = {"id": "1", "text": "Шаг второй.", "status": "done"}
    assert takes.reason(short, S) == "short"
    assert takes.reason(dict(short, locked=True), S) is None
    assert takes.reason(dict(short, status="manual"), S) is None
    assert takes.reason(dict(short, takes=3), S) is None          # already done
    long_ok = {"id": "2", "text": "x" * 100, "status": "done", "min_p": 0.5}
    assert takes.reason(long_ok, S) is None
    assert takes.reason(dict(long_ok, min_p=0.1), S) == "unsure"


def test_take_seeds_fixed_by_base():
    r = {"take_base": 1000, "seed": 5}
    assert takes.take_seeds(r, S) == [1000 + takes.TAKE_STEP, 1000 + 2 * takes.TAKE_STEP]


def test_take_dir_keyed_by_hash(tmp_path):
    r = {"id": "0007", "hash": "abcdef0123456789" * 2}
    assert takes.take_dir(tmp_path, r) == tmp_path / "takes" / "0007__abcdef012345"


def test_score_order():
    base = {"cer": 0.0, "flag_words": [], "min_p": 0.9, "mean_p": 0.9}
    fail = dict(base, cer=0.2)
    unsure = dict(base, flag_words=[["тебья", 0.1, 0.05, "conf"]])
    watch_only = dict(base, flag_words=[["потом", 0.1, 0.9, "watch"]])
    weaker = dict(base, min_p=0.5)
    ranked = sorted([fail, unsure, weaker, base], key=lambda m: takes.score(m, 0.05))
    assert ranked == [base, weaker, unsure, fail]
    assert takes.score(watch_only, 0.05) == takes.score(base, 0.05)   # watch is not a defect


def test_word_stats_ignores_short_words_for_min():
    words = [{"w": "я", "p": 0.01}, {"w": "чувствую", "p": 0.8}, {"w": ",", "p": 0.0}]
    mn, mean = takes.word_stats(words, _norm_word)
    assert mn == 0.8
    assert mean == round((0.01 + 0.8) / 2, 3)


def test_carry_keeps_takes_fields():
    from audiobook.chunker import _CARRY
    for k in ("min_p", "mean_p", "takes", "take_base"):
        assert k in _CARRY


def test_config_enables_takes():
    import yaml
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert takes.settings(cfg)["count"] >= 2


def test_takes_phase_picks_best_and_keeps_all(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf
    from audiobook import qc, synth, worker

    sec = tmp_path / "sec"
    chunks = sec / "chunks"
    chunks.mkdir(parents=True)
    row = {"id": "0001", "hash": "f" * 40, "text": "Шаг второй.", "status": "done",
           "seed": 100, "cer": 0.2, "flag_words": [], "min_p": 0.9, "mean_p": 0.9}
    sf.write(str(chunks / "0001.wav"), np.full(2400, 0.10, dtype=np.float32), 24000,
             subtype="FLOAT")
    good_seed = 100 + 2 * takes.TAKE_STEP
    rendered = []

    class FakeEngine:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def synth(self, text, seed, **kw):
            rendered.append(seed)
            return np.full(4800, 0.5 if seed == good_seed else 0.3, dtype=np.float32)

    def fake_words(model, path):
        amp = float(sf.read(str(path), dtype="float32")[0][0])
        txt = "шаг второй" if abs(amp - 0.5) < 1e-3 else "шак фторой"
        return txt, [{"w": w, "s": 0.0, "e": 0.1, "p": 0.9} for w in txt.split()]

    monkeypatch.setattr(worker, "TimeoutSynth", FakeEngine)
    monkeypatch.setattr(qc, "load_whisper", lambda: object())
    monkeypatch.setattr(qc, "transcribe_words", fake_words)
    monkeypatch.setattr(synth, "prepare_synth_text", lambda t, c, tb, s: (t, None))
    cfg = {"qc": {"takes": {"count": 3, "short_chars": 40}}}
    rows = [row]
    took, replaced = qc._takes_phase(rows, cfg, sec, chunks, sec / "manifest.jsonl",
                                     {}, 10, {}, "", 0.05, set(), 0.6)
    assert (took, replaced) == (1, 1)
    assert row["seed"] == good_seed and row["cer"] == 0.0 and row["takes"] == 3
    assert row["take_base"] == 100
    tdir = takes.take_dir(sec, row)
    assert sorted(p.name for p in tdir.glob("*.wav")) == sorted(
        f"{s}.wav" for s in (100, 100 + takes.TAKE_STEP, good_seed))   # nothing lost
    assert abs(sf.read(str(chunks / "0001.wav"), dtype="float32")[0][0] - 0.5) < 1e-3
    assert row["duration_ms"] == 200
    # re-run: already done → nothing rendered, nothing replaced
    rendered.clear()
    assert qc._takes_phase(rows, cfg, sec, chunks, sec / "manifest.jsonl",
                           {}, 10, {}, "", 0.05, set(), 0.6) == (0, 0)
    assert rendered == []


def test_clipped_reason_and_score():
    row = {"id": "3", "text": "x" * 100, "status": "done", "min_p": 0.9, "peak": 1.0}
    assert takes.reason(row, S) == "clipped"
    assert takes.reason(dict(row, peak=0.8), S) is None
    clean = {"cer": 0.01, "flag_words": [], "min_p": 0.8, "mean_p": 0.8, "peak": 0.7}
    clipped_better_words = {"cer": 0.0, "flag_words": [], "min_p": 0.99, "mean_p": 0.99, "peak": 1.0}
    assert takes.score(clean, 0.05) < takes.score(clipped_better_words, 0.05)


def test_wav_peak(tmp_path):
    import numpy as np
    import soundfile as sf
    p = tmp_path / "a.wav"
    sf.write(str(p), np.array([0.1, -0.75, 0.3], dtype=np.float32), 24000, subtype="FLOAT")
    assert takes.wav_peak(p) == 0.75
