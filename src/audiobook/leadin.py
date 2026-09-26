"""Context lead-in for short chunks.

A short chunk (a heading, a one-word quoted insert like «Я») gives the
voice-clone prompt too little text to hold the reference, so the synthesized
timbre drifts mid-utterance. Fix, validated by ear on ch13 (context-padding
experiment, variant c): prepend a neutral carrier sentence, synthesize the
padded text, then cut the carrier off using whisper word timestamps — keeping
only the chunk's own audio.

The carrier phrase and the char threshold live in config.yaml
(``render.leadin.{phrase,max_chars}``) and enter the chunk hash ONLY for chunks
the threshold fires on (see ``chunker.chunk_hash``), so padding re-queues
exactly the short chunks and leaves every other chunk's cache intact.

Only the cut needs whisper; ``carrier``/``fires``/``pad`` are pure config+string
logic (no models), so the chunker and hashing import this module cheaply.
"""
from __future__ import annotations

import numpy as np

_SAMPLE_RATE = 24000
# Cut this far back into the pre-boundary pause, so the kept audio starts crisply
# on the chunk's own first word rather than clipping its onset.
_GAP_NUDGE_S = 0.10


class TrimFailed(Exception):
    """Whisper could not locate the carrier/own-word boundary. The caller retries
    with another seed (a different generation aligns differently) rather than
    shipping audio with the carrier still audible."""


def carrier(config: dict) -> tuple[str, int] | None:
    """``(phrase, max_chars)`` from config, or ``None`` when lead-in is disabled."""
    lc = config.get("render", {}).get("leadin") or {}
    phrase = lc.get("phrase")
    if not phrase or "max_chars" not in lc:
        return None
    return phrase, int(lc["max_chars"])


def fires(text: str, config: dict) -> str | None:
    """The carrier phrase to prepend for this chunk, or ``None`` to leave it alone.
    Fires on ``len(text) <= max_chars`` (raw chunk text, before respell/sentinel)."""
    c = carrier(config)
    if c is None:
        return None
    phrase, max_chars = c
    return phrase if len(text) <= max_chars else None


def pad(text: str, phrase: str) -> str:
    """Prepend the carrier. Kept trivial and separate so the hash and the synth
    path build the padded string identically."""
    return f"{phrase} {text}"


# ── the cut (needs whisper; imported lazily so chunking stays model-free) ──────

_whisper = None


def _whisper_model():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        from audiobook import paths
        _whisper = WhisperModel(
            str(paths.MODELS / "whisper" / "small"), device="cpu", compute_type="int8"
        )
    return _whisper


def _word_ts(wav: np.ndarray) -> list[tuple[str, float, float]]:
    """``[(normalized_word, start_s, end_s)]`` for a mono float32 24 kHz wav.

    Writes a transient wav (whisper decodes+resamples via its own pipeline; the
    ndarray path would assume 16 kHz) under a pid-unique name in ``out/`` so
    parallel workers never collide, then removes it."""
    import os

    import soundfile as sf

    from audiobook import paths
    from audiobook.qc import normalize_for_cer

    paths.OUT.mkdir(parents=True, exist_ok=True)
    tmp = paths.OUT / f"_leadin_ts_{os.getpid()}.wav"
    try:
        sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16")
        segs, _ = _whisper_model().transcribe(
            str(tmp), language="ru", beam_size=5, word_timestamps=True
        )
        out = []
        for s in segs:
            for w in (s.words or []):
                nw = normalize_for_cer(w.word)
                if nw:
                    out.append((nw, float(w.start), float(w.end)))
        return out
    finally:
        tmp.unlink(missing_ok=True)


def _align(ref_words: list[str], hyp_words: list[str]) -> list[tuple]:
    """Levenshtein DP backtrace → ordered ``[(ref_idx|None, hyp_idx|None)]``."""
    n, m = len(ref_words), len(hyp_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + c)
    i, j, pairs = n, m, []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (
            0 if ref_words[i - 1] == hyp_words[j - 1] else 1
        ):
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return list(reversed(pairs))


def trim_carrier(wav: np.ndarray, synth_text: str, phrase: str) -> np.ndarray:
    """Drop the prepended carrier from a padded chunk's wav.

    ``synth_text`` is the full padded string that was fed to the model (respell +
    sentinel already applied); ``phrase`` is the carrier that was prepended. Both
    are normalized the same way as CER, so respelled stress marks and the
    sentinel fall away and the words match the whisper transcript.

    Aligns whisper word timestamps of the whole utterance to its known words, then
    cuts just before the first OWN word (index ``n_carrier`` in the known list).
    Raises ``TrimFailed`` if that boundary word has no whisper match."""
    from audiobook.qc import normalize_for_cer

    n_carrier = len(normalize_for_cer(phrase).split())
    known = normalize_for_cer(synth_text).split()
    if len(known) <= n_carrier:
        raise TrimFailed("no own words after carrier")
    hyp = _word_ts(wav)
    if not hyp:
        raise TrimFailed("whisper returned no words")
    pairs = _align(known, [h[0] for h in hyp])
    h = next((hj for ri, hj in pairs if ri == n_carrier and hj is not None), None)
    if h is None:
        raise TrimFailed(f"own-word boundary (known idx {n_carrier}) not aligned")
    cut_start = hyp[h][1]
    prev_end = hyp[h - 1][2] if h - 1 >= 0 else 0.0
    gap = max(cut_start - prev_end, 0.0)
    cut_t = cut_start - min(gap, _GAP_NUDGE_S)
    return np.asarray(wav[int(cut_t * _SAMPLE_RATE):], dtype=np.float32)
