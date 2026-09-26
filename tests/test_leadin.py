"""Layer-1 tests for the context lead-in: firing rule, hash participation, and
the carrier-cut math. No models — the whisper word-timestamp step is stubbed."""
from __future__ import annotations

import numpy as np
import pytest

from audiobook import leadin

_CFG = {"render": {"leadin": {"phrase": "Вот что важно понять.", "max_chars": 55}}}
_PHRASE = "Вот что важно понять."  # normalizes to 4 words


# ── firing rule ────────────────────────────────────────────────────────────────

def test_fires_at_and_below_threshold():
    assert leadin.fires("x" * 55, _CFG) == _PHRASE
    assert leadin.fires("x" * 40, _CFG) == _PHRASE


def test_does_not_fire_above_threshold():
    assert leadin.fires("x" * 56, _CFG) is None


def test_disabled_when_no_config():
    assert leadin.fires("short", {}) is None
    assert leadin.fires("short", {"render": {}}) is None
    assert leadin.fires("short", {"render": {"leadin": None}}) is None
    # phrase present but no threshold → disabled (both keys required)
    assert leadin.fires("short", {"render": {"leadin": {"phrase": "x"}}}) is None


def test_pad_prepends_carrier():
    assert leadin.pad("Раз два три.", "Вот.") == "Вот. Раз два три."


# ── hash participation ──────────────────────────────────────────────────────────

def test_leadin_enters_hash_only_when_present():
    from audiobook.chunker import chunk_hash
    args = ("qwen3_tts", 42, 1.0, "ru", "latents-sha")
    base = chunk_hash("Раз два три.", *args)
    assert chunk_hash("Раз два три.", *args, leadin=None) == base      # None → unchanged
    assert chunk_hash("Раз два три.", *args) == base                   # default → unchanged
    with_lead = chunk_hash("Раз два три.", *args, leadin=_PHRASE)
    assert with_lead != base                                           # firing → new hash


def test_leadin_and_pronounce_are_independent_in_hash():
    from audiobook.chunker import chunk_hash
    args = ("qwen3_tts", 42, 1.0, "ru", "latents-sha")
    base = chunk_hash("Раз два три.", *args)
    pron = chunk_hash("Раз два три.", *args, synth_text="Раз двА три.")
    both = chunk_hash("Раз два три.", *args, synth_text="Раз двА три.", leadin=_PHRASE)
    assert len({base, pron, both}) == 3  # each transformation shifts the hash distinctly


# ── carrier cut ─────────────────────────────────────────────────────────────────

def _hyp(words_with_times):
    return list(words_with_times)


def test_trim_cuts_at_first_own_word(monkeypatch):
    # carrier = 4 words; own text begins at known index 4 ("раз").
    synth_text = "Вот что важно понять. Раз два."
    hyp = _hyp([
        ("вот", 0.0, 0.2), ("что", 0.2, 0.4), ("важно", 0.4, 0.7),
        ("понять", 0.7, 1.0),                                   # carrier ends at 1.0
        ("раз", 1.2, 1.5), ("два", 1.5, 1.9),                   # own words; pause 1.0→1.2
    ])
    monkeypatch.setattr(leadin, "_word_ts", lambda wav: hyp)
    wav = np.arange(48000, dtype=np.float32)  # 2 s @ 24 kHz, sample i has value i
    kept = leadin.trim_carrier(wav, synth_text, _PHRASE)
    # cut_start=1.2s, prev_end=1.0s, gap=0.2 → nudge back 0.10s → cut at ~1.1s ≈ 26400
    # (1.1*24000 is 26399.99… in float, so allow the off-by-one from truncation).
    cut = int(kept[0])
    assert abs(cut - 26400) <= 1                 # kept audio starts on the own word
    assert len(kept) == 48000 - cut              # tail is contiguous, nothing dropped after


def test_trim_raises_when_no_own_words():
    # synth_text is only the carrier → nothing to keep
    with pytest.raises(leadin.TrimFailed):
        leadin.trim_carrier(np.zeros(100, np.float32), _PHRASE, _PHRASE)


def test_trim_raises_when_boundary_not_aligned(monkeypatch):
    synth_text = "Вот что важно понять. Раз два."
    # whisper heard only the carrier — the own words never appear in the hyp
    hyp = _hyp([("вот", 0.0, 0.2), ("что", 0.2, 0.4),
                ("важно", 0.4, 0.7), ("понять", 0.7, 1.0)])
    monkeypatch.setattr(leadin, "_word_ts", lambda wav: hyp)
    with pytest.raises(leadin.TrimFailed):
        leadin.trim_carrier(np.zeros(48000, np.float32), synth_text, _PHRASE)


def test_align_backtrace_matches_identical():
    pairs = leadin._align(["a", "b", "c"], ["a", "b", "c"])
    assert pairs == [(0, 0), (1, 1), (2, 2)]


# ── shared synth-input helper (render == redo == qc re-synth) ───────────────────

def test_prepare_synth_text_pads_and_respells_short_chunk():
    from audiobook.synth import prepare_synth_text
    cfg = {"render": {"leadin": {"phrase": _PHRASE, "max_chars": 55}}}
    st, phrase = prepare_synth_text("раз два.", cfg, {"раз": "рАз"}, " .")
    assert phrase == _PHRASE
    assert st.startswith(_PHRASE)          # carrier prepended
    assert "рАз" in st                     # respell applied to the own word
    assert not st.endswith(" .")           # own text ends in "." → no sentinel


def test_prepare_synth_text_long_chunk_gets_no_carrier():
    from audiobook.synth import prepare_synth_text
    cfg = {"render": {"leadin": {"phrase": _PHRASE, "max_chars": 10}}}
    st, phrase = prepare_synth_text("это довольно длинный текст", cfg, {}, " .")
    assert phrase is None
    assert not st.startswith("Вот")        # no carrier on a long chunk
    assert st.endswith(" .")               # no terminal punct → sentinel appended
