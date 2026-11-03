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


def _ctc_frame_starts(ids: list[int], id2tok: dict[int, str], blank: int) -> list[int]:
    """Frame index (in the argmax sequence) where each output token starts."""
    starts, prev, span_start = [], None, 0
    for i, tok_id in enumerate(ids):
        if tok_id == prev:
            continue
        if prev is not None and prev != blank:
            tok = id2tok.get(prev, "")
            if tok and tok not in ("|", " ", "<s>", "</s>", "<unk>"):
                starts.append(span_start)
        prev, span_start = tok_id, i
    if prev is not None and prev != blank:
        tok = id2tok.get(prev, "")
        if tok and tok not in ("|", " ", "<s>", "</s>", "<unk>"):
            starts.append(span_start)
    return starts


def ctc_greedy_counts(ids: list[int], id2tok: dict[int, str],
                      blank: int) -> tuple[list[str], list[int]]:
    """Like ctc_greedy, but also returns frame count for each output token."""
    tokens, counts = [], []
    prev, span = None, 0
    for i in ids:
        if i == prev:
            span += 1
            continue
        if prev is not None and prev != blank:
            tok = id2tok.get(prev, "")
            if tok and tok not in ("|", " ", "<s>", "</s>", "<unk>"):
                tokens.append(tok)
                counts.append(span)
        prev, span = i, 1
    if prev is not None and prev != blank:
        tok = id2tok.get(prev, "")
        if tok and tok not in ("|", " ", "<s>", "</s>", "<unk>"):
            tokens.append(tok)
            counts.append(span)
    return tokens, counts


# ── stress detection helpers (layer-1 tested) ────────────────────────────────

_IPA_IUY = {"i", "u", "ɨ", "ʉ"}   # и/у/ы in IPA — don't reduce → need duration/energy
_CYR_IUY = set("иуы")


def analyze_iyU(form: str, tokens: list[str],
                n_frames: list[int], rms_per_tok: list[float]) -> dict:
    """Extended analyze for и/у/ы stressed vowels: duration + energy score.

    n_frames[i] and rms_per_tok[i] must match tokens[i].
    Score = geometric mean of (duration_ratio, energy_ratio) vs word-vowel average.
    Verdict: ok (>1.2), bad (<0.8), unknown otherwise.
    """
    word, stress = parse_expect(form)
    vowels_cyr = [ch for ch in word if ch in _CYR_VOWELS]
    if not vowels_cyr:
        return analyze(form, tokens)
    target_cyr = vowels_cyr[stress]
    if target_cyr not in _CYR_IUY:
        return analyze(form, tokens)

    vowel_toks = [(i, _base(t)) for i, t in enumerate(tokens) if is_vowel(t)]
    if len(vowel_toks) != len(vowels_cyr):
        # alignment failure → fall back to standard analyze
        return analyze(form, tokens)

    dur = [n_frames[i] for i, _ in vowel_toks]
    rms = [rms_per_tok[i] for i, _ in vowel_toks]
    if not dur:
        return analyze(form, tokens)

    mean_dur = sum(dur) / len(dur) or 1.0
    mean_rms = sum(rms) / len(rms) or 1e-9

    t_dur = dur[stress] / mean_dur
    t_rms = max(rms[stress], 1e-9) / mean_rms
    score = (t_dur * t_rms) ** 0.5

    res = analyze(form, tokens)
    res["iyU_score"] = round(score, 3)
    if score > 1.2:
        res["verdict"] = "ok"
    elif score < 0.8:
        res["verdict"] = "bad"
    else:
        res["verdict"] = "unknown"
    return res


def stress_from_pron(key: str, value: str) -> str | None:
    """Build an expected-form string like "запИть" from a pronounce.yaml entry.

    Handles both the normal case ("запить" → "запИть") and the doubled-initial-
    vowel exception ("Отзывы" → "Оотзывы").  Returns None on parse failure.
    """
    try:
        _plain_v, vowel_idx = parse_expect(value)
    except (ValueError, IndexError):
        return None
    word = key.lower()
    vowels = [i for i, ch in enumerate(word) if ch in _CYR_VOWELS]
    # The value may have an extra leading vowel (doubled-vowel exception) but
    # the same vowel count as the key at that index.
    if vowel_idx >= len(vowels):
        return None
    char_pos = vowels[vowel_idx]
    return word[:char_pos] + word[char_pos].upper() + word[char_pos + 1:]


def parse_acc_word(word_with_plus: str) -> tuple[str, int] | None:
    """Parse a RUAccent-annotated token like "зап+ить" → ("запить", vowel_idx).

    RUAccent places '+' immediately BEFORE the stressed vowel.
    Returns None if no '+' found or the character after '+' is not a vowel.
    """
    if "+" not in word_with_plus:
        return None
    pos = word_with_plus.index("+")
    plain = word_with_plus.replace("+", "").lower()
    if pos >= len(plain) or plain[pos] not in _CYR_VOWELS:
        return None
    vowel_idx = sum(1 for i in range(pos) if plain[i] in _CYR_VOWELS)
    return plain, vowel_idx


def stress_from_acc_line(word_lower: str, acc_line: str) -> str | None:
    """Find word_lower in an acc.txt line and return its expected stressed form."""
    import re
    # Tokenize acc_line into words (keeping + markers)
    for token in re.split(r"\s+|(?=[.!?,;:…»«()\"])|(?<=[.!?,;:…»«()])", acc_line):
        token = token.strip()
        parsed = parse_acc_word(token)
        if parsed is None:
            continue
        plain, vowel_idx = parsed
        if plain == word_lower:
            vowels = [i for i, ch in enumerate(plain) if ch in _CYR_VOWELS]
            if vowel_idx < len(vowels):
                cp = vowels[vowel_idx]
                return plain[:cp] + plain[cp].upper() + plain[cp + 1:]
    return None


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

    def phonemes_scored(self, wav16: np.ndarray) -> tuple[list[str], list[int], list[float]]:
        """Returns (tokens, n_frames, rms_per_token) for и/у/ы scoring."""
        x = (wav16 - wav16.mean()) / (wav16.std() + 1e-7)
        with self._torch.no_grad():
            logits = self.model(self._torch.tensor(x[None, :], dtype=self._torch.float32)).logits
        ids = logits.argmax(-1)[0].tolist()
        tokens, counts = ctc_greedy_counts(ids, self.id2tok, self.blank)
        # wav2vec2-xlsr stride: 320 samples per CTC frame at 16 kHz
        stride = 320
        rms_vals = []
        # Reconstruct which frames each token occupies from the argmax sequence
        # by replaying ctc_greedy_counts logic with frame-start tracking
        frame_starts = _ctc_frame_starts(ids, self.id2tok, self.blank)
        for (tok, n), fstart in zip(zip(tokens, counts), frame_starts):
            a = fstart * stride
            b = min(len(wav16), (fstart + n) * stride)
            seg = wav16[a:b]
            rms_vals.append(float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0)
        return tokens, counts, rms_vals


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


_MAX_PER_WORD = 5   # max chunk hits per candidate word


def _build_candidates(config: dict) -> tuple[dict[str, str | None], bool]:
    """Return {word_lower: form_or_None} and ruaccent_available flag.

    For pronounce.yaml entries: form is e.g. "запИть" (directly parseable).
    For stress_watch words: form is None (stress determined later per-chunk).
    """
    from audiobook.pronounce import load_table
    from audiobook.probe import load_watch

    candidates: dict[str, str | None] = {}

    # pronounce.yaml — explicit expected stress
    table = load_table()
    for key, value in table.items():
        word = key.lower()
        # Only simple single-word entries (no spaces)
        if " " not in word:
            form = stress_from_pron(key, value)
            if form:
                candidates[word] = form

    # stress_watch.yaml — need RUAccent for expected stress
    for w in load_watch():
        if w not in candidates:
            candidates[w] = None  # stress determined from acc.txt/RUAccent

    # Check RUAccent availability
    nn_path = paths.MODELS / "nn"
    dict_path = paths.MODELS / "dictionary"
    ruaccent_ok = nn_path.exists() and dict_path.exists()
    return candidates, ruaccent_ok


def _load_acc_lines(nn: str, slug: str) -> list[str] | None:
    """Load text/{nn}_{slug}.acc.txt as a list of lines; None if missing."""
    p = paths.TEXT / f"{nn}_{slug}.acc.txt"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").splitlines()


def run_auto(config: dict, section: str, first: int | None = None) -> int:
    """EXPERIMENTAL: auto stress check for a whole section.

    Candidates come from text/stress_watch.yaml + text/pronounce.yaml.
    Expected stress: pronounce.yaml value first, then acc.txt, then RUAccent.
    """
    import re
    from audiobook.assemble import preview_name
    from audiobook.chunker import _read_manifest, load_units, section_config
    from audiobook.qc import _release, load_whisper

    sec_dir = paths.OUT / "sections" / section
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"phoneme-check --auto: манифест не найден: {manifest_path}")

    manifest = _read_manifest(manifest_path)
    if first is not None:
        manifest = manifest[:first]
    done_rows = [r for r in manifest if r.get("status") == "done"]
    if not done_rows:
        raise SystemExit("phoneme-check --auto: нет чанков status=done — сначала synth+qc")

    nn, slug = section.split("_", 1)
    units = load_units(nn, slug)
    acc_lines = _load_acc_lines(nn, slug)

    # Unit index per chunk (parallel to manifest)
    from audiobook.chunker import build_chunks, chunk_prose, limits, split_step_label
    sec_cfg = section_config(config, section)
    chunks_raw = build_chunks(units, sec_cfg)
    pauses = sec_cfg.get("pauses_ms") or {}
    p_step = pauses.get("step_label")
    lim = limits(sec_cfg)

    unit_of: list[int] = []
    for ui, u in enumerate(units):
        if u["type"] == "heading":
            from audiobook.chunker import _heading_chunks
            n = len(_heading_chunks(u["text"], 0, pauses))
            unit_of.extend([ui] * n)
        elif u["type"] == "stack":
            unit_of.append(ui)
        else:
            text = u["text"]
            if p_step:
                label, text = split_step_label(text)
                if label:
                    unit_of.append(ui)
            pieces = chunk_prose(text, lim)
            unit_of.extend([ui] * len(pieces))

    candidates, ruaccent_ok = _build_candidates(config)
    if not ruaccent_ok:
        print("ЭКСПЕРИМЕНТ phoneme-check --auto: RUAccent недоступен — "
              "обрабатываю только pronounce.yaml (stress_watch без стресса пропущены)")

    _WORD_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
    word_hits: dict[str, int] = {}   # word → how many chunks already processed
    chunks_dir = sec_dir / "chunks"

    pm = PhonemeModel()
    wm = load_whisper()
    results = []
    timestamps_ms: list[float] = []
    acc = 0.0
    for r in manifest:
        acc += r.get("duration_ms") or 0.0
        timestamps_ms.append(acc)

    try:
        for idx, row in enumerate(manifest):
            if row.get("status") != "done":
                continue
            text = row["text"]
            words_in_chunk = {w.lower() for w in _WORD_RE.findall(text)}
            hits = {w: candidates[w] for w in words_in_chunk if w in candidates}
            if not hits:
                continue

            # Determine expected forms for words that need acc.txt/RUAccent
            forms = {}
            for word, form in hits.items():
                if form is not None:
                    forms[word] = form
                    continue
                # Try acc.txt line for this chunk's unit
                if acc_lines and idx < len(unit_of):
                    ui = unit_of[idx]
                    if ui < len(acc_lines):
                        form = stress_from_acc_line(word, acc_lines[ui])
                if form is None and ruaccent_ok:
                    from audiobook.accent import accent_lines
                    accented = accent_lines([text])[0]
                    form = stress_from_acc_line(word, accented)
                if form is None:
                    continue
                forms[word] = form

            if not forms:
                continue
            # Cap per-word occurrences
            forms = {w: f for w, f in forms.items()
                     if word_hits.get(w, 0) < _MAX_PER_WORD}
            if not forms:
                continue

            wav_path = chunks_dir / f"{row['id']}.wav"
            if not wav_path.exists():
                continue

            ts_ms = timestamps_ms[idx]
            time_str = f"{int(ts_ms // 60000)}:{int(ts_ms // 1000 % 60):02d}"

            import soundfile as sf
            audio, sr = sf.read(str(wav_path), dtype="float32")
            from audiobook.qc import _norm_word, transcribe_words
            _txt, wds = transcribe_words(wm, wav_path)

            for word, form in forms.items():
                word_hits[word] = word_hits.get(word, 0) + 1
                target = _norm_word(form.lower())
                hit = next((w for w in wds if _norm_word(w["w"]) == target), None)
                if hit is None:
                    results.append({"time": time_str, "word": word, "form": form,
                                    "verdict": "нет слова", "score": ""})
                    continue
                a = max(0, int((hit["s"] - 0.05) * sr))
                b = min(len(audio), int((hit["e"] + 0.05) * sr))
                seg16 = _to16k(audio[a:b], sr)

                # Use scored variant when target vowel is и/у/ы
                word_cyr = form.lower()
                vowels_cyr = [ch for ch in word_cyr if ch in _CYR_VOWELS]
                try:
                    _, stress_idx = parse_expect(form)
                except ValueError:
                    stress_idx = -1
                use_scored = (0 <= stress_idx < len(vowels_cyr)
                              and vowels_cyr[stress_idx] in _CYR_IUY)
                if use_scored:
                    toks, n_frames, rms_v = pm.phonemes_scored(seg16)
                    res = analyze_iyU(form, toks, n_frames, rms_v)
                else:
                    res = analyze(form, pm.phonemes(seg16))

                results.append({
                    "time": time_str,
                    "word": word,
                    "form": form,
                    "verdict": res.get("verdict", "?"),
                    "score": str(res.get("iyU_score", "")),
                    "phonemes": res.get("phonemes", ""),
                })
    finally:
        _release(wm)

    stem = preview_name(first)
    out_path = sec_dir / f"{stem}.stress.tsv"
    _write_stress_tsv(results, out_path)
    print(f"ЭКСПЕРИМЕНТ phoneme-check --auto: {len(results)} слов → {out_path}")
    for r in results:
        flag = "  ✗" if r["verdict"] not in ("ok", "нет слова") else ""
        score = f"  [{r['score']}]" if r["score"] else ""
        print(f"{r['time']:<8} {r['word']:<14} {r['form']:<14} {r['verdict']}{score}{flag}")
    return 0


def _write_stress_tsv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["time", "word", "form", "verdict", "score", "phonemes"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")


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
