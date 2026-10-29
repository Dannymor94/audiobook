"""Restore a missing «ё» in model input, using the book's own spelling.

The manuscript mixes «ребёнок» ×149 with «ребенок» ×55, «слёзы» ×16 with
«слезы» ×5. Without ё the model guesses — «слезЫ» was heard in ch13. When
the book itself writes a word with ё at least as often as without, the no-ё
occurrences are written with ё for the model. Homographs where both
spellings are real words (все/всё, чем/чём, берет/берёт…) are never touched.

Model input only (text_prep.yo_restore): .norm.txt and the manifest keep the
author's spelling; changed chunks re-hash through synth_text.
"""
from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from audiobook import paths

# Both spellings are real, different words — the book's majority says nothing
# about a given occurrence.
HOMOGRAPHS = frozenset({
    "все", "всем", "чем", "небо", "полет", "берет", "осел", "узнает",
    "узнаешь", "узнаем", "осознаем", "счета", "передохнуть", "совершенный",
    "падеж", "истекший",
})

_WORD = re.compile(r"[А-Яа-яЁё]+")


def _fold(w: str) -> str:
    return w.replace("ё", "е").replace("Ё", "Е")


def build_map(texts: list[str]) -> dict[str, str]:
    """{no-ё lowercase form: ё form} for words the book spells with ё at least
    as often as without, homographs excluded."""
    freq = Counter(w.lower() for t in texts for w in _WORD.findall(t))
    by_fold: dict[str, dict[str, int]] = {}
    for w, n in freq.items():
        by_fold.setdefault(_fold(w), {})[w] = n
    out: dict[str, str] = {}
    for plain, forms in by_fold.items():
        if plain in HOMOGRAPHS or plain not in forms:
            continue
        yo = [(n, f) for f, n in forms.items() if f != plain]
        if not yo:
            continue
        n_yo, f_yo = max(yo)
        if n_yo >= forms[plain]:
            out[plain] = f_yo
    return out


@lru_cache(maxsize=4)
def _book_map(text_dir: str, stamp: float) -> dict[str, str]:
    files = sorted(Path(text_dir).glob("*.norm.txt"))
    return build_map([f.read_text(encoding="utf-8") for f in files])


def book_map() -> dict[str, str]:
    files = list(paths.TEXT.glob("*.norm.txt"))
    stamp = max((f.stat().st_mtime for f in files), default=0.0)
    return _book_map(str(paths.TEXT), stamp)


def restore(text: str, mapping: dict[str, str] | None = None) -> str:
    m = book_map() if mapping is None else mapping

    def repl(mo: re.Match) -> str:
        w = mo.group()
        r = m.get(w.lower())
        if r is None:
            return w
        if w.isupper() and len(w) > 1:
            return r.upper()
        return r[0].upper() + r[1:] if w[0].isupper() else r

    return _WORD.sub(repl, text)
