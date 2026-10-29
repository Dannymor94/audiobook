"""EXPERIMENTAL: check stress and inserted glides with a phoneme recognizer.

Whisper hears words, so "тЕбя" and "тебЯ" look the same to QC. A phoneme CTC
model (wav2vec2 XLSR-53 fine-tuned on eSpeak IPA, Apache-2.0, 16 kHz) hears
sounds:
  * Russian unstressed vowels are reduced — о/а → [ɐ ə], е/я → [ɪ] — while the
    stressed one keeps full quality [a o e ɛ i u ɨ æ]. So "which vowel is full"
    hints where the stress fell.
  * An inserted glide shows up as an extra [j]: "теб-й-а", "дыш-й-и".

This is a heuristic and must be validated against human labels before it is
trusted (ch13 pron-test files already labelled by ear). Verdicts are
"ok" / "STRESS?" / "J+" / "?" (could not align vowels).

Weights are NOT downloaded here (runtime is offline): see
scripts/fetch_phoneme_model.py, an explicit one-off step.

    ./run.sh phoneme-check --dir out/pron_test/<dir> --expect заЕсть запИть заснУть
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from audiobook import paths

MODEL_ID = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
HUB_DIR = paths.MODELS / "hf" / "hub" / "models--facebook--wav2vec2-xlsr-53-espeak-cv-ft"
SR = 16_000

_CYR_VOWELS = "аеёиоуыэюя"
_FULL = set("aoeɛiuɨæɔʉ")
_REDUCED = set("ɐəɪʊɵʌ")
_JOT_AFTER = set(_CYR_VOWELS) | {"ъ", "ь"}


# ── pure logic (layer-1 tested) ───────────────────────────────────────────────

def parse_expect(form: str) -> tuple[str, int]:
    """"запИть" → ("запить", 1): plain lowercase word + index of the stressed
    vowel among its vowels. Exactly one uppercase vowel (or ё) marks stress."""
    plain = form.lower()
    vowels = [i for i, ch in enumerate(plain) if ch in _CYR_VOWELS]
    marked = [k for k, i in enumerate(vowels) if form[i].isupper() or plain[i] == "ё"]
    if len(marked) != 1:
        raise ValueError(f"{form!r}: отметь ровно одну ударную гласную заглавной буквой")
    return plain, marked[0]


def expected_j(word: str) -> int:
    """How many [j] the spelling implies: й; е/ё/ю/я word-initially or after a
    vowel, ъ or ь; и after ь (чьи). "тебя", "дыши" → 0."""
    w = word.lower()
    n = 0
    for i, ch in enumerate(w):
        prev = w[i - 1] if i else ""
        if ch == "й":
            n += 1
        elif ch in "еёюя" and (i == 0 or prev in _JOT_AFTER):
            n += 1
        elif ch == "и" and prev == "ь":
            n += 1
    return n


def _base(tok: str) -> str:
    return tok.replace("ː", "").replace("ʲ", "").replace("ˈ", "").replace("ˌ", "")


def is_vowel(tok: str) -> bool:
    b = _base(tok)
    return bool(b) and (b[0] in _FULL or b[0] in _REDUCED)


def analyze(form: str, tokens: list[str]) -> dict:
    """Verdict for one expected word given its recognized phoneme tokens."""
    word, stress = parse_expect(form)
    n_letters = sum(ch in _CYR_VOWELS for ch in word)
    vowels = [_base(t) for t in tokens if is_vowel(t)]
    rec_j = sum(_base(t) == "j" for t in tokens)
    res = {"word": word, "phonemes": " ".join(tokens), "vowels": vowels,
           "extra_j": max(0, rec_j - expected_j(word))}
    if res["extra_j"]:
        res["verdict"] = "J+"
    elif len(vowels) != n_letters:
        res["verdict"] = "?"
    elif vowels[stress][0] in _FULL:
        res["verdict"] = "ok"
    else:
        res["verdict"] = "STRESS?"
    return res


def ctc_greedy(ids: list[int], id2tok: dict[int, str], blank: int) -> list[str]:
    out, prev = [], None
    for i in ids:
        if i != prev and i != blank:
            tok = id2tok.get(i, "")
            if tok and tok not in ("|", " ", "<s>", "</s>", "<unk>"):
                out.append(tok)
        prev = i
    return out


# ── model ─────────────────────────────────────────────────────────────────────

def _snapshot() -> Path:
    snaps = HUB_DIR / "snapshots"
    if not snaps.is_dir():
        raise SystemExit(f"нет весов фонемной модели: {HUB_DIR}\n"
                         "скачать один раз: uv run python scripts/fetch_phoneme_model.py")
    ref = HUB_DIR / "refs" / "main"
    if ref.is_file():
        cand = snaps / ref.read_text(encoding="utf-8").strip()
        if cand.is_dir():
            return cand
    return sorted(p for p in snaps.iterdir() if p.is_dir())[-1]


class PhonemeModel:
    def __init__(self) -> None:
        import torch
        from transformers import Wav2Vec2ForCTC
        snap = _snapshot()
        self._torch = torch
        self.model = Wav2Vec2ForCTC.from_pretrained(str(snap)).eval()
        vocab = json.loads((snap / "vocab.json").read_text(encoding="utf-8"))
        self.id2tok = {v: k for k, v in vocab.items()}
        self.blank = vocab.get("<pad>", 0)

    def phonemes(self, wav16: np.ndarray) -> list[str]:
        x = (wav16 - wav16.mean()) / (wav16.std() + 1e-7)  # processor-style normalization
        with self._torch.no_grad():
            logits = self.model(self._torch.tensor(x[None, :], dtype=self._torch.float32)).logits
        ids = logits.argmax(-1)[0].tolist()
        return ctc_greedy(ids, self.id2tok, self.blank)


def _to16k(wav: np.ndarray, sr: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly
    g = gcd(sr, SR)
    return resample_poly(wav, SR // g, sr // g).astype(np.float32)


def check_wav(pm: PhonemeModel, wm, wav_path: Path, forms: list[str]) -> list[dict]:
    """Locate each expected word via whisper word timestamps, crop it, analyze."""
    import soundfile as sf

    from audiobook.qc import _norm_word, transcribe_words
    audio, sr = sf.read(str(wav_path), dtype="float32")
    _txt, words = transcribe_words(wm, wav_path)
    out = []
    for form in forms:
        target = _norm_word(parse_expect(form)[0])
        hit = next((w for w in words if _norm_word(w["w"]) == target), None)
        if hit is None:
            out.append({"word": target, "verdict": "нет слова", "phonemes": "",
                        "heard": " ".join(w["w"] for w in words)})
            continue
        a = max(0, int((hit["s"] - 0.05) * sr))
        b = min(len(audio), int((hit["e"] + 0.05) * sr))
        res = analyze(form, pm.phonemes(_to16k(audio[a:b], sr)))
        res["p"] = hit["p"]
        out.append(res)
    return out


def run(config: dict, dir_: str, forms: list[str]) -> int:
    from audiobook.qc import _release, load_whisper
    d = Path(dir_)
    if not d.is_absolute():
        d = paths.ROOT / d
    wavs = sorted(d.glob("*.wav"), key=lambda p: (len(p.stem), p.stem))
    if not wavs:
        raise SystemExit(f"нет wav в {d}")
    for f in forms:
        parse_expect(f)  # fail early on a bad form
    pm = PhonemeModel()
    wm = load_whisper()
    try:
        for p in wavs:
            for r in check_wav(pm, wm, p, forms):
                extra = (f"  [{r['phonemes']}]" if r.get("phonemes")
                         else f"  (whisper: {r.get('heard', '')})")
                print(f"{p.stem:>4}  {r['word']:<12} {r['verdict']:<9}{extra}")
    finally:
        _release(wm)
    return 0
