"""Adapter tests use synthetic parser objects, not downloaded models."""
from types import SimpleNamespace as NS

import pytest

from audiobook.rhythm_spacy import model_digest, propose


def document():
    text = "Яблоки, груши. Сливы, персики."
    words = ["Яблоки", ",", "груши", ".", "Сливы", ",", "персики", "."]
    tokens = []
    cursor = 0
    for i, word in enumerate(words):
        start = text.index(word, cursor)
        cursor = start + len(word)
        tokens.append(NS(i=i, idx=start, text=word, is_space=False,
                         pos_="PUNCT" if word in ",." else "NOUN",
                         dep_=["ROOT", "punct", "conj", "punct"][i % 4]))
    for i, t in enumerate(tokens):
        t.head = tokens[i-i % 4]
    class Sentence(list):
        pass
    sents = []
    for i in (0, 4):
        sent = Sentence(tokens[i:i+4])
        sent.start_char = sent[0].idx
        sent.end_char = sent[-1].idx + 1
        sents.append(sent)
    return text, NS(text=text, sents=sents)


def test_offsets_second_sentence():
    text, doc = document()
    assert propose(text, doc)["candidate_offsets"] == [
        i for i, c in enumerate(text) if c == ","]


def test_cross_sentence_head_rejected():
    text, doc = document()
    doc.sents[1][2].head = doc.sents[0][0]
    with pytest.raises(ValueError, match="HEAD_OUTSIDE"):
        propose(text, doc)


def test_missing_sentence_rejected():
    text, doc = document()
    doc.sents.pop()
    with pytest.raises(ValueError, match="NOT_EXHAUSTED"):
        propose(text, doc)


def test_model_digest_binds_contents(tmp_path):
    root = tmp_path / "model"
    root.mkdir()
    p = root / "weights"
    p.write_bytes(b"one")
    before = model_digest(root)
    assert model_digest(root) == before
    p.write_bytes(b"two")
    assert model_digest(root) != before
