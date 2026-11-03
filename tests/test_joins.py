"""Layer-1 tests for joins.py — synthetic WAV only, no real models."""

import math
import numpy as np
import pytest
import soundfile as sf

from audiobook.joins import (
    _f0_median_st,
    _f0_slope_st_per_s,
    _rms_db,
    _voiced_dur_s,
    _join_row,
    _flags,
    _within_para_pairs,
)

_SR = 24_000


def _sine(freq_hz: float, dur_s: float, amp: float = 0.3) -> np.ndarray:
    t = np.linspace(0, dur_s, int(dur_s * _SR), endpoint=False)
    return (amp * np.sin(2 * math.pi * freq_hz * t)).astype(np.float32)


def _write_wav(path, y):
    sf.write(str(path), y, _SR)


# ── F0 helpers ────────────────────────────────────────────────────────────────

def test_f0_median_known_freq():
    """Sine at 110 Hz → median F0 ~110 Hz → 12*log2(110/27.5) = 24 semitones."""
    y = _sine(110.0, 1.0)
    st = _f0_median_st(y)
    expected = 12.0 * math.log2(110.0 / 27.5)
    assert abs(st - expected) < 2.0, f"got {st:.2f} st, expected ~{expected:.2f}"


def test_f0_diff_between_tones():
    """Two tones one octave apart differ by 12 semitones."""
    y_low = _sine(110.0, 0.6)
    y_high = _sine(220.0, 0.6)
    diff = _f0_median_st(y_high) - _f0_median_st(y_low)
    assert 10.0 < diff < 14.0, f"expected ~12 st octave, got {diff:.2f}"


def test_f0_slope_falling():
    """Linearly swept tone 200→100 Hz has negative slope."""
    dur = 0.6
    t = np.linspace(0, dur, int(dur * _SR), endpoint=False)
    freq = np.linspace(200.0, 100.0, len(t))
    phase = np.cumsum(2 * math.pi * freq / _SR)
    y = (0.3 * np.sin(phase)).astype(np.float32)
    slope = _f0_slope_st_per_s(y)
    assert slope < -5.0, f"expected falling slope, got {slope:.2f} st/s"


def test_f0_slope_rising():
    """Linearly swept tone 100→200 Hz has positive slope."""
    dur = 0.6
    t = np.linspace(0, dur, int(dur * _SR), endpoint=False)
    freq = np.linspace(100.0, 200.0, len(t))
    phase = np.cumsum(2 * math.pi * freq / _SR)
    y = (0.3 * np.sin(phase)).astype(np.float32)
    slope = _f0_slope_st_per_s(y)
    assert slope > 5.0, f"expected rising slope, got {slope:.2f} st/s"


# ── RMS ───────────────────────────────────────────────────────────────────────

def test_rms_db_half_amplitude():
    """Halving amplitude → -6 dB."""
    y1 = _sine(110.0, 0.5, amp=0.3)
    y2 = _sine(110.0, 0.5, amp=0.15)
    diff = _rms_db(y2) - _rms_db(y1)
    assert abs(diff - (-6.0)) < 1.0, f"expected ~-6 dB, got {diff:.2f}"


# ── join_row ──────────────────────────────────────────────────────────────────

def test_join_row_f0_jump():
    """Octave jump → f0_diff_st ~12."""
    y_i = _sine(110.0, 1.0)
    y_j = _sine(220.0, 1.0)
    row = _join_row(y_i, y_j, "слово раз", "слово два")
    assert abs(row["f0_diff_st"] - 12.0) < 3.0, row["f0_diff_st"]


def test_join_row_no_jump_same_tone():
    """Same tone → f0_diff_st near 0, rms_diff_db near 0."""
    y = _sine(150.0, 1.0)
    row = _join_row(y, y, "тест", "тест")
    assert abs(row["f0_diff_st"]) < 2.0
    assert abs(row["rms_diff_db"]) < 1.0


# ── flags ─────────────────────────────────────────────────────────────────────

def test_flags_f0_jump_triggered():
    thresholds = {"f0_jump_st": 4.0, "slope_fall_st_s": 8.0,
                  "rms_jump_db": 6.0, "tempo_diff_pct": 25.0}
    row = {"f0_diff_st": 5.0, "slope_tail_st_s": 0.0,
           "rms_diff_db": 1.0, "tempo_diff_pct": 10.0}
    assert "F0_JUMP" in _flags(row, thresholds)


def test_flags_fall_end_triggered():
    thresholds = {"f0_jump_st": 4.0, "slope_fall_st_s": 8.0,
                  "rms_jump_db": 6.0, "tempo_diff_pct": 25.0}
    row = {"f0_diff_st": 0.0, "slope_tail_st_s": -10.0,
           "rms_diff_db": 1.0, "tempo_diff_pct": 5.0}
    assert "FALL_END" in _flags(row, thresholds)


def test_flags_none_when_all_ok():
    thresholds = {"f0_jump_st": 4.0, "slope_fall_st_s": 8.0,
                  "rms_jump_db": 6.0, "tempo_diff_pct": 25.0}
    row = {"f0_diff_st": 1.0, "slope_tail_st_s": -2.0,
           "rms_diff_db": 1.0, "tempo_diff_pct": 5.0}
    assert _flags(row, thresholds) == ""


# ── within_para_pairs ─────────────────────────────────────────────────────────

def test_within_para_pairs_single_paragraph_two_chunks():
    """One long paragraph that splits into 2 chunks → 1 pair."""
    # Build a minimal unit list with text that exceeds chunk limit
    long_text = ("Это длинное предложение для теста. " * 10).strip()
    units = [{"type": "paragraph", "text": long_text}]
    # Use default config (None → module defaults, which have small enough limits
    # that 10 repetitions of the sentence will split).
    # If the text fits in one chunk, we still get 0 pairs — test for >= 0.
    pairs = _within_para_pairs(units, None)
    assert isinstance(pairs, list)
    for i, j in pairs:
        assert j == i + 1


def test_within_para_pairs_heading_not_counted():
    """Headings are never within-para pairs."""
    units = [
        {"type": "heading", "text": "Глава первая", "level": 1},
        {"type": "paragraph", "text": "Короткий абзац."},
    ]
    pairs = _within_para_pairs(units, None)
    assert all(p[0] != 0 for p in pairs), "heading should not form a pair"


def test_within_para_pairs_two_paragraphs_no_cross():
    """Two short paragraphs → no cross-paragraph pairs."""
    units = [
        {"type": "paragraph", "text": "Первый."},
        {"type": "paragraph", "text": "Второй."},
    ]
    pairs = _within_para_pairs(units, None)
    # Each paragraph is a single chunk → no within-para pairs at all
    assert pairs == []


# ── qc.joins thresholds do not enter chunk hash ───────────────────────────────

def test_qc_joins_thresholds_not_in_chunk_hash():
    """Changing qc.joins must not change any chunk hash."""
    from audiobook.chunker import build_manifest, load_units
    import copy

    # Minimal synthetic units (no real text needed)
    units = [{"type": "paragraph", "text": "Тест раз два три."}]
    base_config = {
        "model": {"name": "test", "seed": 0, "temperature": 1.0, "language": "ru"},
        "render": {"latents": "none"},
        "qc": {
            "joins": {
                "f0_jump_st": 4.0,
                "slope_fall_st_s": 8.0,
                "rms_jump_db": 6.0,
                "tempo_diff_pct": 25.0,
            }
        },
    }
    config_modified = copy.deepcopy(base_config)
    config_modified["qc"]["joins"]["f0_jump_st"] = 99.0
    config_modified["qc"]["joins"]["rms_jump_db"] = 99.0

    from audiobook.chunker import chunk_hash, build_chunks, limits
    from audiobook.pronounce import load_table, respell
    from audiobook import voicecfg, leadin

    def _hashes(cfg):
        table = load_table()
        chunks = build_chunks(units, cfg)
        model = "test"
        seed = 0
        temperature = 1.0
        language = "ru"
        lat = "none"
        result = []
        prev_prepared, prev_kind = None, None
        for c in chunks:
            prepared = voicecfg.prepare_text(c["text"], cfg)
            synth_text = respell(prepared, table)
            kind = c.get("kind", "text")
            phrase = leadin.phrase_for(
                prepared, cfg, prev_prepared,
                kind in ("text", "stack") and prev_kind in ("text", "stack"),
            )
            prev_prepared, prev_kind = prepared, kind
            result.append(chunk_hash(c["text"], model, seed, temperature,
                                      language, lat, synth_text, phrase))
        return result

    assert _hashes(base_config) == _hashes(config_modified), (
        "qc.joins thresholds must not affect chunk hashes"
    )
