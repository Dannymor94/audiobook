"""Stress risk inventory from text/*.norm.txt.

Produces:
  out/stress/risk.tsv      — aggregated risk list (top/homograph/name/dict)
  out/stress/omographs.tsv — per-occurrence detail for dictionary homographs

No synthesis models required. RUAccent accentizer used only if models/ present
(for context-resolved variant column in omographs.tsv); otherwise shows options.

Exit code 1 + message if models/dictionary/omographs.json.gz is missing.
Outputs are written atomically (temp → rename) so a previous run is never
left as an apparently-current result when this run fails.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from audiobook import paths

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


# ── loaders ───────────────────────────────────────────────────────────────────

def _omograph_dict() -> dict[str, list[str]]:
    """Load omograph dictionary.  Missing file is a fatal error (blocked)."""
    p = paths.MODELS / "dictionary" / "omographs.json.gz"
    if not p.exists():
        raise SystemExit(
            f"stress-inventory: словарь омографов не найден: {p}\n"
            "Скопируй models/dictionary/ из хранилища проекта.  Статус: blocked."
        )
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _load_verified(p: Path) -> set[str]:
    if not p.exists():
        p.write_text(
            "# Verified stress forms — excluded from risk.tsv.\n"
            "# One lowercase form per entry. After confirming by ear,\n"
            "# add the form here so it stops appearing in the report.\n"
            "#\n"
            "# verified:\n"
            "#   - стоит\n"
            "#   - руки\n"
            "verified: []\n",
            encoding="utf-8",
        )
        return set()
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return set(str(w).lower() for w in (data.get("verified") or []))


def _load_pronounce_forms(p: Path) -> set[str]:
    if not p.exists():
        return set()
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {k.lower() for k in data if isinstance(k, str) and _WORD.search(k)}


def _load_watch_forms(p: Path) -> set[str]:
    if not p.exists():
        return set()
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    result: set[str] = set()
    for key in ("homographs", "names", "watch"):
        for w in data.get(key) or []:
            result.add(str(w).lower().strip())
    return result


# ── chunk-number index ────────────────────────────────────────────────────────

def _build_chunk_index(section: str) -> dict[str, list[str]]:
    """word (lowercase) → [chunk_id, ...] in text order, from manifest.

    Returns empty dict when no manifest exists (graceful degradation;
    chunk_id column will show '?' for that section).
    """
    manifest_path = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest_path.exists():
        return {}
    try:
        from audiobook.chunker import _read_manifest
        rows = _read_manifest(manifest_path)
        idx: dict[str, list[str]] = {}
        for row in rows:
            text = row.get("text") or ""
            for word in _WORD.findall(text.lower()):
                idx.setdefault(word, []).append(row["id"])
        return idx
    except Exception:
        return {}


# ── text helpers ──────────────────────────────────────────────────────────────

def _split_sentences(para: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]


def _char_context(sent: str, char_pos: int, word_len: int) -> str:
    """Context window around char_pos, guaranteed ≤80 chars, always contains the word.

    Slices ±40 from the word's start, then truncates to 80.  For any realistic
    Russian word (len≪40), the word itself is well within the 80-char window.
    """
    start = max(0, char_pos - 40)
    return sent[start: start + 80]


# ── optional accentizer ───────────────────────────────────────────────────────

def _try_accentizer():
    """Return accentizer.process_all callable, or None if models absent."""
    try:
        from audiobook.accent import _get_accentizer
        return _get_accentizer().process_all
    except Exception:
        return None


# ── atomic write ─────────────────────────────────────────────────────────────

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── main ──────────────────────────────────────────────────────────────────────

def run(config: dict) -> int:
    top_n = int((config.get("stress") or {}).get("top_n", 300))

    omographs = _omograph_dict()          # raises SystemExit if missing
    verified = _load_verified(paths.TEXT / "stress_verified.yaml")
    pronounce_forms = _load_pronounce_forms(paths.TEXT / "pronounce.yaml")
    watch_forms = _load_watch_forms(paths.TEXT / "stress_watch.yaml")

    form_count: Counter[str] = Counter()
    # form → shortest sentence ≤80 chars, or ±40 context snippet if none
    form_example: dict[str, str] = {}     # best example so far
    form_example_len: dict[str, int] = {} # length of stored sentence (inf for snippet)
    name_forms: set[str] = set()
    occ_rows: list[dict] = []
    occ_sents: list[str] = []  # parallel to occ_rows, for RUAccent

    for norm_path in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm_path.stem.replace(".norm", "")
        chunk_index = _build_chunk_index(section)
        # per-section occurrence counter for each word form → chunk lookup
        local_occ: Counter[str] = Counter()

        for para in norm_path.read_text(encoding="utf-8").splitlines():
            para = para.strip()
            if not para:
                continue
            sents = _split_sentences(para)

            # Track word index across the whole paragraph for name detection
            para_word_i = 0

            for si, sent in enumerate(sents):
                for m in _WORD.finditer(sent):
                    word = m.group()
                    lower = word.lower()
                    char_pos = m.start()
                    para_word_i += 1

                    form_count[lower] += 1

                    # Example: prefer sentence ≤80 chars; fallback = ±40 snippet
                    stripped = sent.strip()
                    slen = len(stripped)
                    snippet = _char_context(sent, char_pos, len(word))
                    if lower not in form_example:
                        if slen <= 80:
                            form_example[lower] = stripped
                            form_example_len[lower] = slen
                        else:
                            form_example[lower] = snippet
                            form_example_len[lower] = 999  # sentinel: snippet stored
                    else:
                        prev_len = form_example_len[lower]
                        if slen <= 80 and slen < prev_len:
                            form_example[lower] = stripped
                            form_example_len[lower] = slen

                    # Name: capital letter, not at word-index-0 in paragraph
                    if word[0].isupper() and para_word_i > 1:
                        name_forms.add(lower)

                    # Omograph: form has >1 accentuation in dict
                    if lower in omographs and len(omographs[lower]) > 1:
                        occ_n = local_occ[lower]
                        local_occ[lower] += 1
                        ids = chunk_index.get(lower, [])
                        chunk_id = ids[occ_n] if occ_n < len(ids) else "?"
                        occ_rows.append({
                            "form": lower,
                            "section": section,
                            "chunk": chunk_id,
                            "context": _char_context(sent, char_pos, len(word)),
                            "options": " / ".join(omographs[lower]),
                            "ruaccent": "",
                        })
                        occ_sents.append(sent)

    # Optional: resolve omograph variant with RUAccent
    process = _try_accentizer()
    if process and occ_rows:
        for row, sent in zip(occ_rows, occ_sents):
            try:
                accented = process(sent)
                form = row["form"]
                # RUAccent marks stress with '+' before the stressed vowel
                pat = re.compile(
                    r"\b" + re.sub(r"([а-яёА-ЯЁ])", r"\+?\1", re.escape(form)) + r"\b",
                    re.IGNORECASE,
                )
                m = pat.search(accented)
                row["ruaccent"] = m.group(0) if m else ""
            except Exception:
                # RUAccent inference is optional; don't hide the row
                pass

    # ── build risk list ───────────────────────────────────────────────────────

    top_forms = {f for f, _ in form_count.most_common(top_n)}
    omograph_forms = {r["form"] for r in occ_rows}
    known_forms = set(form_count)

    all_risk = (
        top_forms
        | omograph_forms
        | (name_forms & known_forms)
        | (pronounce_forms & known_forms)
        | (watch_forms & known_forms)
    ) - verified

    _REASON_ORDER = {"top": 0, "homograph": 1, "name": 2, "dict": 3}
    top_ranked = [f for f, _ in form_count.most_common(top_n)]
    top_rank_map = {f: i for i, f in enumerate(top_ranked)}

    risk_rows = []
    for form in all_risk:
        reasons = []
        if form in top_rank_map:
            reasons.append("top")
        if form in omograph_forms:
            reasons.append("homograph")
        if form in name_forms:
            reasons.append("name")
        if form in pronounce_forms or form in watch_forms:
            reasons.append("dict")
        risk_rows.append({
            "form": form,
            "freq": form_count[form],
            "reason": "+".join(reasons) if reasons else "other",
            "example": form_example.get(form, ""),
        })

    # Fully deterministic: reason priority, then freq desc, then form alpha
    risk_rows.sort(key=lambda r: (
        min((_REASON_ORDER.get(x, 9) for x in r["reason"].split("+")), default=9),
        -r["freq"],
        r["form"],
    ))

    # ── write output (atomic) ─────────────────────────────────────────────────

    out_dir = paths.OUT / "stress"
    out_dir.mkdir(parents=True, exist_ok=True)

    risk_lines = ["форма\tчастота\tпричина\tпример\n"]
    for r in risk_rows:
        risk_lines.append(f"{r['form']}\t{r['freq']}\t{r['reason']}\t{r['example']}\n")
    _atomic_write(out_dir / "risk.tsv", "".join(risk_lines))

    if occ_rows:
        occ_lines = ["форма\tсекция\tчанк\tконтекст\tварианты\truaccent\n"]
        for r in occ_rows:
            occ_lines.append(
                f"{r['form']}\t{r['section']}\t{r['chunk']}\t"
                f"{r['context']}\t{r['options']}\t{r['ruaccent']}\n"
            )
        _atomic_write(out_dir / "omographs.tsv", "".join(occ_lines))

    # ── console summary ───────────────────────────────────────────────────────

    by_reason: Counter[str] = Counter()
    occ_by_reason: Counter[str] = Counter()
    for r in risk_rows:
        for reason in r["reason"].split("+"):
            if reason in _REASON_ORDER:
                by_reason[reason] += 1
                occ_by_reason[reason] += r["freq"]

    risk_path = out_dir / "risk.tsv"
    print(f"stress-inventory: {len(risk_rows)} форм в списке риска → {risk_path}")
    for reason in ("top", "homograph", "name", "dict"):
        label = {
            "top": f"top-{top_n}", "homograph": "омографы",
            "name": "имена", "dict": "словарь",
        }[reason]
        print(f"  {label:<12} {by_reason[reason]:4d} форм  {occ_by_reason[reason]:7d} вхождений")
    if verified:
        print(f"  исключено (verified): {len(verified)} форм")
    if occ_rows:
        print(f"  детали омографов → {out_dir / 'omographs.tsv'}")
    if process is None and occ_rows:
        print("  (RUAccent не загружен — колонка ruaccent пуста; "
              "запусти с models/ для заполнения)")
    return 0
