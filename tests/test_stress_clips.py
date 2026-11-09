"""Layer-1 tests for stress_clips: synthetic wav + fake flag_words → correct boundaries."""
import numpy as np
import pytest
import soundfile as sf

from audiobook.stress_clips import (
    _norm,
    collect_hits,
    slice_wav,
    build_clips,
    load_tsv_words,
)

SR = 24000
PAD_S = 0.6
GAP_S = 0.4


def _sine(dur_s: float, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0, dur_s, int(dur_s * SR), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)


# ── _norm ────────────────────────────────────────────────────────────────────

def test_norm_strips_stress_and_yo():
    assert _norm("тебя́") == "тебя"
    assert _norm("нёс") == "нес"
    assert _norm("Тебя") == "тебя"


def test_norm_strips_plus():
    assert _norm("те+бя") == "тебя"


# ── collect_hits ─────────────────────────────────────────────────────────────

def _rows(flag_words_list):
    return [{"id": "1", "flag_words": flag_words_list, "status": "done"}]


def test_collect_hits_match():
    rows = _rows([["тебя", 2.0, 0.9, "watch"], ["сыра", 3.0, 0.8, "conf"]])
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 1
    assert hits[0]["start_s"] == pytest.approx(2.0)
    assert hits[0]["word"] == "тебя"


def test_collect_hits_no_match():
    rows = _rows([["дышит", 1.0, 0.7, "conf"]])
    assert collect_hits(rows, {"тебя"}) == []


def test_collect_hits_norm_stress():
    # flag_words word has stress mark; word_set is plain
    rows = _rows([["теб́я", 1.5, 0.95, "watch"]])
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 1


def test_collect_hits_multiple_chunks():
    rows = [
        {"id": "1", "flag_words": [["тебя", 1.0, 0.9, "watch"]], "status": "done"},
        {"id": "2", "flag_words": [["тебя", 2.5, 0.85, "watch"],
                                   ["нас", 0.5, 0.7, "conf"]], "status": "done"},
    ]
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 2


def test_collect_hits_missing_flag_words():
    rows = [{"id": "1", "status": "done"}]
    assert collect_hits(rows, {"тебя"}) == []


# ── slice_wav ────────────────────────────────────────────────────────────────

def test_slice_wav_mid():
    data = _sine(10.0)
    clip = slice_wav(data, SR, center_s=5.0, pad_s=PAD_S)
    expected_len = int(2 * PAD_S * SR)
    assert abs(len(clip) - expected_len) <= 2


def test_slice_wav_near_start():
    data = _sine(5.0)
    clip = slice_wav(data, SR, center_s=0.1, pad_s=PAD_S)
    # clamped to 0: shorter than full window
    assert len(clip) < int(2 * PAD_S * SR)
    assert len(clip) > 0


def test_slice_wav_near_end():
    data = _sine(5.0)
    clip = slice_wav(data, SR, center_s=4.9, pad_s=PAD_S)
    assert len(clip) < int(2 * PAD_S * SR)
    assert len(clip) > 0


# ── build_clips ──────────────────────────────────────────────────────────────

def test_build_clips_boundaries(tmp_path):
    """Two hits → two clips; gap between them; clip_starts match."""
    wav_path = tmp_path / "ch1.wav"
    data = _sine(10.0, freq=220.0)
    sf.write(str(wav_path), data, SR, subtype="PCM_16")

    hits = [
        {"id": "ch1", "start_s": 2.0, "word": "тебя", "prob": 0.9},
        {"id": "ch1", "start_s": 7.0, "word": "тебя", "prob": 0.85},
    ]
    audio, starts = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)

    clip_len = int(2 * PAD_S * SR)
    gap_len = int(GAP_S * SR)
    expected_total = clip_len * 2 + gap_len
    assert abs(len(audio) - expected_total) <= 4

    assert len(starts) == 2
    assert starts[0] == pytest.approx(0.0)
    # second clip starts after first clip + gap
    assert starts[1] == pytest.approx(2 * PAD_S + GAP_S, abs=0.01)


def test_build_clips_missing_wav(tmp_path):
    """Missing wav is skipped silently; clip list shorter."""
    hits = [{"id": "missing", "start_s": 1.0, "word": "тест", "prob": 0.9}]
    audio, starts = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)
    assert audio.size == 0
    assert starts == []


# ── load_tsv_words ───────────────────────────────────────────────────────────

def test_load_tsv_words(tmp_path):
    p = tmp_path / "risk.tsv"
    p.write_text("form\tfreq\treason\nтебя\t12\ttop\nнёс\t3\thomograph\n",
                 encoding="utf-8")
    words = load_tsv_words(p)
    assert "тебя" in words
    assert "нес" in words   # ё→е normalised


def test_load_tsv_words_missing(tmp_path):
    assert load_tsv_words(tmp_path / "nonexistent.tsv") == set()
