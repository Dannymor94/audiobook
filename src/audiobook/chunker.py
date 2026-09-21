"""Chunker + manifest. Reads .norm.txt (text) and blocks JSON (structure),
emits out/sections/NN_<slug>/manifest.jsonl. Does NOT synthesize.

Rules: target 120-220 chars, hard cap 250, min 40 (merge forward).
Paragraph is always a boundary. Never split inside quotes/brackets.
Never end a chunk on a preposition, conjunction or "не".
Heading = own chunk (pause by level). Stack lines = own chunks, 500ms between.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from audiobook import paths

TARGET = 220
CAP = 250
MIN_LEN = 40

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


def _split_long(s: str) -> list[str]:
    """Split a sentence longer than CAP at depth-0 boundaries, preferring
    clause delimiters, never exceeding CAP, never ending on a stopword."""
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


def _merge_short(chunks: list[str]) -> list[str]:
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


def _fix_stopword_endings(chunks: list[str]) -> list[str]:
    for i in range(len(chunks) - 1):
        words = chunks[i].split()
        while len(words) > 1 and _is_stopword(words[-1]):
            moved = words.pop()
            if len(chunks[i + 1]) + 1 + len(moved) > CAP:
                break
            chunks[i + 1] = moved + " " + chunks[i + 1]
            chunks[i] = " ".join(words)
    return [c for c in chunks if c]


def chunk_prose(text: str) -> list[str]:
    """Split a paragraph's text into chunks obeying length + boundary rules."""
    units: list[str] = []
    for s in _split_sentences(text):
        units.extend(_split_long(s) if len(s) > CAP else [s])

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

    chunks = _merge_short(chunks)
    chunks = _fix_stopword_endings(chunks)
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


def build_chunks(units: list[dict]) -> list[dict]:
    """Return ordered [{text, pause_after_ms}]."""
    chunks: list[dict] = []
    for u in units:
        t = u["type"]
        if t == "heading":
            pause = _HEADING_PAUSE.get(u["level"], 600)
            chunks.append({"text": u["text"], "pause_after_ms": pause})
        elif t == "stack":
            pause = PAUSE_STACK if not u["last_in_stack"] else PAUSE_PARAGRAPH
            chunks.append({"text": u["text"], "pause_after_ms": pause})
        else:  # paragraph, flow, chain, prose_with_arrow
            pieces = chunk_prose(u["text"])
            for i, p in enumerate(pieces):
                pause = PAUSE_SENTENCE if i < len(pieces) - 1 else PAUSE_PARAGRAPH
                chunks.append({"text": p, "pause_after_ms": pause})
    if chunks:
        chunks[-1]["pause_after_ms"] = PAUSE_SECTION
    return chunks


# ── hashing ──────────────────────────────────────────────────────────────────

def latents_hash(config: dict) -> str:
    ref = paths.ROOT / config["reference"]["path"]
    lat = ref.with_suffix(".latents.pt")
    if lat.exists():
        return hashlib.sha1(lat.read_bytes()).hexdigest()
    return "no-latents"


def chunk_hash(text: str, model: str, seed: int, temperature: float,
               language: str, lat_hash: str, synth_text: str | None = None) -> str:
    payload = f"{text}\x00{model}\x00{seed}\x00{temperature}\x00{language}\x00{lat_hash}"
    # The pronounce respelling only enters the hash when it actually changes the
    # text, so chunks the dictionary does not touch keep their pre-dictionary
    # hash (and cached audio). A firing entry re-queues exactly its chunks.
    if synth_text is not None and synth_text != text:
        payload += f"\x00pron={synth_text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_manifest(units: list[dict], config: dict) -> list[dict]:
    model = config["model"]["name"]
    seed = config["model"]["seed"]
    temperature = config["model"]["temperature"]
    language = config["model"]["language"]
    lat = latents_hash(config)
    from audiobook.pronounce import load_table, respell
    table = load_table()

    manifest: list[dict] = []
    for n, c in enumerate(build_chunks(units), start=1):
        synth_text = respell(c["text"], table)
        manifest.append({
            "id": f"{n:04d}",
            "n": n,
            "text": c["text"],
            "hash": chunk_hash(c["text"], model, seed, temperature, language, lat, synth_text),
            "seed": seed,
            "pause_after_ms": c["pause_after_ms"],
            "status": "pending",
            "locked": False,
            "duration_ms": None,
        })
    return manifest


# ── alignment ────────────────────────────────────────────────────────────────

def align(old: list[dict], new: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Match new chunks to old by hash. Returns (aligned_new, queued_ids, orphan_ids).

    aligned_new = new manifest with status/locked/duration carried over where the
    hash matched (wav gets renamed old.id -> new.id). Unmatched new -> queued.
    Old chunks whose hash is gone -> orphans (wav moved to _orphan/).
    """
    old_by_hash = {c["hash"]: c for c in old}
    new_hashes = {c["hash"] for c in new}

    aligned: list[dict] = []
    queued: list[str] = []
    for nc in new:
        oc = old_by_hash.get(nc["hash"])
        if oc is not None:
            merged = dict(nc)
            merged["status"] = oc["status"]
            merged["locked"] = oc["locked"]
            merged["duration_ms"] = oc["duration_ms"]
            merged["_from_id"] = oc["id"]  # for wav rename
            aligned.append(merged)
        else:
            aligned.append(nc)
            queued.append(nc["id"])
    orphans = [oc["id"] for oc in old if oc["hash"] not in new_hashes]
    return aligned, queued, orphans


def _apply_wav_moves(aligned: list[dict], orphans: list[str], chunks_dir: Path) -> None:
    """Rename matched wavs to their new ids; move orphan wavs to _orphan/."""
    if not chunks_dir.exists():
        return
    orphan_dir = chunks_dir / "_orphan"
    for oid in orphans:
        wav = chunks_dir / f"{oid}.wav"
        if wav.exists():
            orphan_dir.mkdir(exist_ok=True)
            wav.rename(orphan_dir / wav.name)
    # two-phase rename to avoid id collisions
    staged: list[tuple[Path, Path]] = []
    for c in aligned:
        old_id = c.pop("_from_id", None)
        if old_id and old_id != c["id"]:
            src = chunks_dir / f"{old_id}.wav"
            if src.exists():
                tmp = chunks_dir / f"__tmp_{c['id']}.wav"
                src.rename(tmp)
                staged.append((tmp, chunks_dir / f"{c['id']}.wav"))
    for tmp, dst in staged:
        tmp.rename(dst)
    # drop leftover _from_id on non-renamed
    for c in aligned:
        c.pop("_from_id", None)


def _write_manifest(path: Path, manifest: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps({k: v for k, v in row.items() if k != "_from_id"},
                               ensure_ascii=False) + "\n")


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def run(config: dict) -> int:
    import glob
    out_root = paths.OUT / "sections"
    out_root.mkdir(parents=True, exist_ok=True)

    total = 0
    per_section: list[tuple[str, int, str]] = []
    for jf in sorted(glob.glob(str(paths.TEXT / "blocks" / "*.blocks.json"))):
        d = json.loads(Path(jf).read_text(encoding="utf-8"))
        nn, slug = d["nn"], d["slug"]
        normf = paths.TEXT / f"{nn}_{slug}.norm.txt"
        if not normf.exists() or normf.stat().st_size < 50:
            continue  # empty/skipped section
        units = load_units(nn, slug)
        new_manifest = build_manifest(units, config)

        sec_dir = out_root / f"{nn}_{slug}"
        sec_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = sec_dir / "manifest.jsonl"
        chunks_dir = sec_dir / "chunks"

        note = ""
        if manifest_path.exists():
            old = _read_manifest(manifest_path)
            aligned, queued, orphans = align(old, new_manifest)
            _apply_wav_moves(aligned, orphans, chunks_dir)
            _write_manifest(manifest_path, aligned)
            note = f"re-chunk: {len(queued)} queued, {len(orphans)} orphaned"
        else:
            _write_manifest(manifest_path, new_manifest)

        n = len(new_manifest)
        total += n
        per_section.append((f"{nn}_{slug}", n, note))

    for name, n, note in per_section:
        extra = f"   [{note}]" if note else ""
        print(f"{name:<52} {n:>4} chunks{extra}")
    print("─" * 66)
    print(f"{'TOTAL':<52} {total:>4} chunks  ({len(per_section)} sections)")
    return 0
