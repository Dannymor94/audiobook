"""Stress risk inventory from manifest.jsonl + text/*.norm.txt  — Iteration 3.

Outputs (out/stress/inventory/):
  risk.tsv      — aggregated risk list (top/homograph/name/dict)
  omographs.tsv — per-occurrence detail for dictionary homographs
  summary.json  — SHA-256 of both TSVs, input fingerprint, counters

Source of occurrences: manifest.jsonl chunk texts (not norm.txt directly).
chunk_id is resolved by bisect on character intervals, never by occurrence order.

Fatal conditions (SystemExit, non-zero):
  • models/dictionary/omographs.json.gz absent, corrupt, or wrong structure
  • Token mismatch between manifest and norm.txt for any section
  • Any exception from RUAccent inference on a sentence
  • Word form longer than 80 characters

Allowed non-fatal uncertainty (rc=0, logged in summary):
  • unresolved/no_stress — RUAccent returned no stress mark for the form
  • unresolved/tokenization_mismatch — SequenceMatcher could not align the token
"""
from __future__ import annotations

import bisect
import datetime
import difflib
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from audiobook import paths

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
# Allows '+' (stress mark) inside tokens for RUAccent output
_WORD_PLUS = re.compile(r"[а-яёА-ЯЁ+]+")

# Sentence end: punctuation followed by whitespace
_SENT_END = re.compile(r"(?<=[.!?…])\s+")
# Single-letter initial at end of text: А. Б. В. etc.
_INITIAL_DOT = re.compile(r"(?<![А-ЯЁа-яёA-Za-z0-9])[А-ЯЁ]\.$")


# ── loaders ───────────────────────────────────────────────────────────────────

def _omograph_dict() -> dict[str, list[str]]:
    """Load omograph dictionary.  Missing, corrupt, or wrong structure is fatal."""
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


# ── section data (manifest-based) ─────────────────────────────────────────────

def _cyrillic_tokens(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in _WORD.findall(text)]


def _build_section_data(section: str) -> tuple[str, list[int], list[str]]:
    """Concatenate manifest chunk texts into one string; build bisect intervals.

    Returns (full_text, starts, chunk_ids) where starts[i] is the character
    offset of chunk chunk_ids[i] inside full_text.  Chunks are separated by
    '\\n\\n' (two newlines), so words never land in separators.

    Also validates that _cyrillic_tokens(full_text) == _cyrillic_tokens(norm.txt).
    Raises SystemExit on token mismatch.
    """
    manifest_path = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(
            f"stress-inventory: манифест отсутствует: {manifest_path}\n"
            "Статус: blocked."
        )

    try:
        from audiobook.chunker import _read_manifest
        rows = _read_manifest(manifest_path)
    except Exception as exc:
        raise SystemExit(
            f"stress-inventory: не удалось прочитать манифест {manifest_path}: {exc}\n"
            "Статус: blocked."
        ) from None

    parts: list[str] = []
    starts: list[int] = []
    chunk_ids: list[str] = []
    pos = 0

    for row in rows:
        text = row.get("text") or ""
        cid = row.get("id", "?")
        starts.append(pos)
        chunk_ids.append(cid)
        parts.append(text)
        pos += len(text) + 2  # +2 for "\n\n"

    full_text = "\n\n".join(parts)

    # Mandatory token validation against norm.txt
    norm_path = paths.TEXT / f"{section}.norm.txt"
    if norm_path.exists():
        m_toks = _cyrillic_tokens(full_text)
        n_toks = _cyrillic_tokens(norm_path.read_text(encoding="utf-8"))
        if m_toks != n_toks:
            first_diff: tuple
            for i, (a, b) in enumerate(zip(m_toks, n_toks)):
                if a != b:
                    first_diff = (i, a, b)
                    break
            else:
                first_diff = ("length", len(m_toks), len(n_toks))
            raise SystemExit(
                f"stress-inventory: несовпадение токенов в секции '{section}':\n"
                f"  manifest={len(m_toks)}, norm.txt={len(n_toks)} токенов\n"
                f"  первое различие: pos={first_diff[0]}, "
                f"manifest={first_diff[1]!r}, norm.txt={first_diff[2]!r}\n"
                "Статус: blocked."
            )

    return full_text, starts, chunk_ids


def _chunk_id_at(starts: list[int], chunk_ids: list[str], pos: int) -> str:
    """Find chunk_id for character position pos via binary search on starts."""
    i = bisect.bisect_right(starts, pos) - 1
    return chunk_ids[i] if 0 <= i < len(chunk_ids) else "?"


# ── text helpers ──────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    Respects paragraph boundaries (\\n\\n).  Single-letter initials (А., В.)
    do not create sentence boundaries.  Used for BOTH name detection and
    RUAccent processing — same function, same boundaries.
    """
    result: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Collect sentence start positions
        splits = [0]
        for m in _SENT_END.finditer(para):
            prev = para[:m.start() + 1].rstrip()
            if _INITIAL_DOT.search(prev):
                continue  # skip: single-letter initial before punctuation
            splits.append(m.end())
        splits.append(len(para))
        for i in range(len(splits) - 1):
            s = para[splits[i]: splits[i + 1]].strip()
            if s:
                result.append(s)
    return result


def _char_context(full_text: str, char_pos: int, word_len: int) -> str:
    """Context window guaranteed ≤80 chars that fully contains the form.

    Raises SystemExit if word_len > 80 (fatal per spec).
    """
    if word_len > 80:
        raise SystemExit(
            f"stress-inventory: словоформа длиннее 80 символов ({word_len}) "
            f"начиная с позиции {char_pos}.  Статус: blocked."
        )
    start = max(0, char_pos - 40)
    form_end = char_pos + word_len
    if form_end > start + 80:
        start = max(0, form_end - 80)
    # Replace internal chunk separators (\n\n) with spaces so TSV stays single-line.
    return full_text[start: start + 80].replace("\n", " ")


# ── RUAccent resolution ───────────────────────────────────────────────────────

def _try_accentizer():
    """Return accentizer.process_all callable, or None if models absent."""
    try:
        from audiobook.accent import _get_accentizer
        return _get_accentizer().process_all
    except Exception:
        return None


def _ruaccent_resolve(form: str, occ_in_sent: int, sent: str,
                      accented: str) -> tuple[str, str]:
    """Match RUAccent output for one specific occurrence of form in sent.

    Uses per-token index matching, with difflib.SequenceMatcher fallback
    when tokenization diverges.

    Returns (stressed_form_or_empty, status) where status is:
      "resolved"                       — stress mark found
      "unresolved/no_stress"           — form found, no '+' present
      "unresolved/tokenization_mismatch"  — SequenceMatcher gap covers position
    """
    form_norm = form.lower().replace("ё", "е")

    input_toks = [m.group().lower().replace("ё", "е") for m in _WORD.finditer(sent)]
    acc_toks_plus = [m.group() for m in _WORD_PLUS.finditer(accented)]
    acc_toks_norm = [t.replace("+", "").lower().replace("ё", "е") for t in acc_toks_plus]

    # Find the occ_in_sent-th occurrence of form in input tokens
    form_positions = [i for i, t in enumerate(input_toks) if t == form_norm]
    if occ_in_sent >= len(form_positions):
        return "", "unresolved/no_stress"
    target_i = form_positions[occ_in_sent]

    def _extract(acc_pos: int) -> tuple[str, str]:
        if acc_pos >= len(acc_toks_plus):
            return "", "unresolved/no_stress"
        tok = acc_toks_plus[acc_pos]
        return (tok, "resolved") if "+" in tok else (tok, "unresolved/no_stress")

    if input_toks == acc_toks_norm:
        return _extract(target_i)

    # Tokenization diverged: use SequenceMatcher on normalised token lists
    sm = difflib.SequenceMatcher(None, input_toks, acc_toks_norm, autojunk=False)
    for i1, j1, n in sm.get_matching_blocks():
        if n and i1 <= target_i < i1 + n:
            return _extract(j1 + (target_i - i1))
    return "", "unresolved/tokenization_mismatch"


# ── atomic publish ────────────────────────────────────────────────────────────

def _prepare_tmp_dir(stress_dir: Path) -> Path:
    """Handle stale artifacts from interrupted previous runs; return fresh tmp dir."""
    tmp_dir = stress_dir / "inventory.tmp"
    old_dir = stress_dir / "inventory.old"
    inventory_dir = stress_dir / "inventory"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    if old_dir.exists():
        if not inventory_dir.exists():
            # Interrupted at rename step — restore last confirmed report
            old_dir.rename(inventory_dir)
        else:
            # Interrupted at delete step — clean up
            shutil.rmtree(old_dir)

    tmp_dir.mkdir(parents=True)
    return tmp_dir


def _atomic_publish_inventory(tmp_dir: Path, inventory_dir: Path) -> None:
    """Replace inventory/ with inventory.tmp/ atomically.

    Sequence: inventory/ → inventory.old/ → inventory.tmp/ → inventory/ → delete old/.
    """
    old_dir = inventory_dir.parent / "inventory.old"
    if inventory_dir.exists():
        inventory_dir.rename(old_dir)
    tmp_dir.rename(inventory_dir)
    if old_dir.exists():
        shutil.rmtree(old_dir)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text file atomically within the same directory."""
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


def _input_fingerprint(omograph_path: Path, pronounce_p: Path,
                        watch_p: Path, verified_p: Path,
                        section_manifest_paths: list[Path]) -> dict:
    """SHA-256 fingerprints of all inputs that determine the report content."""
    def _sha(p: Path) -> str:
        return _file_sha256(p) if p.exists() else "absent"

    return {
        "dict": {"path": str(omograph_path), "sha256": _sha(omograph_path)},
        "pronounce": {"sha256": _sha(pronounce_p)},
        "watch": {"sha256": _sha(watch_p)},
        "verified": {"sha256": _sha(verified_p)},
        "manifests": {
            "count": len(section_manifest_paths),
            "sha256_list": [_sha(p) for p in section_manifest_paths],
        },
    }


# ── main ──────────────────────────────────────────────────────────────────────

def run(config: dict) -> int:  # noqa: C901 (complex but linear)
    top_n = int((config.get("stress") or {}).get("top_n", 300))

    omographs = _omograph_dict()     # SystemExit if missing / corrupt / wrong type
    verified = _load_verified(paths.TEXT / "stress_verified.yaml")
    pronounce_forms = _load_pronounce_forms(paths.TEXT / "pronounce.yaml")
    watch_forms = _load_watch_forms(paths.TEXT / "stress_watch.yaml")

    stress_dir = paths.OUT / "stress"
    stress_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = _prepare_tmp_dir(stress_dir)

    # --- section scan ---------------------------------------------------------
    form_count: Counter[str] = Counter()
    form_example: dict[str, str] = {}
    form_example_len: dict[str, int] = {}

    # Name detection: two sets built per spec section 5
    cap_in_mid: set[str] = set()       # forms capitalised at non-sentence-start
    form_lowercase_seen: set[str] = set()  # forms seen in lowercase

    occ_rows: list[dict] = []
    occ_sents: list[str] = []

    # Collect manifest paths for fingerprint
    manifest_paths: list[Path] = []
    skipped_sections: list[str] = []
    sections_validated = 0

    for norm_path in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm_path.stem.replace(".norm", "")
        manifest_path = paths.OUT / "sections" / section / "manifest.jsonl"
        if not manifest_path.exists():
            skipped_sections.append(section)
            continue

        manifest_paths.append(manifest_path)
        full_text, starts, chunk_ids = _build_section_data(section)
        sections_validated += 1

        for sent in _split_sentences(full_text):
            sent_form_occ: Counter[str] = Counter()

            for wi, m in enumerate(_WORD.finditer(sent)):
                word = m.group()
                lower = word.lower()
                char_pos = m.start()
                word_len = len(word)

                # Fatal: word > 80 chars (should never happen in Russian)
                if word_len > 80:
                    _char_context(full_text, char_pos, word_len)  # raises

                form_count[lower] += 1

                # Track case for name detection
                if word[0].islower():
                    form_lowercase_seen.add(lower)
                elif wi > 0:
                    cap_in_mid.add(lower)

                # Example: shortest sentence ≤80 chars; fallback = snippet
                stripped = sent.strip()
                slen = len(stripped)
                if lower not in form_example:
                    if slen <= 80:
                        form_example[lower] = stripped
                        form_example_len[lower] = slen
                    else:
                        snippet = _char_context(full_text, char_pos, word_len)
                        form_example[lower] = snippet
                        form_example_len[lower] = 999
                elif slen <= 80 and slen < form_example_len[lower]:
                    form_example[lower] = stripped
                    form_example_len[lower] = slen

                # Omograph: >1 accentuation variant in dictionary
                if lower in omographs and len(omographs[lower]) > 1:
                    occ_in_sent = sent_form_occ[lower]
                    sent_form_occ[lower] += 1

                    # Adjust char_pos: sent is a substring of full_text via split;
                    # find the actual position in full_text for bisect
                    # (sent comes from _split_sentences which splits on substrings of full_text)
                    # We search for the word at m.start() within the sent; the sent was
                    # extracted from full_text, so we need its offset there.
                    # Strategy: find sent inside full_text to get absolute char_pos.
                    # NOTE: this is O(len(full_text)) per sent; acceptable for <10k sents/section.
                    abs_pos = full_text.find(sent)
                    if abs_pos < 0:
                        abs_pos = 0  # fallback: won't happen with correct split
                    global_pos = abs_pos + char_pos

                    chunk_id = _chunk_id_at(starts, chunk_ids, global_pos)
                    occ_rows.append({
                        "form": lower,
                        "section": section,
                        "chunk": chunk_id,
                        "context": _char_context(full_text, global_pos, word_len),
                        "options": " / ".join(omographs[lower]),
                        "ruaccent": "",
                        "ruaccent_status": "",
                        "occ_in_sent": occ_in_sent,
                    })
                    occ_sents.append(sent)

    if skipped_sections:
        print(
            f"  ДИАГНОСТИКА: пропущено {len(skipped_sections)} секций без манифеста: "
            f"{', '.join(skipped_sections)}",
            file=sys.stderr,
        )

    # Name candidates: spec section 5
    # Rule 1: capitalised at non-sentence-start
    # Rule 2: capitalised at sentence-start, never lowercase, appears mid-sentence
    #   → rule 2 adds forms from cap_in_mid that never appeared lowercase
    #   (the form set is the same as rule 1 since cap_in_mid already captured them)
    name_forms = cap_in_mid  # rule 1 covers rule 2's form set

    # --- RUAccent resolution --------------------------------------------------
    process = _try_accentizer()
    ruaccent_resolved = 0
    ruaccent_no_stress = 0
    ruaccent_mismatch = 0

    if process and occ_rows:
        for row, sent in zip(occ_rows, occ_sents):
            # Exception from process() is fatal (not silenced)
            try:
                accented = process(sent)
            except Exception as exc:
                raise SystemExit(
                    f"stress-inventory: RUAccent завершился с ошибкой:\n"
                    f"  {exc!r}\nСтатус: blocked."
                ) from exc

            stressed, status = _ruaccent_resolve(
                row["form"], row["occ_in_sent"], sent, accented,
            )
            row["ruaccent"] = stressed
            row["ruaccent_status"] = status

            if status == "resolved":
                ruaccent_resolved += 1
            elif status == "unresolved/no_stress":
                ruaccent_no_stress += 1
            else:
                ruaccent_mismatch += 1

    # --- build risk list ------------------------------------------------------
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

    # --- write to tmp/ --------------------------------------------------------
    RISK_HEADER = "форма\tчастота\tпричина\tпример"
    OCC_HEADER = "форма\tсекция\tчанк\tконтекст\tварианты\truaccent\truaccent_status"

    risk_lines = [RISK_HEADER + "\n"]
    for r in risk_rows:
        risk_lines.append(f"{r['form']}\t{r['freq']}\t{r['reason']}\t{r['example']}\n")
    _atomic_write_text(tmp_dir / "risk.tsv", "".join(risk_lines))

    occ_lines = [OCC_HEADER + "\n"]
    for r in occ_rows:
        occ_lines.append(
            f"{r['form']}\t{r['section']}\t{r['chunk']}\t"
            f"{r['context']}\t{r['options']}\t{r['ruaccent']}\t{r['ruaccent_status']}\n"
        )
    _atomic_write_text(tmp_dir / "omographs.tsv", "".join(occ_lines))

    # Validate before publishing
    for fname, expected_rows, expected_hdr in [
        ("risk.tsv", len(risk_rows), RISK_HEADER),
        ("omographs.tsv", len(occ_rows), OCC_HEADER),
    ]:
        lines = (tmp_dir / fname).read_text(encoding="utf-8").splitlines()
        actual_hdr = lines[0] if lines else ""
        if actual_hdr != expected_hdr:
            raise SystemExit(
                f"stress-inventory: неверный заголовок в {fname}:\n"
                f"  ожидался: {expected_hdr!r}\n  получен: {actual_hdr!r}"
            )
        if len(lines) - 1 != expected_rows:
            raise SystemExit(
                f"stress-inventory: несовпадение числа строк в {fname}: "
                f"ожидалось {expected_rows}, фактически {len(lines) - 1}"
            )

    # --- summary.json (written last) ------------------------------------------
    by_reason: Counter[str] = Counter()
    occ_by_reason: Counter[str] = Counter()
    for r in risk_rows:
        for reason in r["reason"].split("+"):
            if reason in _REASON_ORDER:
                by_reason[reason] += 1
                occ_by_reason[reason] += r["freq"]

    summary = {
        "schema_version": 1,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "files": {
            "risk.tsv": {
                "sha256": _file_sha256(tmp_dir / "risk.tsv"),
                "rows": len(risk_rows),
            },
            "omographs.tsv": {
                "sha256": _file_sha256(tmp_dir / "omographs.tsv"),
                "rows": len(occ_rows),
            },
        },
        "inputs": _input_fingerprint(
            paths.MODELS / "dictionary" / "omographs.json.gz",
            paths.TEXT / "pronounce.yaml",
            paths.TEXT / "stress_watch.yaml",
            paths.TEXT / "stress_verified.yaml",
            manifest_paths,
        ),
        "counters": {
            "top": by_reason["top"],
            "homograph": by_reason["homograph"],
            "name": by_reason["name"],
            "dict": by_reason["dict"],
            "total_risk_forms": len(risk_rows),
            "total_occ_rows": len(occ_rows),
        },
        "diagnostics": {
            "sections_validated": sections_validated,
            "sections_skipped_no_manifest": len(skipped_sections),
            "skipped_sections": skipped_sections,
            "ruaccent_resolved": ruaccent_resolved,
            "ruaccent_unresolved_no_stress": ruaccent_no_stress,
            "ruaccent_unresolved_mismatch": ruaccent_mismatch,
            "ruaccent_available": process is not None,
        },
    }
    (tmp_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- atomic publish -------------------------------------------------------
    _atomic_publish_inventory(tmp_dir, stress_dir / "inventory")

    # --- console summary ------------------------------------------------------
    inventory_dir = stress_dir / "inventory"
    print(f"stress-inventory: {len(risk_rows)} форм в списке риска → {inventory_dir / 'risk.tsv'}")
    for reason in ("top", "homograph", "name", "dict"):
        label = {
            "top": f"top-{top_n}", "homograph": "омографы",
            "name": "имена", "dict": "словарь",
        }[reason]
        print(f"  {label:<12} {by_reason[reason]:4d} форм  {occ_by_reason[reason]:7d} вхождений")
    if skipped_sections:
        print(f"  пропущено (нет манифеста): {len(skipped_sections)} секций")
    if verified:
        print(f"  исключено (verified): {len(verified)} форм")
    if occ_rows:
        print(f"  детали омографов → {inventory_dir / 'omographs.tsv'}")
        if process:
            print(
                f"  RUAccent: resolved={ruaccent_resolved}, "
                f"no_stress={ruaccent_no_stress}, mismatch={ruaccent_mismatch}"
            )
        else:
            print(
                "  (RUAccent не загружен — ruaccent пусто; "
                "запусти с models/ для заполнения)"
            )
    print(f"  summary → {inventory_dir / 'summary.json'}")
    return 0
