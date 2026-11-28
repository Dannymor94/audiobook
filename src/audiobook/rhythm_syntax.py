"""Parser-independent, read-only coordination boundary proposals for ALG-03.

Input is an externally produced UD-style tree with exact character offsets.
No parser/model download or TTS. Proposals are not approved acoustic pauses.
"""
from __future__ import annotations

import hashlib
import re

_LEXICAL = frozenset({"NOUN", "PROPN", "ADJ", "ADV", "NUM", "PRON"})
_OPEN = {"«": "»", "(": ")", "[": "]", "{": "}", "„": "“", "“": "”", '"': '"'}
_CLOSE = frozenset(_OPEN.values())
_GROUP = re.compile(r"[А-Яа-яЁё]+(?:[-‐‑][А-Яа-яЁё]+)*")


def protected_commas(text: str) -> set[int]:
    stack: list[str] = []
    result = set()
    for i, c in enumerate(text):
        if stack and c == stack[-1]:
            stack.pop()
        elif c in _OPEN:
            stack.append(_OPEN[c])
        elif c in _CLOSE:
            # Ambiguous/unbalanced quote/bracket: no proposals for this sentence.
            return {j for j, ch in enumerate(text) if ch == ","}
        elif c == ",":
            if stack or (i and i+1 < len(text)
                         and text[i-1].isdigit() and text[i+1].isdigit()):
                result.add(i)
    if stack:
        return {j for j, ch in enumerate(text) if ch == ","}
    return result


def coordination_boundaries(text: str, tokens: list[dict]) -> dict:
    """One complete sentence; tokens ordered, 1-based IDs, one root (head 0).

    Required fields: id, start, end, text, head, deprel, upos.
    Reject partial/misaligned/non-tree parses, including missing punctuation.
    Accept only direct nominal/adjectival/adverbial conjuncts with an exact
    comma gap between contiguous, non-overlapping component subtrees.
    Coordinated clauses, ambiguous nested coordination and protected commas
    stay unproposed. No automatic insertion or splitting.
    """
    by_id = {}
    cursor = 0
    for i, t in enumerate(tokens, 1):
        start, end = t["start"], t["end"]
        if (type(t["id"]) is not int or t["id"] != i
                or type(start) is not int or type(end) is not int
                or not cursor <= start < end <= len(text)
                or text[cursor:start].strip()
                or text[start:end] != t["text"]
                or type(t["head"]) is not int
                or not 0 <= t["head"] <= len(tokens)
                or t["head"] == i
                or not isinstance(t["deprel"], str)
                or not isinstance(t["upos"], str)):
            raise ValueError("SYNTAX_ALIGNMENT_MISMATCH")
        by_id[i] = t
        cursor = end
    if not tokens or text[cursor:].strip():
        raise ValueError("SYNTAX_SOURCE_NOT_EXHAUSTED")
    roots = [i for i, t in by_id.items() if t["head"] == 0]
    if len(roots) != 1 or by_id[roots[0]]["deprel"] != "root":
        raise ValueError("SYNTAX_ROOT_MISMATCH")
    children: dict[int, list[int]] = {i: [] for i in by_id}
    for i, t in by_id.items():
        if t["head"]:
            children[t["head"]].append(i)
        seen = {i}
        h = t["head"]
        while h:
            if h in seen:
                raise ValueError("SYNTAX_CYCLE")
            seen.add(h)
            h = by_id[h]["head"]

    def rel(i: int) -> str:
        return by_id[i]["deprel"].split(":")[0]

    def component(root: int) -> set[int]:
        result = set()
        todo = [root]
        while todo:
            node = todo.pop()
            result.add(node)
            todo.extend(c for c in children[node] if rel(c) not in {"conj", "cc", "punct"})
        return result

    protected = protected_commas(text)
    result = set()
    for root in by_id:
        conjuncts = [c for c in children[root] if rel(c) == "conj"]
        if not conjuncts or rel(root) == "conj":
            continue
        members = [root, *conjuncts]
        if any(by_id[i]["upos"] not in _LEXICAL for i in members):
            continue
        groups = [component(i) for i in members]
        if any(any(rel(c) == "conj" and c not in conjuncts
                   for i in g for c in children[i]) for g in groups):
            continue
        spans = []
        for group in groups:
            lo, hi = min(group), max(group)
            if group != set(range(lo, hi+1)):
                break
            if any(by_id[i]["upos"] in {"VERB", "AUX", "SCONJ", "PUNCT"} for i in group):
                break
            spans.append((by_id[lo]["start"], by_id[hi]["end"]))
        else:
            spans.sort()
            for left, right in zip(spans, spans[1:]):
                gap = text[left[1]:right[0]]
                if left[1] <= right[0] and gap.strip() == ",":
                    offset = left[1] + gap.index(",")
                    if offset not in protected:
                        result.add(offset)
    # Hyphenated lexical spans must never be cut. A comma cannot be inside
    # these spans; keeping the check explicit documents the invariant.
    assert all(not any(m.start() <= i < m.end() for m in _GROUP.finditer(text))
               for i in result)
    return {"policy": "ud-coordination-review-v1",
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "candidate_offsets": sorted(result),
            "protected_offsets": sorted(protected)}
