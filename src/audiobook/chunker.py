"""Chunker + manifest. Reads .norm.txt (text) and blocks JSON (structure),
emits out/sections/NN_<slug>/manifest.jsonl. Does NOT synthesize.

Rules: target 120-220 chars, hard cap 250, min 40 (merge forward); config
chunking: {target, cap, min_len} overrides (1.7B: 180/180/40).
Paragraph is always a boundary. Never split inside quotes/brackets.
Never end a chunk on a preposition, conjunction or "не".
Heading = own chunk (pause by level). Stack lines = own chunks, 500ms between.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import NamedTuple

from audiobook import paths, voicecfg

TARGET = 220
CAP = 250
MIN_LEN = 40


class Limits(NamedTuple):
    """Chunk length rules. Defaults = the module constants (the 0.6B-era rules);
    config ``chunking: {target, cap, min_len}`` overrides them. 1.7B garbled
    word-level on long chunks — 180 was the validated cap."""
    target: int = TARGET
    cap: int = CAP
    min_len: int = MIN_LEN


def limits(config: dict | None) -> Limits:
    c = (config or {}).get("chunking") or {}
    return Limits(int(c.get("target", TARGET)), int(c.get("cap", CAP)),
                  int(c.get("min_len", MIN_LEN)))

PAUSE_SENTENCE = 350
PAUSE_PARAGRAPH = 900
PAUSE_STACK = 500
PAUSE_SECTION = 2000
_HEADING_PAUSE = {1: 1500, 2: 900}  # else 600

# Only reliably-paired delimiters. « » are balanced 1428/1428 in the book;
# ( ) too, with the d>0 guard absorbing list markers like "1)". The rare
# German nested quotes „ “ ” (14 total, inconsistent) are left depth-neutral —
# modelling them wrong splits inside quotes more often than ignoring them.
_OPEN = "«(["
_CLOSE = "»)]"

# Russian prepositions, conjunctions and the particle «не» — a chunk must not
# end on any of these (leaves the listener hanging mid-thought).
_STOPWORDS = {
    # prepositions
    "в", "во", "на", "за", "к", "ко", "с", "со", "о", "об", "обо", "от", "ото",
    "до", "из", "изо", "у", "по", "под", "подо", "над", "надо", "при", "про",
    "для", "без", "безо", "через", "между", "перед", "передо", "около", "возле",
    "вокруг", "среди", "ради", "сквозь", "кроме", "вместо", "близ", "вдоль",
    "из-за", "из-под",
    # conjunctions
    "и", "а", "но", "да", "или", "либо", "что", "чтобы", "чтоб", "как", "когда",
    "если", "хотя", "зато", "тоже", "также", "то", "чем", "будто", "словно",
    "точно", "дабы", "ибо", "пока", "коли", "раз", "ежели", "притом", "причём",
    # particles
    "не", "ни", "бы", "б", "же", "ль", "ли",
}


# ── depth / quote-aware helpers ──────────────────────────────────────────────

def _depths(s: str) -> list[int]:
    """depth[i] = bracket/quote nesting depth of the gap BEFORE character i."""
    out = []
    depth = 0
    for ch in s:
        out.append(depth)
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE and depth > 0:
            depth -= 1
    return out


def _split_sentences(text: str) -> list[str]:
    """Split into sentences at .!?… that sit at depth 0, keeping delimiters.
    Never splits inside quotes or brackets."""
    depths = _depths(text)
    sents: list[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ".!?…" and depths[i] == 0:
            j = i + 1
            # absorb trailing punctuation and closing quotes/brackets
            while j < n and (text[j] in ".!?…" or text[j] in _CLOSE):
                j += 1
            # sentence boundary only if followed by whitespace (or end)
            if j >= n or text[j].isspace():
                sents.append(text[start:j].strip())
                # skip whitespace
                while j < n and text[j].isspace():
                    j += 1
                start = j
                i = j
                continue
        i += 1
    if start < n:
        tail = text[start:].strip()
        if tail:
            sents.append(tail)
    return [s for s in sents if s]


# ── enumeration-comma split ──────────────────────────────────────────────────
# Depth-0 commas between short (≤20 char) non-subordinate segments are treated
# as enumeration boundaries at synthesis time. Lives here (not synth.py) so
# chunk_hash can reference it without a circular import.

_SUBORD_STARTS = frozenset({
    "который", "которая", "которое", "которые", "которого", "которому",
    "которым", "которых", "которую", "которой",
    "когда", "если", "хотя", "пока", "потому", "поскольку", "чтобы",
    "откуда", "зачем", "почему", "несмотря", "кто", "куда", "где", "что",
})
_SUBORD_ANYWHERE = frozenset({
    "который", "которая", "которое", "которые", "которого", "которому",
    "которым", "которых", "которую", "которой", "где",
})
_ENUM_MAX_ITEM = 20
_AGE_WORDS = frozenset({"лет", "год", "года"})


def _ecw(w: str) -> str:
    return w.strip(".,;:—–!?…»«()[]\"'").lower()


def _enum_has_subord(seg: str) -> bool:
    words = seg.split()
    if not words:
        return False
    if _ecw(words[0]) in _SUBORD_STARTS:
        return True
    return bool({_ecw(w) for w in words} & _SUBORD_ANYWHERE)


def enum_splits(sentence: str) -> list[str]:
    """Split sentence at enumeration commas; returns [sentence] if none apply.

    An enum comma sits at depth 0 between two segments each ≤ 20 chars with
    no subordinating markers. Em-dashes reset the left-segment window.
    Byline guard: if any resulting part ends in an age word, returns [sentence].
    """
    depths = _depths(sentence)
    n = len(sentence)
    seg_start = 0
    splits: list[int] = []
    i = 0
    while i < n:
        if sentence[i] in "—–" and depths[i] == 0:
            seg_start = i + 1
            while seg_start < n and sentence[seg_start] == " ":
                seg_start += 1
        elif sentence[i] == "," and depths[i] == 0:
            left = sentence[seg_start:i].strip()
            j = i + 1
            while j < n and sentence[j] == " ":
                j += 1
            k = j
            while k < n and (depths[k] != 0 or sentence[k] not in ",—–.!?…"):
                k += 1
            right = sentence[j:k].strip()
            if (len(left) <= _ENUM_MAX_ITEM and len(right) <= _ENUM_MAX_ITEM
                    and not _enum_has_subord(left) and not _enum_has_subord(right)
                    and left and right):
                splits.append(i)
            seg_start = i + 1
            while seg_start < n and sentence[seg_start] == " ":
                seg_start += 1
        i += 1
    if not splits:
        return [sentence]
    parts: list[str] = []
    prev = 0
    for pos in splits:
        p = sentence[prev:pos].strip()
        if p:
            parts.append(p)
        prev = pos + 1
        while prev < n and sentence[prev] == " ":
            prev += 1
    tail = sentence[prev:].strip()
    if tail:
        parts.append(tail)
    parts = [p for p in parts if p]
    def _last_word(p: str) -> str:
        w = p.lower().split()
        return w[-1].strip(".,!?") if w else ""
    if any(_last_word(p) in _AGE_WORDS for p in parts):
        return [sentence]
    return parts


def _is_stopword(word: str) -> bool:
    w = word.strip(".,;:—–!?…»«()[]\"'").lower()
    return w in _STOPWORDS


def _ends_on_stopword(chunk: str) -> bool:
    """True only for a bare mid-clause cut: the chunk ends on a letter and that
    last word is a stop-word. A chunk ending in punctuation (comma, colon,
    closing quote, sentence mark) is a legitimate boundary, not a dangling word."""
    c = chunk.rstrip()
    if not c or not c[-1].isalpha():
        return False
    words = c.split()
    return bool(words) and _is_stopword(words[-1])


def _safe_space_points(s: str) -> list[int]:
    """Indices of spaces at depth 0 (safe to cut after)."""
    depths = _depths(s)
    return [i for i in range(len(s)) if s[i] == " " and depths[i] == 0]


def _split_sentences_flat(text: str) -> list[str]:
    """Like _split_sentences but splits at .!?… at ANY depth.
    Used only as a fallback when the whole string is inside quotes."""
    sents: list[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ".!?…":
            j = i + 1
            while j < n and (text[j] in ".!?…" or text[j] in _CLOSE):
                j += 1
            if j >= n or text[j].isspace():
                sents.append(text[start:j].strip())
                while j < n and text[j].isspace():
                    j += 1
                start = j
                i = j
                continue
        i += 1
    if start < n:
        tail = text[start:].strip()
        if tail:
            sents.append(tail)
    return [s for s in sents if s]


def _split_long(s: str, lim: Limits = Limits()) -> list[str]:
    """Split a sentence longer than cap at depth-0 boundaries, preferring
    clause delimiters, never exceeding cap, never ending on a stopword."""
    TARGET, CAP = lim.target, lim.cap
    pts = _safe_space_points(s)
    if not pts:
        # No depth-0 spaces — entire string is inside quotes.
        # Quote rule yields to hard cap: split at sentence boundaries inside,
        # ignoring depth (the enclosing «…» makes all punctuation depth>=1).
        if len(s) <= CAP:
            return [s]
        sents = _split_sentences_flat(s)
        if len(sents) <= 1:
            return [s]
        pieces: list[str] = []
        cur = ""
        for sent in sents:
            if not cur:
                cur = sent
            elif len(cur) + 1 + len(sent) <= TARGET:
                cur = cur + " " + sent
            else:
                pieces.append(cur)
                cur = sent
        if cur:
            pieces.append(cur)
        return pieces

    def prefer(i: int) -> bool:
        left = s[:i].rstrip()
        return bool(left) and left[-1] in ",;:—–"

    pieces: list[str] = []
    start = 0
    while len(s) - start > CAP:
        window = [i for i in pts if start < i <= start + CAP]
        if not window:
            # no safe point within cap — extend to the first safe point past cap
            window = [i for i in pts if i > start]
            if not window:
                break
            cut = window[0]
        else:
            clause = [i for i in window if prefer(i)]
            candidates = clause or window
            # farthest that does not end on a stopword; else farthest
            cut = None
            for i in sorted(candidates, reverse=True):
                if not _ends_on_stopword(s[start:i]):
                    cut = i
                    break
            if cut is None:
                cut = candidates[-1]
        pieces.append(s[start:cut].strip())
        start = cut + 1
    if start < len(s):
        pieces.append(s[start:].strip())
    return [p for p in pieces if p]


def _merge_short(chunks: list[str], lim: Limits = Limits()) -> list[str]:
    MIN_LEN, CAP = lim.min_len, lim.cap
    out: list[str] = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if (len(c) < MIN_LEN and i + 1 < len(chunks)
                and len(c) + 1 + len(chunks[i + 1]) <= CAP):
            out.append(c + " " + chunks[i + 1])
            i += 2
        else:
            out.append(c)
            i += 1
    # short trailing chunk: merge backward if it fits
    if len(out) >= 2 and len(out[-1]) < MIN_LEN and len(out[-2]) + 1 + len(out[-1]) <= CAP:
        last = out.pop()
        out[-1] = out[-1] + " " + last
    return out


def _fix_stopword_endings(chunks: list[str], lim: Limits = Limits()) -> list[str]:
    CAP = lim.cap
    for i in range(len(chunks) - 1):
        words = chunks[i].split()
        while len(words) > 1 and _is_stopword(words[-1]):
            moved = words.pop()
            if len(chunks[i + 1]) + 1 + len(moved) > CAP:
                break
            chunks[i + 1] = moved + " " + chunks[i + 1]
            chunks[i] = " ".join(words)
    return [c for c in chunks if c]


def chunk_prose(text: str, lim: Limits = Limits()) -> list[str]:
    """Split a paragraph's text into chunks obeying length + boundary rules."""
    TARGET, CAP = lim.target, lim.cap
    units: list[str] = []
    for s in _split_sentences(text):
        units.extend(_split_long(s, lim) if len(s) > CAP else [s])

    chunks: list[str] = []
    cur = ""
    for u in units:
        if not cur:
            cur = u
        elif len(cur) + 1 + len(u) <= TARGET:
            cur = cur + " " + u
        else:
            chunks.append(cur)
            cur = u
    if cur:
        chunks.append(cur)

    chunks = _merge_short(chunks, lim)
    chunks = _fix_stopword_endings(chunks, lim)
    return chunks


# ── structure loading ────────────────────────────────────────────────────────

def load_units(nn: str, slug: str) -> list[dict]:
    """Map blocks JSON (structure) onto .norm.txt lines (text)."""
    jf = paths.TEXT / "blocks" / f"{nn}_{slug}.blocks.json"
    normf = paths.TEXT / f"{nn}_{slug}.norm.txt"
    blocks = json.loads(jf.read_text(encoding="utf-8"))["blocks"]
    norm_lines = normf.read_text(encoding="utf-8").splitlines()

    units: list[dict] = []
    li = 0
    for b in blocks:
        t = b["type"]
        if t == "figure_caption":
            continue
        if t == "stack":
            parts = [p for p in b["text"].split("\n") if p.strip()]
            lines = norm_lines[li:li + len(parts)]
            li += len(parts)
            for j, line in enumerate(lines):
                units.append({"type": "stack", "text": line,
                              "last_in_stack": j == len(lines) - 1})
        else:
            line = norm_lines[li]
            li += 1
            u = {"type": t, "text": line}
            if t == "heading":
                u["level"] = b.get("heading_level", 1)
            units.append(u)
    if li != len(norm_lines):
        raise SystemExit(
            f"block/line mismatch in {nn}_{slug}: consumed {li} of {len(norm_lines)} lines"
        )
    return units


_HEADING_NUMBER = re.compile(r"^(Глава\s+[^.:]+?\.)\s+(\S.*)$")


def split_heading(text: str) -> tuple[str | None, str | None, str]:
    """Split a heading into (number, label, title) at "Глава N." and the first
    depth-0 ": ". Missing parts are None; title is always the remainder.
      "Глава тринадцатая. Базовый навык: «Цитата»" → ("Глава тринадцатая.",
                                                      "Базовый навык:", "«Цитата»")
      "Упражнение: найди" → (None, "Упражнение:", "найди")
    Read as one chunk the model ran the parts together with no breath; split,
    each part gets its own pause (validated by ear on 1.7B, ch13 test)."""
    number = None
    m = _HEADING_NUMBER.match(text)
    rest = text
    if m:
        number, rest = m.group(1), m.group(2)
    label = None
    depth = 0
    for i, ch in enumerate(rest):
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE and depth > 0:
            depth -= 1
        elif ch == ":" and depth == 0 and rest[i + 1:i + 2] == " ":
            head, tail = rest[:i + 1].strip(), rest[i + 2:].strip()
            if head != ":" and tail:
                label, rest = head, tail
            break
    return number, label, rest


def _heading_chunks(text: str, pause: int, pauses: dict) -> list[dict]:
    """One heading → 1..3 chunks. Splitting is on only when config sets
    pauses_ms.heading_number / heading_colon; absent keys keep the heading whole
    (pre-1.7B behaviour, unchanged hashes)."""
    p_num = pauses.get("heading_number")
    p_col = pauses.get("heading_colon")
    if not p_num and not p_col:
        return [{"text": text, "pause_after_ms": pause}]
    number, label, title = split_heading(text)
    # A part whose pause is not configured is glued onto the next part.
    parts: list[tuple[str, int | None]] = []
    if number:
        parts.append((number, int(p_num) if p_num else None))
    if label:
        parts.append((label, int(p_col) if p_col else None))
    parts.append((title, pause))
    out: list[dict] = []
    carry = ""
    for txt, p in parts:
        txt = f"{carry} {txt}" if carry else txt
        if p is None:
            carry = txt
            continue
        carry = ""
        out.append({"text": txt, "pause_after_ms": p})
    return out


_STEP_LABEL = re.compile(r"^(Шаг\s+[А-Яа-яЁё0-9]+\.)\s+(\S.*)$")


def split_step_label(text: str) -> tuple[str | None, str]:
    """ "Шаг третий. «Чувствую». Включись." → ("Шаг третий.", "«Чувствую». Включись.").
    Read in one breath the label ran into the step text; split, it gets its
    own pause (ch13 listening: "Шаг 3. Слово. ... Пауза.")."""
    m = _STEP_LABEL.match(text)
    return (m.group(1), m.group(2)) if m else (None, text)


_CLOSERS = "»”\"')]"


def end_mark(text: str) -> str:
    """The terminal punctuation of a chunk, looking past closing quotes and
    brackets: "?" "!" "…" ":" ";" "." or "" (none). "..." counts as "…"."""
    t = text.rstrip().rstrip(_CLOSERS).rstrip()
    if t.endswith("...") or t.endswith("…"):
        return "…"
    return t[-1] if t and t[-1] in "?!:;." else ""


def sentence_pause(text: str, default: int, by_end: dict) -> int:
    """Pause after a chunk that ends mid-paragraph: ``pauses_ms.by_end`` by its
    final mark ("?": 500, "…": 650 …), else the plain sentence pause."""
    mark = end_mark(text)
    return int(by_end.get(mark, default)) if mark else default


def section_config(config: dict, section: str | None) -> dict:
    """``config`` with ``pauses_ms.sections.<section>`` merged over ``pauses_ms``
    (e.g. slower practices). Pauses are not in the chunk hash: changing them
    needs chunk + assemble, never a re-render."""
    if not section:
        return config
    pauses = dict(config.get("pauses_ms") or {})
    over = (pauses.get("sections") or {}).get(section)
    if not over:
        return config
    pauses.update(over)
    return {**config, "pauses_ms": pauses}


def build_chunks(units: list[dict], config: dict | None = None) -> list[dict]:
    """Return ordered [{text, pause_after_ms}]. ``config`` supplies chunk length
    limits (``chunking``) and heading split pauses (``pauses_ms``); None = the
    module defaults, headings whole."""
    lim = limits(config)
    pauses = (config or {}).get("pauses_ms") or {}
    level_pause = {int(k): int(v) for k, v in (pauses.get("heading_level") or {}).items()}
    p_step = pauses.get("step_label")
    # config.pauses_ms is the source of truth; module constants are defaults
    p_sent = int(pauses.get("sentence", PAUSE_SENTENCE))
    p_par = int(pauses.get("paragraph", PAUSE_PARAGRAPH))
    p_stack = int(pauses.get("stack", PAUSE_STACK))
    p_sec = int(pauses.get("chapter", PAUSE_SECTION))
    by_end = {str(k): int(v) for k, v in (pauses.get("by_end") or {}).items()}
    chunks: list[dict] = []
    role_carrier = (((config or {}).get("render") or {}).get("leadin") or {}).get(
        "chapter_title_carrier", False)
    if type(role_carrier) is not bool:
        raise ValueError("chapter_title_carrier must be boolean")
    for u in units:
        t = u["type"]
        if t == "heading":
            pause = level_pause.get(u["level"], _HEADING_PAUSE.get(u["level"], 600))
            parts = [{**h, "kind": "heading"} for h in _heading_chunks(u["text"], pause, pauses)]
            if role_carrier:
                number, _label, _title = split_heading(u["text"])
                # Same source heading only: require an actual separate chapter-number chunk.
                if number and len(parts) > 1 and parts[0]["text"] == number:
                    parts[-1]["chapter_title_carrier"] = number
            chunks.extend(parts)
        elif t == "stack":
            pause = p_stack if not u["last_in_stack"] else p_par
            chunks.append({"text": u["text"], "pause_after_ms": pause, "kind": "stack"})
        else:  # paragraph, flow, chain, prose_with_arrow
            text = u["text"]
            if p_step:
                label, text = split_step_label(text)
                if label:
                    chunks.append({"text": label, "pause_after_ms": int(p_step), "kind": "step"})
            pieces = chunk_prose(text, lim)
            for i, p in enumerate(pieces):
                pause = (sentence_pause(p, p_sent, by_end) if i < len(pieces) - 1
                         else p_par)
                chunks.append({"text": p, "pause_after_ms": pause, "kind": "text"})
    if chunks:
        chunks[-1]["pause_after_ms"] = p_sec
    return chunks


# ── hashing ──────────────────────────────────────────────────────────────────

def latents_hash(config: dict) -> str:
    lat = voicecfg.latents_path(config)  # per model variant
    if lat.exists():
        return hashlib.sha1(lat.read_bytes()).hexdigest()
    return "no-latents"


_TERMINAL_RAW = frozenset(".!?…:;»\"")  # raw text always has quotes


def chunk_open_end(text: str, next_text: str | None = None) -> bool:
    """True when the chunk ends mid-sentence AND the following chunk continues it.

    Criteria (both must hold):
    1. No terminal punctuation on the last non-whitespace character.
    2. next_text is not None and its first non-whitespace character is lowercase
       (sentence continues — not a new sentence, heading or paragraph start).

    The last chunk of a paragraph always returns False (next_text=None).
    next_text should be None when the next chunk is a heading or step label."""
    s = text.rstrip()
    if not s or s[-1] in _TERMINAL_RAW:
        return False
    if next_text is None:
        return False
    ns = next_text.lstrip()
    return bool(ns) and ns[0].islower()


def chunk_hash(text: str, model: str, seed: int, temperature: float,
               language: str, lat_hash: str, synth_text: str | None = None,
               leadin: str | None = None, enum_pause_ms: int = 0,
               chapter_title_input: str | None = None,
               carrier_recovery_input: str | None = None) -> str:
    payload = f"{text}\x00{model}\x00{seed}\x00{temperature}\x00{language}\x00{lat_hash}"
    # The pronounce respelling only enters the hash when it actually changes the
    # text, so chunks the dictionary does not touch keep their pre-dictionary
    # hash (and cached audio). A firing entry re-queues exactly its chunks.
    if synth_text is not None and synth_text != text:
        payload += f"\x00pron={synth_text}"
    # The context lead-in likewise enters the hash only for chunks short enough to
    # fire on it (see leadin.fires), so padding re-queues exactly the short chunks
    # and every other chunk keeps its cached audio.
    if leadin:
        payload += f"\x00leadin={leadin}"
    # Enum-pause enters the hash only for chunks that actually have enum splits,
    # so changing enum_pause_ms re-queues exactly the affected chunks.
    if enum_pause_ms:
        payload += f"\x00enum_pause={enum_pause_ms}"
    # Opt-in chapter-title conditioning binds the entire padded model input,
    # including carrier-only/cross-boundary dictionary edits. Legacy hashes stay intact.
    if chapter_title_input is not None:
        payload += "\\x00chapter_title_input=" + chapter_title_input
    if carrier_recovery_input is not None:
        payload += "\\x00carrier_recovery_input=" + carrier_recovery_input
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_manifest(units: list[dict], config: dict, *,
                   pronounce_table: dict[str, str] | None = None) -> list[dict]:
    model = voicecfg.model_id(config)  # 0.6B → bare name (old hashes kept)
    seed = config["model"]["seed"]
    temperature = config["model"]["temperature"]
    language = config["model"]["language"]
    lat = latents_hash(config)
    from audiobook import leadin
    from audiobook.pronounce import load_table, respell
    # Explicit table snapshots are for read-only candidate planning; default is unchanged.
    table = load_table() if pronounce_table is None else pronounce_table

    enum_pause_ms = config.get("pauses_ms", {}).get("enum_pause_ms", 0)

    recovery = ((config.get("render") or {}).get("leadin") or {}).get("recovery_by_hash", {})
    if not isinstance(recovery, dict) or any(
        not isinstance(k, str) or not re.fullmatch(r"[0-9a-f]{40}", k)
        or v not in ("none", "fixed") for k, v in recovery.items()
    ):
        raise ValueError("INVALID_CARRIER_RECOVERY")
    used_recovery: set[str] = set()
    chunks = list(build_chunks(units, config))
    manifest: list[dict] = []
    prev_prepared, prev_kind = None, None
    prev_open_end = False
    for i, c in enumerate(chunks):
        n = i + 1
        kind = c.get("kind", "text")
        # open_end: sentence continues mid-chunk AND next running-text chunk starts lowercase.
        # Headings/step labels are excluded (complete thoughts even without terminal mark).
        # next_text is None when next chunk is a heading/step/absent → forces False.
        if kind in ("text", "stack"):
            nc = chunks[i + 1] if i + 1 < len(chunks) else None
            next_text = (nc["text"]
                         if nc and nc.get("kind", "text") in ("text", "stack")
                         else None)
            is_open_end = chunk_open_end(c["text"], next_text)
        else:
            is_open_end = False
        # Same order as synth.prepare_synth_text: text_prep → lead-in → respell.
        # text_prep changes enter the hash through synth_text (pron=…).
        prepared = voicecfg.prepare_text(c["text"], config, is_open_end)
        synth_text = respell(prepared, table)
        # Context lead-in only inside running text: never for headings/step
        # labels, never borrowing from one. Default mode → fixed carrier (fires).
        phrase = leadin.phrase_for(prepared, config, prev_prepared,
                                   kind in ("text", "stack") and prev_kind in ("text", "stack"))
        chapter_title_input = None
        if "chapter_title_carrier" in c:
            if enum_pause_ms:
                raise ValueError("chapter_title_carrier requires enum_pause_ms=0")
            phrase = c["chapter_title_carrier"]
            chapter_title_input = json.dumps(
                [respell(leadin.pad(prepared, phrase), table), config["model"].get("sentinel", "")],
                ensure_ascii=False, separators=(",", ":"))
        prev_prepared, prev_kind = prepared, kind
        # Enum-pause enters hash only when this chunk actually has splits.
        c_enum_ms = enum_pause_ms if (enum_pause_ms and any(
            len(enum_splits(s)) > 1 for s in _split_sentences(c["text"])
        )) else 0
        base_hash = chunk_hash(c["text"], model, seed, temperature, language, lat,
                               synth_text, phrase, c_enum_ms, chapter_title_input)
        effective_hash = base_hash
        if base_hash in recovery:
            if (base_hash in used_recovery or not phrase or chapter_title_input is not None
                    or enum_pause_ms or kind not in ("text", "stack")):
                raise ValueError("INVALID_CARRIER_RECOVERY_TARGET")
            used_recovery.add(base_hash)
            if recovery[base_hash] == "none":
                phrase = None
            else:
                fixed = leadin.carrier(config)
                if not fixed or fixed[0] == phrase:
                    raise ValueError("INVALID_FIXED_RECOVERY_CARRIER")
                phrase = fixed[0]
            recovery_input = json.dumps(
                [respell(leadin.pad(prepared, phrase) if phrase else prepared, table),
                 config["model"].get("sentinel", "")], ensure_ascii=False, separators=(",", ":"))
            effective_hash = chunk_hash(c["text"], model, seed, temperature, language, lat,
                                        synth_text, phrase, c_enum_ms,
                                        carrier_recovery_input=recovery_input)
        manifest.append({
            "id": f"{n:04d}",
            "n": n,
            "text": c["text"],
            "hash": effective_hash,
            "seed": seed,
            "pause_after_ms": c["pause_after_ms"],
            "leadin": phrase,       # carrier/context read before the text and cut off (in hash)
            "open_end": is_open_end,   # sentence continues into next chunk (not in hash)
            "cont": prev_open_end,     # chunk starts mid-sentence (not in hash)
            "status": "pending",
            "locked": False,
            "seed_override": None,  # set by `accept`; never enters the hash
            "duration_ms": None,
        })
        prev_open_end = is_open_end
    return manifest


# ── alignment ────────────────────────────────────────────────────────────────

# Per-chunk results that belong to the audio, not to the text: carried over
# with the wav when a re-chunk keeps the chunk (same hash).
_CARRY = ("status", "locked", "seed_override", "duration_ms", "seed", "cer",
          "transcript", "flag_words", "ms_per_char", "suspect",
          "min_p", "mean_p", "takes", "take_base", "peak", "reused_from",
          "seed_provenance", "last_reported_seed", "approved_wav_sha256")


def align(old: list[dict], new: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Match new chunks to old by hash. Returns (aligned_new, queued_ids, orphan_ids).

    Each old row is matched at most once: the book repeats identical chunks
    ("Шаг один." ×6), and a dict by hash sent every copy to the same old wav —
    renaming over an accepted (locked) take. Same id + same hash is matched
    first, then the remaining copies in order. aligned_new carries status,
    lock, seed and QC results; ``_from_id`` drives the wav rename. Unmatched
    new → queued; old rows left unmatched → orphans (wav to _orphan/).
    """
    pools: dict[str, list[dict]] = {}
    for oc in old:
        pools.setdefault(oc["hash"], []).append(oc)
    used: set[int] = set()
    pick: dict[str, dict] = {}
    for nc in new:  # pass 1: same id, same hash
        same = next((oc for oc in pools.get(nc["hash"], [])
                     if oc["id"] == nc["id"] and id(oc) not in used), None)
        if same is not None:
            pick[nc["id"]] = same
            used.add(id(same))
    aligned: list[dict] = []
    queued: list[str] = []
    for nc in new:  # pass 2: remaining copies in order
        oc = pick.get(nc["id"])
        if oc is None:
            oc = next((c for c in pools.get(nc["hash"], []) if id(c) not in used), None)
            if oc is not None:
                used.add(id(oc))
        if oc is None:
            aligned.append(nc)
            queued.append(nc["id"])
            continue
        merged = dict(nc)
        for k in _CARRY:
            if k in oc:
                merged[k] = oc[k]
        merged["_from_id"] = oc["id"]  # for wav rename
        aligned.append(merged)
    orphans = [oc["id"] for oc in old if id(oc) not in used]
    return aligned, queued, orphans


def _apply_wav_moves(aligned: list[dict], orphans: list[str], chunks_dir: Path,
                     old: list[dict] | None = None) -> None:
    """Rename matched wavs to their new ids; move orphan wavs to _orphan/.
    Orphans are named <id>__<hash12>.wav so an earlier orphan with the same id
    is never overwritten (that would be deleting rendered audio)."""
    if not chunks_dir.exists():
        return
    hash_of = {c["id"]: c["hash"] for c in (old or [])}
    orphan_dir = chunks_dir / "_orphan"
    for oid in orphans:
        wav = chunks_dir / f"{oid}.wav"
        if wav.exists():
            orphan_dir.mkdir(exist_ok=True)
            dst = orphan_dir / f"{oid}__{hash_of.get(oid, 'nohash')[:12]}.wav"
            n = 1
            while dst.exists():
                dst = orphan_dir / f"{oid}__{hash_of.get(oid, 'nohash')[:12]}_{n}.wav"
                n += 1
            wav.replace(dst)
    # two-phase rename to avoid id collisions
    staged: list[tuple[Path, Path]] = []
    for c in aligned:
        old_id = c.pop("_from_id", None)
        if old_id and old_id != c["id"]:
            src = chunks_dir / f"{old_id}.wav"
            if src.exists():
                tmp = chunks_dir / f"__tmp_{c['id']}.wav"
                src.replace(tmp)
                staged.append((tmp, chunks_dir / f"{c['id']}.wav"))
    for tmp, dst in staged:
        tmp.replace(dst)  # replace: works on Windows when dst exists
    for c in aligned:
        c.pop("_from_id", None)


def _write_manifest(path: Path, manifest: list[dict]) -> None:
    """Atomic: temp file + rename, so an interrupt never leaves half a manifest."""
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps({k: v for k, v in row.items() if k != "_from_id"},
                               ensure_ascii=False) + "\n")
    tmp.replace(path)


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def run(config: dict, section: str | None = None) -> int:
    """Re-chunk every section, or only ``section`` (NN_slug). A single-section
    re-chunk touches only that section's manifest and wavs (orphans → _orphan/)."""
    import glob
    out_root = paths.OUT / "sections"
    out_root.mkdir(parents=True, exist_ok=True)

    total = 0
    per_section: list[tuple[str, int, str]] = []
    for jf in sorted(glob.glob(str(paths.TEXT / "blocks" / "*.blocks.json"))):
        d = json.loads(Path(jf).read_text(encoding="utf-8"))
        nn, slug = d["nn"], d["slug"]
        if section and f"{nn}_{slug}" != section:
            continue
        normf = paths.TEXT / f"{nn}_{slug}.norm.txt"
        if not normf.exists() or normf.stat().st_size < 50:
            continue  # empty/skipped section
        units = load_units(nn, slug)
        new_manifest = build_manifest(units, section_config(config, f"{nn}_{slug}"))

        sec_dir = out_root / f"{nn}_{slug}"
        sec_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = sec_dir / "manifest.jsonl"
        chunks_dir = sec_dir / "chunks"

        note = ""
        if manifest_path.exists():
            old = _read_manifest(manifest_path)
            aligned, queued, orphans = align(old, new_manifest)
            _apply_wav_moves(aligned, orphans, chunks_dir, old)
            _write_manifest(manifest_path, aligned)
            note = f"re-chunk: {len(queued)} queued, {len(orphans)} orphaned"
        else:
            _write_manifest(manifest_path, new_manifest)

        n = len(new_manifest)
        total += n
        per_section.append((f"{nn}_{slug}", n, note))

    if section and not per_section:
        raise SystemExit(f"chunk: секция не найдена или пуста: {section}")
    for name, n, note in per_section:
        extra = f"   [{note}]" if note else ""
        print(f"{name:<52} {n:>4} chunks{extra}")
    print("─" * 66)
    print(f"{'TOTAL':<52} {total:>4} chunks  ({len(per_section)} sections)")
    return 0
