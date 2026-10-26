"""Pronunciation dictionary: exact-string respellings applied to chunk text
right before synthesis, *after* normalization.

It does NOT touch the book text (.norm.txt) — the respelling only steers the
model's stress/reading. The manifest keeps the clean book text (QC/CER compare
against that); the respelling is what actually reaches the model.

Each entry that fires on a chunk changes that chunk's hash (see
chunker.chunk_hash), so a re-render picks up a dictionary edit — surgically:
chunks the dictionary does not touch keep their old hash and cached audio.
"""
from __future__ import annotations

import re
from pathlib import Path

from audiobook import paths

_PATH = paths.TEXT / "pronounce.yaml"


def load_table(path: Path | None = None) -> dict[str, str]:
    """Load {source_string: respelling}. Absent/empty file → empty table."""
    p = path if path is not None else _PATH
    if not p.exists():
        return {}
    import yaml
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(k): str(v) for k, v in data.items()}


def respell(text: str, table: dict[str, str]) -> str:
    """Replace each source string with its respelling, whole-word only.

    One pass over the text with a single alternation, longest keys first, so a
    phrase entry wins over a word inside it AND a replacement is never fed back
    into the table (a phrase value containing "тебя" must not be re-respelled
    by the "тебя" entry — that double-marked pron-test variants). Word
    boundaries (\\b, Unicode-aware) keep 'Отзывы' from firing inside a longer
    word. Identity when nothing matches — that is what keeps the hash stable.
    """
    if not table:
        return text
    keys = sorted(table, key=len, reverse=True)
    pat = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b")
    return pat.sub(lambda m: table[m.group(0)], text)
