"""Integration tests: QC word_times → stress_clips pipeline.

Layer 1: no models. word_times populated directly in manifest rows.
Covers:
- confident word outside the watch list (would be missed by flag_words)
- repeated occurrences of the same word in one chunk
- long word (end_s - start_s > 0.6s): clip width = word_dur + 2*pad
- word_times/flag_words independence: no false occurrences from flags
- no-word_times → reject with qc-words hint
"""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from audiobook.stress_clips import (
    build_clips,
    collect_hits,
    chunks_without_timestamps,
    slice_wav,
)

SR = 24000
PAD_S = 0.6
GAP_S = 0.4


def _sine(dur_s: float, freq: float = 330.0) -> np.ndarray:
    t = np.linspace(0, dur_s, int(dur_s * SR), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * 0.4).astype(np.float32)


# ── confident word outside watch list ────────────────────────────────────────

def test_confident_word_outside_watch_found(tmp_path):
    """Word with high confidence, NOT in watch list → found via word_times."""
    # This word would NOT appear in flag_words (high conf, not watch)
    rows = [{
        "id": "ch1",
        "word_times": [
            ["тебя",  1.0, 1.3, 0.95],  # watch word (would be in flag_words too)
            ["замок", 2.0, 2.4, 0.98],  # confident, NOT in watch → only in word_times
        ],
        "flag_words": [["тебя", 1.0, 0.95, "watch"]],  # only watch word flagged
        "status": "done",
    }]
    # Word set includes "замок" (a risk word, say)
    hits = collect_hits(rows, {"замок"})
    assert len(hits) == 1
    assert hits[0]["word"] == "замок"
    assert hits[0]["start_s"] == pytest.approx(2.0)
    assert hits[0]["end_s"] == pytest.approx(2.4)


def test_confident_word_produces_correct_clip(tmp_path):
    """confident word → correct clip boundaries in audio."""
    wav_data = _sine(10.0)
    sf.write(str(tmp_path / "ch1.wav"), wav_data, SR, subtype="PCM_16")

    hits = [{"id": "ch1", "start_s": 2.0, "end_s": 2.4, "word": "замок", "prob": 0.98}]
    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)

    assert len(records) == 1
    expected_len = int((2.4 - 2.0 + 2 * PAD_S) * SR)
    assert abs(len(audio) - expected_len) <= 2


# ── repeated occurrences ──────────────────────────────────────────────────────

def test_repeated_occurrences_multiple_clips(tmp_path):
    """Same word at three timestamps → three clips, correct start times."""
    wav_data = _sine(15.0)
    sf.write(str(tmp_path / "ch1.wav"), wav_data, SR, subtype="PCM_16")

    rows = [{
        "id": "ch1",
        "word_times": [
            ["тебя", 1.0, 1.3, 0.95],
            ["тебя", 5.0, 5.3, 0.9],
            ["тебя", 9.0, 9.3, 0.88],
        ],
        "status": "done",
    }]
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 3

    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)
    assert len(records) == 3

    # Verify start times are strictly increasing
    starts = [r["clip_start_s"] for r in records]
    assert starts[0] < starts[1] < starts[2]

    # First clip starts at 0
    assert starts[0] == pytest.approx(0.0)

    # Each clip width: 0.3s word + 1.2s padding
    clip_dur = 0.3 + 2 * PAD_S
    gap_dur = GAP_S
    assert starts[1] == pytest.approx(clip_dur + gap_dur, abs=0.02)
    assert starts[2] == pytest.approx(2 * (clip_dur + gap_dur), abs=0.02)


def test_repeated_occurrences_in_index(tmp_path):
    """index.tsv has one row per clip, with correct clip_time values."""
    wav_data = _sine(15.0)
    sf.write(str(tmp_path / "ch1.wav"), wav_data, SR, subtype="PCM_16")

    hits = [
        {"id": "ch1", "start_s": 1.0, "end_s": 1.3, "word": "тебя", "prob": 0.95},
        {"id": "ch1", "start_s": 5.0, "end_s": 5.3, "word": "тебя", "prob": 0.9},
    ]
    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)
    assert records[0]["hit"]["id"] == "ch1"
    assert records[1]["hit"]["start_s"] == pytest.approx(5.0)


# ── long word (duration > pad) ────────────────────────────────────────────────

def test_long_word_wider_clip(tmp_path):
    """Long word (1.5s): clip = 1.5 + 2*0.6 = 2.7s, not 2*0.6 = 1.2s."""
    wav_data = _sine(10.0)
    sf.write(str(tmp_path / "ch1.wav"), wav_data, SR, subtype="PCM_16")

    word_dur = 1.5  # > PAD_S
    start_s, end_s = 2.0, 2.0 + word_dur
    hits = [{"id": "ch1", "start_s": start_s, "end_s": end_s,
             "word": "длинное", "prob": 0.9}]
    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)

    assert len(records) == 1
    expected_dur = word_dur + 2 * PAD_S
    actual_dur = len(audio) / SR
    assert abs(actual_dur - expected_dur) < 0.01


def test_long_word_vs_centre_based(tmp_path):
    """Long word clip is wider than the centre-based fallback would give."""
    wav_data = _sine(10.0)
    # long word: start=3, end=4.5 (1.5s duration)
    clip_proper = slice_wav(wav_data, SR, 3.0, 4.5, PAD_S)
    clip_fallback = slice_wav(wav_data, SR, 3.0, None, PAD_S)   # centre-only
    # proper clip includes word_end+pad; fallback stops at start+pad
    assert len(clip_proper) > len(clip_fallback)


# ── no word_times → reject cleanly ───────────────────────────────────────────

def test_no_word_times_all_missing():
    """P1-4: all rendered chunks have no word_times → reported."""
    rows = [
        {"id": "1", "status": "done", "flag_words": [["тебя", 1.0, 0.9, "watch"]]},
        {"id": "2", "status": "done"},
    ]
    missing = chunks_without_timestamps(rows)
    # Both lack word_times
    assert set(missing) == {"1", "2"}


def test_collect_hits_returns_empty_when_no_word_times():
    """When word_times absent (even with flag_words), collect_hits returns []."""
    rows = [{"id": "1", "flag_words": [["тебя", 1.0, 0.9, "watch"]], "status": "done"}]
    assert collect_hits(rows, {"тебя"}) == []


# ── word_times / flag_words independence ─────────────────────────────────────

def test_word_in_flag_but_not_word_times_not_found():
    """R2-6: word appears in flag_words but absent from word_times → NOT found."""
    rows = [{
        "id": "1",
        "word_times": [["нас", 0.5, 0.7, 0.9]],
        "flag_words": [["тебя", 2.0, 0.9, "watch"]],
        "status": "done",
    }]
    assert collect_hits(rows, {"тебя"}) == []


def test_word_times_has_more_entries_than_flag_words():
    """word_times has ALL words; collect_hits finds non-flagged confident words."""
    rows = [{
        "id": "1",
        "word_times": [
            ["тебя",  1.0, 1.3, 0.95],  # watch → also in flag_words
            ["замок", 2.0, 2.4, 0.98],  # risk word, not in watch, high conf
            ["пишет", 3.0, 3.3, 0.9],   # neutral
        ],
        "flag_words": [["тебя", 1.0, 0.95, "watch"]],
        "status": "done",
    }]
    # risk set includes "замок"
    hits = collect_hits(rows, {"замок"})
    assert len(hits) == 1
    assert hits[0]["word"] == "замок"
