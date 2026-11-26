import re

import pytest

from audiobook.rhythm_syntax import coordination_boundaries, protected_commas


def tree(text, specs):
    spans = list(re.finditer(r"[А-Яа-яЁё]+|[^\s]", text))
    assert len(spans) == len(specs)
    return [dict(id=i, start=m.start(), end=m.end(), text=m.group(),
                 head=h, deprel=r, upos=p)
            for i, (m, (h, r, p)) in enumerate(zip(spans, specs), 1)]


def test_list_without_colon_and_long_items():
    text = "Большие красные яблоки, сладкие груши, свежие сливы."
    t = tree(text, [(3,"amod","ADJ"), (3,"amod","ADJ"), (0,"root","NOUN"),
                    (6,"punct","PUNCT"), (6,"amod","ADJ"), (3,"conj","NOUN"),
                    (9,"punct","PUNCT"), (9,"amod","ADJ"), (3,"conj","NOUN"),
                    (3,"punct","PUNCT")])
    assert coordination_boundaries(text,t)["candidate_offsets"] == [
        i for i,c in enumerate(text) if c == ","]


def test_subordination_not_list():
    text = "Знаю, где дом."
    t = tree(text, [(0,"root","VERB"), (4,"punct","PUNCT"),
                    (4,"advmod","ADV"), (1,"ccomp","NOUN"), (1,"punct","PUNCT")])
    assert coordination_boundaries(text,t)["candidate_offsets"] == []


def test_quoted_list_protected():
    text = '«Яблоки, груши».'
    t = tree(text, [(2,"punct","PUNCT"), (0,"root","NOUN"),
                    (4,"punct","PUNCT"), (2,"conj","NOUN"),
                    (2,"punct","PUNCT"), (2,"punct","PUNCT")])
    result = coordination_boundaries(text,t)
    assert result["candidate_offsets"] == []
    assert result["protected_offsets"] == [text.index(",")]


def test_numeric_and_unbalanced_quotes():
    assert protected_commas("3,14") == {1}
    assert protected_commas('«один, два, три') == {5, 10}
    assert protected_commas('"один, два", три') == {5}


def test_misalignment_rejected():
    text = "Яблоки, груши."
    t = tree(text, [(0,"root","NOUN"), (3,"punct","PUNCT"),
                    (1,"conj","NOUN"), (1,"punct","PUNCT")])
    t[2]["start"] += 1
    with pytest.raises(ValueError, match="ALIGNMENT"):
        coordination_boundaries(text,t)


def test_cycle_rejected():
    text = "Яблоки, груши."
    t = tree(text, [(0,"root","NOUN"), (3,"punct","PUNCT"),
                    (4,"conj","NOUN"), (3,"punct","PUNCT")])
    with pytest.raises(ValueError, match="CYCLE"):
        coordination_boundaries(text,t)
