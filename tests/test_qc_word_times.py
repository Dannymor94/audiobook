"""Layer-1 tests for QC word_times field.

Verifies:
- _measure returns word_times with every whisper word (not just flagged)
- word_times format: [[word_str, start_s, end_s, prob], ...]
- Existing flags/status/CER unaffected by the new field
- run_words_only only sets word_times; never changes status/flags/CER
- word_times is replaced atomically on re-transcription (hash binding)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf

SR = 24000


def _sine(dur_s: float, freq: float = 220.0) -> np.ndarray:
    t = np.linspace(0, dur_s, int(dur_s * SR), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * 0.3).astype(np.float32)


def _make_model(words: list[dict], text: str = "слово"):
    """Minimal whisper model mock returning the given per-word data."""
    seg = MagicMock()
    seg.text = text
    seg.words = [MagicMock(word=w["w"], start=w["s"], end=w["e"],
                            probability=w.get("p", 0.9)) for w in words]
    model = MagicMock()
    model.transcribe.return_value = ([seg], MagicMock())
    return model


# ── _measure includes word_times ─────────────────────────────────────────────

def test_measure_includes_word_times(tmp_path):
    """_measure return has word_times: [[w, s, e, p], ...] for every word."""
    from audiobook.qc import _measure
    wav_path = tmp_path / "ch.wav"
    sf.write(str(wav_path), _sine(3.0), SR, subtype="PCM_16")

    words = [
        {"w": "тебя", "s": 0.5, "e": 0.8, "p": 0.95},
        {"w": "нас",  "s": 1.0, "e": 1.2, "p": 0.9},
    ]
    model = _make_model(words, "тебя нас")
    # patch transcribe_words to return controlled data
    with patch("audiobook.qc.transcribe_words", return_value=("тебя нас", words)):
        result = _measure(model, wav_path, "тебя нас", set(), 0.6)

    assert "word_times" in result
    wt = result["word_times"]
    assert len(wt) == 2
    assert wt[0] == ["тебя", 0.5, 0.8, 0.95]
    assert wt[1] == ["нас", 1.0, 1.2, 0.9]


def test_measure_word_times_all_words_not_just_flagged(tmp_path):
    """word_times contains ALL words; flag_words is a subset."""
    from audiobook.qc import _measure
    wav_path = tmp_path / "ch.wav"
    sf.write(str(wav_path), _sine(5.0), SR, subtype="PCM_16")

    # "тебя" is in the watch set; "нас" is not and has high confidence
    words = [
        {"w": "тебя", "s": 0.5, "e": 0.8, "p": 0.95},  # watch → in flag_words
        {"w": "нас",  "s": 1.0, "e": 1.2, "p": 0.98},  # confident, not watch
        {"w": "идёт", "s": 1.5, "e": 1.9, "p": 0.9},   # confident, not watch
    ]
    watch = {"тебя"}
    with patch("audiobook.qc.transcribe_words", return_value=("тебя нас идёт", words)):
        result = _measure(MagicMock(), wav_path, "тебя нас идёт", watch, 0.6)

    # word_times has all 3 words
    wt_words = [e[0] for e in result["word_times"]]
    assert "тебя" in wt_words
    assert "нас" in wt_words
    assert "идёт" in wt_words

    # flag_words has only "тебя" (watch word)
    fw_words = [f[0] for f in result["flag_words"] if f[3] == "watch"]
    assert "тебя" in fw_words
    assert "нас" not in [f[0] for f in result["flag_words"]]
    assert "идёт" not in [f[0] for f in result["flag_words"]]


def test_measure_existing_fields_unaffected(tmp_path):
    """Adding word_times must not change cer, flag_words, transcript."""
    from audiobook.qc import _measure
    wav_path = tmp_path / "ch.wav"
    sf.write(str(wav_path), _sine(3.0), SR, subtype="PCM_16")

    words = [{"w": "слово", "s": 0.5, "e": 0.9, "p": 0.9}]
    with patch("audiobook.qc.transcribe_words", return_value=("слово", words)):
        result = _measure(MagicMock(), wav_path, "слово", set(), 0.6)

    assert "transcript" in result
    assert "flag_words" in result
    assert "cer" in result
    assert "word_times" in result   # new field present alongside old ones


# ── word_times replaces on re-transcription (hash binding) ───────────────────

def test_word_times_replaced_on_update():
    """r.update(_measure(...)) replaces word_times atomically."""
    r = {
        "id": "1", "word_times": [["старое", 0.0, 0.3, 0.9]],
        "flag_words": [], "status": "done",
    }
    new_wt = [["новое", 1.0, 1.4, 0.95]]
    r.update({"word_times": new_wt, "flag_words": []})
    assert r["word_times"] == new_wt
    assert len(r["word_times"]) == 1
    assert r["word_times"][0][0] == "новое"


# ── run_words_only preserves status and flags ─────────────────────────────────

def _write_manifest(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")




def test_run_words_only_preserves_all_fields(tmp_path, monkeypatch):
    """run_words_only only adds word_times; status/cer/flag_words unchanged."""
    import json as _json
    from audiobook import paths as _paths
    monkeypatch.setattr(_paths, "OUT", tmp_path / "out")

    sec_dir = tmp_path / "out" / "sections" / "01_test"
    chunks_dir = sec_dir / "chunks"
    chunks_dir.mkdir(parents=True)
    wav_path = chunks_dir / "1.wav"
    sf.write(str(wav_path), _sine(3.0), SR, subtype="PCM_16")

    original_row = {
        "id": "1", "status": "manual", "text": "слово",
        "hash": "abc123", "seed": 42,
        "flag_words": [["тебя", 0.5, 0.9, "watch"]],
        "cer": 0.05,
    }
    manifest_path = sec_dir / "manifest.jsonl"
    _write_manifest(manifest_path, [original_row])

    config = {"qc": {"word_conf": 0.6}, "master": {}}
    new_wt = [["слово", 0.3, 0.6, 0.98]]

    with patch("audiobook.qc.load_whisper") as mock_lw, \
         patch("audiobook.qc._release"), \
         patch("audiobook.qc._measure") as mock_m, \
         patch("audiobook.probe.load_watch", return_value=set()):
        mock_m.return_value = {
            "transcript": "слово", "flag_words": [], "cer": 0.0,
            "word_times": new_wt,
            "word_diff": "", "min_p": 0.98, "mean_p": 0.98, "peak": 0.3,
        }
        from audiobook.qc import run_words_only
        run_words_only(config, "01_test")

    # Read back manifest and verify
    rows_back = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows_back.append(_json.loads(line))

    assert len(rows_back) == 1
    r = rows_back[0]
    # word_times was added
    assert r["word_times"] == new_wt
    # nothing else changed
    assert r["status"] == "manual"
    assert r["cer"] == pytest.approx(0.05)
    assert r["hash"] == "abc123"
    assert r["flag_words"] == [["тебя", 0.5, 0.9, "watch"]]


def test_run_words_only_skips_already_populated(tmp_path, monkeypatch):
    """run_words_only skips chunks that already have word_times."""
    import json as _json
    from audiobook import paths as _paths
    monkeypatch.setattr(_paths, "OUT", tmp_path / "out")

    sec_dir = tmp_path / "out" / "sections" / "01_test"
    chunks_dir = sec_dir / "chunks"
    chunks_dir.mkdir(parents=True)
    wav_path = chunks_dir / "1.wav"
    sf.write(str(wav_path), _sine(3.0), SR, subtype="PCM_16")

    existing_wt = [["слово", 0.3, 0.6, 0.98]]
    row = {"id": "1", "status": "done", "text": "слово",
           "word_times": existing_wt, "hash": "abc"}
    manifest_path = sec_dir / "manifest.jsonl"
    _write_manifest(manifest_path, [row])

    config = {"qc": {"word_conf": 0.6}, "master": {}}
    with patch("audiobook.qc.load_whisper") as mock_lw, \
         patch("audiobook.qc._release"), \
         patch("audiobook.qc._measure") as mock_m, \
         patch("audiobook.probe.load_watch", return_value=set()):
        from audiobook.qc import run_words_only
        run_words_only(config, "01_test")
        mock_m.assert_not_called()   # nothing transcribed — already populated
