"""Stress risk inventory from text/*.norm.txt.

Produces:
  out/stress/risk.tsv      — aggregated risk list (top/homograph/name/dict)
  out/stress/omographs.tsv — per-occurrence detail for dictionary homographs

No synthesis models required. RUAccent used only if models/ present.
Outputs are written atomically (temp → rename); a failed run never
overwrites a previous result with partial data.

Fatal conditions (SystemExit, non-zero):
  • models/dictionary/omographs.json.gz absent or unreadable
  • omographs.json.gz has wrong structure (not a {str: [str, ...]} dict)
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

from audiobook import paths

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


# ── loaders ───────────────────────────────────────────────────────────────────

def _omograph_dict() -> dict[str, list[str]]:
    """Load omograph dictionary.  Missing or corrupt file is a fatal error."""
    p = paths.MODELS / "dictionary" / "omographs.json.gz"
    if not p.exists():
        raise SystemExit(
            f"stress-inventory: словарь омографов не найден: {p}\n"
            "Скопируй models/dictionary/ из хранилища проекта.  Статус: blocked."
        )
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise SystemExit(
            f"stress-inventory: словарь омографов повреждён: {p}\n"
            f"  {exc}\nСтатус: blocked."
        ) from None
    if not isinstance(data, dict):
        raise SystemExit(
            f"stress-inventory: неверная структура словаря "
            f"(ожидался dict, получен {type(data).__name__}): {p}\n"
            "Статус: blocked."
        )
    return data


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


# ── chunk index ───────────────────────────────────────────────────────────────

def _build_chunk_index(section: str) -> dict[str, list[tuple[str, str]]]:
    """word (lowercase) → [(chunk_id, chunk_text), ...], one entry per chunk.

    Returns empty dict when no manifest exists (graceful degradation;
    chunk_id column will show '?' for that section).
    """
    manifest_path = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest_path.exists():
        return {}
    try:
        from audiobook.chunker import _read_manifest
        rows = _read_manifest(manifest_path)
        idx: dict[str, list[tuple[str, str]]] = {}
        for row in rows:
            chunk_id = row.get("id", "?")
            text = row.get("text") or ""
            # One entry per (word, chunk): multiple occurrences of a word
            # inside the same chunk collapse to one entry.
            for word in set(_WORD.findall(text.lower())):
                idx.setdefault(word, []).append((chunk_id, text))
        return idx
    except Exception:
        return {}


def _find_chunk_id(form: str, sent: str, char_pos: int,
                   candidates: list[tuple[str, str]]) -> str:
    """Match one occurrence to a manifest chunk by text fingerprint.

    Uses ±2 adjacent words as a fingerprint.  Returns chunk_id only when
    exactly one candidate matches; otherwise '?' (ambiguous or no match).
    This is safer than occurrence-order alignment, which breaks when the
    manifest and norm.txt diverge.
    """
    if not candidates:
        return "?"
    if len(candidates) == 1:
        return candidates[0][0]

    # Gather adjacent words for a 5-word fingerprint centred on the target
    all_ms = list(_WORD.finditer(sent))
    target_wi = next((i for i, m in enumerate(all_ms) if m.start() == char_pos), None)
    if target_wi is None:
        return "?"

    window = all_ms[max(0, target_wi - 2): target_wi + 3]
    fp_words = [m.group().lower() for m in window]

    matched = [cid for cid, ctext in candidates
               if all(w in ctext.lower() for w in fp_words)]
    # dict.fromkeys preserves order and removes duplicates (a chunk can appear
    # only once in candidates, but be defensive anyway)
    matched = list(dict.fromkeys(matched))
    return matched[0] if len(matched) == 1 else "?"


# ── text helpers ──────────────────────────────────────────────────────────────

def _split_sentences(para: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]


def _char_context(sent: str, char_pos: int, word_len: int) -> str:
    """Context window, guaranteed ≤80 chars, always contains the full form.

    If word_len > 80 (impossible for Russian), returns start of the form
    with an ellipsis and reports the limitation rather than silently truncating.
    """
    if word_len > 80:
        # Can't fit the form in 80 chars; return what we can with an indicator.
        print(
            f"  ПРЕДУПРЕЖДЕНИЕ: форма длиннее 80 символов ({word_len}) — "
            "контекст обрезан",
            file=sys.stderr,
        )
        return sent[char_pos: char_pos + 79] + "…"

    # Ideal window: 40 chars before the word's start
    start = max(0, char_pos - 40)
    # Guarantee the form END is within [start : start+80]
    form_end = char_pos + word_len
    if form_end > start + 80:
        start = max(0, form_end - 80)
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

    omographs = _omograph_dict()      # SystemExit if missing / corrupt / wrong type
    verified = _load_verified(paths.TEXT / "stress_verified.yaml")
    pronounce_forms = _load_pronounce_forms(paths.TEXT / "pronounce.yaml")
    watch_forms = _load_watch_forms(paths.TEXT / "stress_watch.yaml")

    form_count: Counter[str] = Counter()
    form_example: dict[str, str] = {}       # form → best example text
    form_example_len: dict[str, int] = {}   # len of stored sentence; 999 = snippet
    name_forms: set[str] = set()
    occ_rows: list[dict] = []
    occ_sents: list[str] = []  # parallel to occ_rows, sentence for RUAccent

    for norm_path in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm_path.stem.replace(".norm", "")
        chunk_index = _build_chunk_index(section)

        for para in norm_path.read_text(encoding="utf-8").splitlines():
            para = para.strip()
            if not para:
                continue
            sents = _split_sentences(para)

            for sent in sents:
                # Reset per-sentence occurrence counter for chunk and RUAccent lookup
                sent_form_occ: Counter[str] = Counter()

                for wi, m in enumerate(_WORD.finditer(sent)):
                    word = m.group()
                    lower = word.lower()
                    char_pos = m.start()

                    form_count[lower] += 1

                    # Example: prefer the shortest sentence ≤80 chars;
                    # fallback = ±40 context snippet (always ≤80, always contains form)
                    stripped = sent.strip()
                    slen = len(stripped)
                    snippet = _char_context(sent, char_pos, len(word))
                    if lower not in form_example:
                        if slen <= 80:
                            form_example[lower] = stripped
                            form_example_len[lower] = slen
                        else:
                            form_example[lower] = snippet
                            form_example_len[lower] = 999
                    elif slen <= 80 and slen < form_example_len[lower]:
                        form_example[lower] = stripped
                        form_example_len[lower] = slen

                    # Name: capitalised at non-sentence-start.
                    # wi is per-sentence (resets for each sentence), so the
                    # first word of every sentence is correctly excluded.
                    if word[0].isupper() and wi > 0:
                        name_forms.add(lower)

                    # Omograph: form has >1 accentuation in dict
                    if lower in omographs and len(omographs[lower]) > 1:
                        occ_in_sent = sent_form_occ[lower]
                        sent_form_occ[lower] += 1
                        candidates = chunk_index.get(lower, [])
                        chunk_id = _find_chunk_id(
                            form=lower, sent=sent,
                            char_pos=char_pos, candidates=candidates,
                        )
                        occ_rows.append({
                            "form": lower,
                            "section": section,
                            "chunk": chunk_id,
                            "context": _char_context(sent, char_pos, len(word)),
                            "options": " / ".join(omographs[lower]),
                            "ruaccent": "",
                            "occ_in_sent": occ_in_sent,  # used for RUAccent below
                        })
                        occ_sents.append(sent)

    # Optional RUAccent: resolve per-occurrence stressed variant
    process = _try_accentizer()
    ruaccent_errors = 0
    if process and occ_rows:
        for row, sent in zip(occ_rows, occ_sents):
            try:
                accented = process(sent)
                form = row["form"]
                # RUAccent marks stress with '+' before the stressed vowel.
                pat = re.compile(
                    r"\b" + re.sub(r"([а-яёА-ЯЁ])", r"\+?\1", re.escape(form)) + r"\b",
                    re.IGNORECASE,
                )
                # Extract the Nth match for this specific occurrence (not always first)
                all_matches = list(pat.finditer(accented))
                target_occ = row["occ_in_sent"]
                row["ruaccent"] = (
                    all_matches[target_occ].group(0)
                    if target_occ < len(all_matches) else ""
                )
            except Exception as exc:
                ruaccent_errors += 1
                row["ruaccent"] = f"ERR:{exc}"

        if ruaccent_errors:
            print(
                f"  ПРЕДУПРЕЖДЕНИЕ: RUAccent: {ruaccent_errors}/{len(occ_rows)} "
                "ошибок обработки — колонка ruaccent частично заполнена",
                file=sys.stderr,
            )

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
        print(
            "  (RUAccent не загружен — колонка ruaccent пуста; "
            "запусти с models/ для заполнения)"
        )
    return 0
