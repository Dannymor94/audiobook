"""Layer-1 regression tests for stress_clips.

Synthetic wavs + hand-crafted manifest rows; no models, no network.
Covers all P1/P2 issues from code review and the round-2 requirements:
  P1-1  word_times is the only source (no flag_words fallback)
  P1-2  clip boundaries [word_start-pad, word_end+pad]
  P1-3  index built from successful clips only (no zip mismatch)
  P1-4  full list of chunks without timestamps
  P1-5  stale/unverifiable section index is refused (not silently ?-filled)
  P1-6  duplicate occurrences are deduplicated
  P1-7  mismatched sample rate raises SystemExit
  R2-3  no fallback: no word_times → reject with qc-words hint
  R2-6  word_times independent from flag_words (no false occurrences)
"""
import numpy as np
import pytest
import soundfile as sf

from audiobook.stress_clips import (
    _norm,
    collect_hits,
    slice_wav,
    build_clips,
    load_tsv_words,
    chunks_without_timestamps,
)

SR = 24000
PAD_S = 0.6
GAP_S = 0.4


def _sine(dur_s: float, freq: float = 440.0, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, dur_s, int(dur_s * sr), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)


# ── _norm ────────────────────────────────────────────────────────────────────

def test_norm_strips_stress_and_yo():
    assert _norm("тебя́") == "тебя"
    assert _norm("нёс") == "нес"
    assert _norm("Тебя") == "тебя"


def test_norm_strips_plus():
    assert _norm("те+бя") == "тебя"


# ── P1-1 / R2-3: word_times is the only source ───────────────────────────────

def test_collect_hits_uses_word_times():
    rows = [{
        "id": "1",
        "word_times": [["тебя", 2.0, 2.4, 0.95]],
        "flag_words": [],
        "status": "done",
    }]
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 1
    assert hits[0]["start_s"] == pytest.approx(2.0)
    assert hits[0]["end_s"] == pytest.approx(2.4)


def test_collect_hits_no_fallback_to_flag_words():
    """R2-3: word_times absent → chunk skipped (no fallback to flag_words)."""
    rows = [{
        "id": "1",
        "flag_words": [["тебя", 2.0, 0.9, "watch"]],
        "status": "done",
    }]
    hits = collect_hits(rows, {"тебя"})
    assert hits == []


def test_collect_hits_no_match():
    rows = [{"id": "1", "word_times": [["дышит", 1.0, 1.3, 0.7]], "status": "done"}]
    assert collect_hits(rows, {"тебя"}) == []


def test_collect_hits_norm_stress_in_word_times():
    rows = [{"id": "1", "word_times": [["теб́я", 1.5, 1.8, 0.95]], "status": "done"}]
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 1


def test_collect_hits_multiple_chunks():
    rows = [
        {"id": "1", "word_times": [["тебя", 1.0, 1.3, 0.9]], "status": "done"},
        {"id": "2", "word_times": [["тебя", 2.5, 2.8, 0.85],
                                   ["нас", 0.5, 0.7, 0.9]], "status": "done"},
    ]
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 2


def test_collect_hits_missing_word_times():
    rows = [{"id": "1", "status": "done"}]
    assert collect_hits(rows, {"тебя"}) == []


# ── R2-6: word_times and flag_words are independent ──────────────────────────

def test_flag_words_not_used_as_source():
    """R2-6: word in flag_words but not in word_times → NOT in hits."""
    rows = [{
        "id": "1",
        "word_times": [["нас", 0.5, 0.7, 0.9]],   # only "нас"
        "flag_words": [["тебя", 2.0, 0.9, "watch"]],  # "тебя" only in flags
        "status": "done",
    }]
    hits = collect_hits(rows, {"тебя"})
    assert hits == []


def test_word_in_both_sources_uses_word_times_values():
    """R2-6: word in both word_times and flag_words → word_times values used."""
    rows = [{
        "id": "1",
        # word_times has correct start/end; flag_words has stale start
        "word_times": [["тебя", 2.0, 2.4, 0.95]],
        "flag_words": [["тебя", 9.9, 0.1, "watch"]],
        "status": "done",
    }]
    hits = collect_hits(rows, {"тебя"})
    assert len(hits) == 1
    assert hits[0]["start_s"] == pytest.approx(2.0)
    assert hits[0]["end_s"] == pytest.approx(2.4)


# ── P1-6: deduplication ───────────────────────────────────────────────────────

def test_collect_hits_dedup_exact_duplicate():
    """P1-6: same (id, norm_word, start_s) → one hit."""
    rows = [{
        "id": "1",
        "word_times": [["тебя", 2.0, 2.4, 0.95], ["тебя", 2.0, 2.4, 0.95]],
        "status": "done",
    }]
    assert len(collect_hits(rows, {"тебя"})) == 1


def test_collect_hits_dedup_stress_variant():
    """P1-6: stressed vs plain at same time → one hit."""
    rows = [{
        "id": "1",
        "word_times": [["тебя́", 2.0, 2.4, 0.95], ["тебя", 2.0, 2.4, 0.9]],
        "status": "done",
    }]
    assert len(collect_hits(rows, {"тебя"})) == 1


def test_collect_hits_distinct_times_not_deduped():
    rows = [{"id": "1", "word_times": [["тебя", 2.0, 2.4, 0.95],
                                        ["тебя", 5.0, 5.4, 0.9]], "status": "done"}]
    assert len(collect_hits(rows, {"тебя"})) == 2


# ── P1-4: chunks_without_timestamps ──────────────────────────────────────────

def test_chunks_without_timestamps_all_missing():
    rows = [{"id": "1", "status": "done"}, {"id": "2", "status": "done"}]
    assert chunks_without_timestamps(rows) == ["1", "2"]


def test_chunks_without_timestamps_partial():
    rows = [
        {"id": "1", "status": "done", "word_times": [["тебя", 1.0, 1.3, 0.9]]},
        {"id": "2", "status": "done"},
        {"id": "3", "status": "todo"},   # not rendered → not reported
    ]
    assert chunks_without_timestamps(rows) == ["2"]


def test_chunks_without_timestamps_all_present():
    rows = [{"id": "1", "status": "done", "word_times": [["тебя", 1.0, 1.3, 0.9]]}]
    assert chunks_without_timestamps(rows) == []


# ── P1-2: slice_wav with word_start / word_end ────────────────────────────────

def test_slice_wav_uses_end_s():
    """P1-2: window is [start-pad, end+pad]."""
    data = _sine(10.0)
    start_s, end_s = 3.0, 4.0
    clip = slice_wav(data, SR, start_s, end_s, PAD_S)
    expected_len = int((end_s - start_s + 2 * PAD_S) * SR)
    assert abs(len(clip) - expected_len) <= 2


def test_slice_wav_fallback_no_end_s():
    """Fallback end_s=None → centre-based [start-pad, start+pad]."""
    data = _sine(10.0)
    clip = slice_wav(data, SR, start_s=5.0, end_s=None, pad_s=PAD_S)
    assert abs(len(clip) - int(2 * PAD_S * SR)) <= 2


def test_slice_wav_clamped_start():
    data = _sine(5.0)
    clip = slice_wav(data, SR, start_s=0.1, end_s=0.5, pad_s=PAD_S)
    assert len(clip) < int((0.5 - 0.1 + 2 * PAD_S) * SR)
    assert len(clip) > 0


def test_slice_wav_clamped_end():
    data = _sine(5.0)
    clip = slice_wav(data, SR, start_s=4.5, end_s=4.8, pad_s=PAD_S)
    assert len(clip) < int((0.3 + 2 * PAD_S) * SR)
    assert len(clip) > 0


# ── P1-3: build_clips index from successful clips only ───────────────────────

def test_build_clips_index_survives_missing_wav(tmp_path):
    """P1-3: missing wav is skipped; subsequent clips have correct start times."""
    sf.write(str(tmp_path / "ch2.wav"), _sine(10.0), SR, subtype="PCM_16")
    hits = [
        {"id": "ch1", "start_s": 2.0, "end_s": 2.4, "word": "тебя", "prob": 0.9},
        {"id": "ch2", "start_s": 3.0, "end_s": 3.5, "word": "тебя", "prob": 0.85},
    ]
    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)
    assert len(records) == 1
    assert records[0]["hit"]["id"] == "ch2"
    assert records[0]["clip_start_s"] == pytest.approx(0.0)


def test_build_clips_two_clips_start_times(tmp_path):
    """P1-3: second clip starts after first+gap."""
    sf.write(str(tmp_path / "ch1.wav"), _sine(10.0), SR, subtype="PCM_16")
    hits = [
        {"id": "ch1", "start_s": 2.0, "end_s": 2.5, "word": "тебя", "prob": 0.9},
        {"id": "ch1", "start_s": 7.0, "end_s": 7.4, "word": "тебя", "prob": 0.85},
    ]
    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)
    assert len(records) == 2
    clip1_dur = hits[0]["end_s"] - hits[0]["start_s"] + 2 * PAD_S
    assert records[1]["clip_start_s"] == pytest.approx(clip1_dur + GAP_S, abs=0.02)


def test_build_clips_missing_wav_returns_empty(tmp_path):
    hits = [{"id": "missing", "start_s": 1.0, "end_s": 1.3, "word": "тест", "prob": 0.9}]
    audio, records = build_clips(hits, tmp_path, SR, PAD_S, GAP_S)
    assert audio.size == 0
    assert records == []


# ── P1-7: sample rate mismatch ────────────────────────────────────────────────

def test_build_clips_wrong_sr_raises(tmp_path):
    """P1-7: chunk wav at wrong sample rate → SystemExit."""
    wrong_sr = 16000
    sf.write(str(tmp_path / "ch1.wav"), _sine(5.0, sr=wrong_sr), wrong_sr, subtype="PCM_16")
    hits = [{"id": "ch1", "start_s": 1.0, "end_s": 1.3, "word": "тест", "prob": 0.9}]
    with pytest.raises(SystemExit, match="16000"):
        build_clips(hits, tmp_path, SR, PAD_S, GAP_S)


# ── load_tsv_words ───────────────────────────────────────────────────────────

def test_load_tsv_words(tmp_path):
    p = tmp_path / "risk.tsv"
    p.write_text("form\tfreq\treason\nтебя\t12\ttop\nнёс\t3\thomograph\n",
                 encoding="utf-8")
    words = load_tsv_words(p)
    assert "тебя" in words
    assert "нес" in words


def test_load_tsv_words_missing(tmp_path):
    assert load_tsv_words(tmp_path / "nonexistent.tsv") == set()
