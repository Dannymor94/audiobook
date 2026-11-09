"""Stress risk inventory from text/*.norm.txt.

Produces:
  out/stress/risk.tsv      — aggregated risk list (top/homograph/name/dict)
  out/stress/omographs.tsv — per-occurrence detail for dictionary homographs

No synthesis models required. RUAccent accentizer used only if models/ present
(for context-resolved variant column in omographs.tsv); otherwise shows options.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from audiobook import paths

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
# Split on sentence-ending punctuation followed by whitespace
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


# ── loaders ───────────────────────────────────────────────────────────────────

def _omograph_dict() -> dict[str, list[str]]:
    p = paths.MODELS / "dictionary" / "omographs.json.gz"
    if not p.exists():
        return {}
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


# ── text helpers ──────────────────────────────────────────────────────────────

def _split_sentences(para: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]


def _context(sent: str, word: str) -> str:
    """±40 chars around first occurrence of word in sent."""
    pos = sent.lower().find(word)
    if pos < 0:
        return sent[:80]
    return sent[max(0, pos - 40): pos + len(word) + 40]


# ── optional accentizer ───────────────────────────────────────────────────────

def _try_accentizer():
    """Return accentizer.process_all callable or None if models absent."""
    try:
        from audiobook.accent import _get_accentizer
        acc = _get_accentizer()
        return acc.process_all
    except Exception:
        return None


# ── main ──────────────────────────────────────────────────────────────────────

def run(config: dict) -> int:
    top_n = int((config.get("stress") or {}).get("top_n", 300))

    omographs = _omograph_dict()
    verified = _load_verified(paths.TEXT / "stress_verified.yaml")
    pronounce_forms = _load_pronounce_forms(paths.TEXT / "pronounce.yaml")
    watch_forms = _load_watch_forms(paths.TEXT / "stress_watch.yaml")

    # Per-form counters
    form_count: Counter[str] = Counter()
    # form → shortest sentence ≤ 80 chars containing it
    form_shortest: dict[str, str] = {}
    # forms found capitalized at non-sentence-start position
    name_forms: set[str] = set()
    # omograph occurrences for detail tsv
    occ_rows: list[dict] = []
    # sentences containing omographs (for optional RUAccent resolve)
    occ_sents: list[str] = []

    for norm_path in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm_path.stem.replace(".norm", "")
        for para_no, para in enumerate(norm_path.read_text(encoding="utf-8").splitlines()):
            para = para.strip()
            if not para:
                continue
            sents = _split_sentences(para)
            for si, sent in enumerate(sents):
                words = _WORD.findall(sent)
                for wi, word in enumerate(words):
                    lower = word.lower()
                    form_count[lower] += 1

                    # Shortest example sentence
                    stripped = sent.strip()
                    if len(stripped) <= 80:
                        prev = form_shortest.get(lower)
                        if prev is None or len(stripped) < len(prev):
                            form_shortest[lower] = stripped

                    # Name: capital letter, not at sentence start (wi > 0)
                    if word[0].isupper() and wi > 0:
                        name_forms.add(lower)

                    # Omograph: form has >1 accentuation in dict
                    if lower in omographs and len(omographs[lower]) > 1:
                        occ_rows.append({
                            "form": lower,
                            "section": section,
                            "chunk": para_no,
                            "context": _context(sent, lower),
                            "options": " / ".join(omographs[lower]),
                            "ruaccent": "",  # filled below if models present
                        })
                        occ_sents.append(sent)

    # Optional: resolve omograph variant with RUAccent
    process = _try_accentizer()
    if process and occ_rows:
        for i, (row, sent) in enumerate(zip(occ_rows, occ_sents)):
            try:
                accented = process(sent)
                # find the accented form of the word inside the accented sentence
                # RUAccent marks stress with '+' before the stressed vowel
                # Extract the word with stress mark
                form = row["form"]
                # match form letters with optional + markers
                pattern = re.compile(
                    r"\b" + re.sub(r"([а-яёА-ЯЁ])", r"\+?\1", re.escape(form)) + r"\b",
                    re.IGNORECASE,
                )
                m = pattern.search(accented)
                row["ruaccent"] = m.group(0) if m else ""
            except Exception:
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
    risk_rows = []
    top_ranked = [f for f, _ in form_count.most_common(top_n)]
    top_rank_map = {f: i for i, f in enumerate(top_ranked)}

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
            "example": form_shortest.get(form, ""),
        })

    risk_rows.sort(key=lambda r: (
        min((_REASON_ORDER.get(x, 9) for x in r["reason"].split("+")), default=9),
        -r["freq"],
    ))

    # ── write output ──────────────────────────────────────────────────────────

    out_dir = paths.OUT / "stress"
    out_dir.mkdir(parents=True, exist_ok=True)

    risk_path = out_dir / "risk.tsv"
    with open(risk_path, "w", encoding="utf-8") as f:
        f.write("форма\tчастота\tпричина\tпример\n")
        for r in risk_rows:
            f.write(f"{r['form']}\t{r['freq']}\t{r['reason']}\t{r['example']}\n")

    if occ_rows:
        occ_path = out_dir / "omographs.tsv"
        with open(occ_path, "w", encoding="utf-8") as f:
            f.write("форма\tсекция\tчанк\tконтекст\tварианты\truaccent\n")
            for r in occ_rows:
                f.write(
                    f"{r['form']}\t{r['section']}\t{r['chunk']}\t"
                    f"{r['context']}\t{r['options']}\t{r['ruaccent']}\n"
                )

    # ── console summary ───────────────────────────────────────────────────────

    by_reason: Counter[str] = Counter()
    occ_by_reason: Counter[str] = Counter()
    for r in risk_rows:
        for reason in r["reason"].split("+"):
            if reason in _REASON_ORDER:
                by_reason[reason] += 1
                occ_by_reason[reason] += r["freq"]

    print(f"stress-inventory: {len(risk_rows)} форм в списке риска → {risk_path}")
    for reason in ("top", "homograph", "name", "dict"):
        label = {"top": f"top-{top_n}", "homograph": "омографы", "name": "имена", "dict": "словарь"}[reason]
        print(f"  {label:<12} {by_reason[reason]:4d} форм  {occ_by_reason[reason]:7d} вхождений")
    if verified:
        print(f"  исключено (verified): {len(verified)} форм")
    if occ_rows:
        print(f"  детали омографов → {out_dir / 'omographs.tsv'}")
    if process is None and occ_rows:
        print("  (RUAccent не загружен — колонка ruaccent пуста; запусти с models/ для заполнения)")
    return 0
