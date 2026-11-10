"""Stress risk inventory from manifest.jsonl + text/*.norm.txt  — Iteration 5.

Outputs (out/stress/inventory/):
  risk.tsv      — aggregated risk list (top/homograph/name/dict)
  omographs.tsv — per-occurrence detail for dictionary homographs
  summary.json  — SHA-256 of both TSVs, input fingerprint, counters
  current.json  — {gen_id, summary_sha256} pointer to gen/<gen_id>/

Generation archive (out/stress/gen/<gen_id>/):
  same three files, immutable once written.

Paragraph boundaries are determined by pause_after_ms from manifest rows:
  pause_after_ms < paragraph_ms  → space separator (same paragraph)
  pause_after_ms >= paragraph_ms → \\n\\n separator (paragraph boundary)
This matches the boundary logic in joins.py exactly.

Fatal conditions (SystemExit, non-zero):
  • models/dictionary/omographs.json.gz absent, corrupt, or wrong structure/types
  • Token mismatch between manifest and norm.txt for any section
  • Any exception from RUAccent init (ImportError, FileNotFoundError, OSError, or other)
  • Word form longer than 80 characters
  • No sections have a manifest (sections_validated == 0)
  • No Cyrillic tokens found across all processed sections
  • Missing manifest for a section not in sections: allowlist (exclude.yaml)
  • Allowlisted section token count mismatch (norm.txt changed)
  • Allowlisted section now has a manifest (stale exclusion)

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
from audiobook.stress_fp import INVENTORY_ALGO_VERSION, stress_params

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
_WORD_PLUS = re.compile(r"[а-яёА-ЯЁ+]+")
_SENT_END = re.compile(r"(?<=[.!?…])\s+")
_INITIAL_DOT = re.compile(r"(?<![А-ЯЁа-яёA-Za-z0-9])[А-ЯЁ]\.$")


# ── loaders ───────────────────────────────────────────────────────────────────

def _omograph_dict() -> dict[str, list[str]]:
    """Load omograph dictionary.  Missing, corrupt, or wrong structure/types is fatal."""
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
            f"(ожидался dict, получен {type(data).__name__}): {p}\nСтатус: blocked."
        )
    for key, val in data.items():
        if not isinstance(val, list) or not all(isinstance(s, str) for s in val):
            raise SystemExit(
                f"stress-inventory: неверный тип значения в словаре для ключа {key!r}: "
                f"ожидался list[str], получен {type(val).__name__!r}.\nСтатус: blocked."
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


def _load_exclude_forms(p: Path) -> set[str]:
    """Strict exclusions — forms here never appear in risk.tsv regardless of reason.

    File format (YAML):
      exclude:
        - форма1
        - форма2
    """
    if not p.exists():
        p.write_text(
            "# Strict inventory exclusions — forms listed here are NEVER shown in\n"
            "# risk.tsv, even if they are top-N, omographs, or names. Use sparingly:\n"
            "# prefer stress_verified.yaml for forms confirmed by ear.\n"
            "#\n"
            "# exclude:\n"
            "#   - это\n"
            "#   - что\n"
            "exclude: []\n",
            encoding="utf-8",
        )
        return set()
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return set(str(w).lower() for w in (data.get("exclude") or []))


def _load_section_skip(p: Path) -> dict[str, dict]:
    """Return {section_name: {tokens, reason}} from exclude.yaml sections: key.

    Sections in this dict are allowed to have missing manifests.
    """
    if not p.exists():
        return {}
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    result: dict[str, dict] = {}
    for entry in data.get("sections") or []:
        sec = str(entry.get("section", "")).strip()
        if sec:
            result[sec] = {
                "tokens": int(entry.get("tokens", -1)),
                "reason": str(entry.get("reason", "")),
            }
    return result


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


# ── section data (manifest-based, pause-aware paragraph detection) ─────────────

def _cyrillic_tokens(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in _WORD.findall(text)]


def _build_section_data(
    section: str, paragraph_ms: int
) -> tuple[str, list[int], list[str]]:
    """Concatenate manifest chunk texts into one string; build bisect intervals.

    Paragraph boundaries are determined by pause_after_ms from manifest rows:
      row["pause_after_ms"] < paragraph_ms  → space (same paragraph continues)
      row["pause_after_ms"] >= paragraph_ms → \\n\\n (new paragraph)

    This matches joins.py _within_para_pairs() boundary logic exactly.

    Returns (full_text, starts, chunk_ids) where starts[i] is the character
    offset of chunk chunk_ids[i] inside full_text.

    Also validates _cyrillic_tokens(full_text) == _cyrillic_tokens(norm.txt).
    Raises SystemExit on token mismatch.
    """
    manifest_path = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(
            f"stress-inventory: манифест отсутствует: {manifest_path}\nСтатус: blocked."
        )

    try:
        from audiobook.chunker import _read_manifest
        rows = _read_manifest(manifest_path)
    except Exception as exc:
        raise SystemExit(
            f"stress-inventory: не удалось прочитать манифест {manifest_path}: {exc}\n"
            "Статус: blocked."
        ) from None

    norm_path = paths.TEXT / f"{section}.norm.txt"
    norm_text = norm_path.read_text(encoding="utf-8") if norm_path.exists() else None

    full_parts: list[str] = []
    starts: list[int] = []
    chunk_ids: list[str] = []
    pos = 0

    for i, row in enumerate(rows):
        text = row.get("text") or ""
        cid = row.get("id", "?")

        if pos == 0:
            sep = ""
        else:
            prev_pause = rows[i - 1].get("pause_after_ms", paragraph_ms)
            sep = " " if prev_pause < paragraph_ms else "\n\n"

        starts.append(pos + len(sep))
        chunk_ids.append(cid)
        full_parts.append(sep + text)
        pos += len(sep) + len(text)

    full_text = "".join(full_parts)

    if norm_text is not None:
        m_toks = _cyrillic_tokens(full_text)
        n_toks = _cyrillic_tokens(norm_text)
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

def _split_sentences_with_pos(text: str) -> list[tuple[str, int]]:
    """Split text into (sentence, absolute_start_in_text) pairs.

    Respects paragraph boundaries (\\n\\n).  Single-letter initials (А., В.)
    do not create sentence boundaries.
    """
    result: list[tuple[str, int]] = []
    para_offset = 0

    for para_text in text.split("\n\n"):
        para = para_text.strip()
        if para:
            leading = len(para_text) - len(para_text.lstrip())
            para_abs_start = para_offset + leading

            splits = [0]
            for m in _SENT_END.finditer(para):
                prev = para[:m.start() + 1].rstrip()
                if _INITIAL_DOT.search(prev):
                    continue
                splits.append(m.end())
            splits.append(len(para))

            for i in range(len(splits) - 1):
                raw = para[splits[i]:splits[i + 1]]
                s = raw.strip()
                if s:
                    raw_leading = len(raw) - len(raw.lstrip())
                    s_abs = para_abs_start + splits[i] + raw_leading
                    result.append((s, s_abs))

        para_offset += len(para_text) + 2  # +2 for "\n\n"

    return result


def _char_context(full_text: str, char_pos: int, word_len: int) -> str:
    """Context window guaranteed ≤80 chars that fully contains the form.

    char_pos must be an absolute position in full_text.
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
    return full_text[start: start + 80].replace("\n", " ")


# ── RUAccent resolution ───────────────────────────────────────────────────────

def _try_accentizer():
    """Return accentizer.process_all callable, or raise SystemExit on any init failure."""
    try:
        from audiobook.accent import _get_accentizer  # noqa: PLC0415
        return _get_accentizer().process_all
    except Exception as exc:
        raise SystemExit(
            f"stress-inventory: RUAccent инициализация завершилась с ошибкой:\n"
            f"  {exc!r}\nСтатус: blocked."
        ) from exc


def _ruaccent_meta() -> dict:
    """Return {version, nn_fingerprint} for RUAccent, best-effort.

    Uses sys.modules to avoid triggering onnxruntime side effects when
    ruaccent was not imported during this run (weights missing).
    """
    ra = sys.modules.get("ruaccent")
    if ra is None:
        return {"version": "not_loaded"}
    version = getattr(ra, "__version__", "unknown")
    nn_path = paths.MODELS / "nn"
    if nn_path.exists():
        # Fast fingerprint: sorted (name, size) pairs — avoids reading weights
        entries = sorted(
            (str(p.relative_to(nn_path)), p.stat().st_size)
            for p in nn_path.rglob("*") if p.is_file()
        )
        h = hashlib.sha256(json.dumps(entries).encode()).hexdigest()
        return {"version": version, "nn_fingerprint": h}
    return {"version": version, "nn_fingerprint": "absent"}


def _ruaccent_resolve(form: str, occ_in_sent: int, sent: str,
                      accented: str) -> tuple[str, str]:
    """Match RUAccent output for one specific occurrence of form in sent.

    Uses per-token index matching.  form.lower() (preserving ё) is used to
    find the exact token position, avoiding ё/е confusion between homonyms.
    difflib.SequenceMatcher fallback when tokenization diverges.

    Returns (stressed_form_or_empty, status) where status is:
      "resolved"                       — stress mark found
      "unresolved/no_stress"           — form found, no '+' present
      "unresolved/tokenization_mismatch"  — SequenceMatcher gap covers position
    """
    form_exact = form.lower()
    input_toks_exact = [m.group().lower() for m in _WORD.finditer(sent)]
    input_toks_norm = [t.replace("ё", "е") for t in input_toks_exact]

    acc_toks_plus = [m.group() for m in _WORD_PLUS.finditer(accented)]
    acc_toks_norm = [t.replace("+", "").lower().replace("ё", "е") for t in acc_toks_plus]

    form_positions = [i for i, t in enumerate(input_toks_exact) if t == form_exact]
    if occ_in_sent >= len(form_positions):
        return "", "unresolved/no_stress"
    target_i = form_positions[occ_in_sent]

    def _extract(acc_pos: int) -> tuple[str, str]:
        if acc_pos >= len(acc_toks_plus):
            return "", "unresolved/no_stress"
        tok = acc_toks_plus[acc_pos]
        return (tok, "resolved") if "+" in tok else (tok, "unresolved/no_stress")

    if input_toks_norm == acc_toks_norm:
        return _extract(target_i)

    sm = difflib.SequenceMatcher(None, input_toks_norm, acc_toks_norm, autojunk=False)
    for i1, j1, n in sm.get_matching_blocks():
        if n and i1 <= target_i < i1 + n:
            return _extract(j1 + (target_i - i1))
    return "", "unresolved/tokenization_mismatch"


# ── atomic publish ────────────────────────────────────────────────────────────

def _prepare_tmp_dir(stress_dir: Path) -> Path:
    """Handle stale artifacts from interrupted previous runs; return fresh tmp dir.

    Must be called BEFORE any failure-prone loader so that inventory.old/ is
    restored to inventory/ even if the current run exits early.
    """
    tmp_dir = stress_dir / "inventory.tmp"
    old_dir = stress_dir / "inventory.old"
    inventory_dir = stress_dir / "inventory"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    if old_dir.exists():
        if not inventory_dir.exists():
            # Interrupted at the second rename — restore last confirmed report
            old_dir.rename(inventory_dir)
        else:
            # Interrupted at the delete step — clean up orphan
            shutil.rmtree(old_dir)

    tmp_dir.mkdir(parents=True)
    return tmp_dir


def _atomic_publish_inventory(
    tmp_dir: Path, stress_dir: Path, gen_id: str
) -> None:
    """Replace inventory/ with inventory.tmp/ atomically and archive to gen/<gen_id>/.

    Sequence:
      1. Write current.json into tmp_dir
      2. Copy tmp_dir → gen/<gen_id>/  (immutable archive)
      3. inventory/ → inventory.old/ → tmp_dir → inventory/ → delete old/
    """
    inventory_dir = stress_dir / "inventory"
    old_dir = stress_dir / "inventory.old"
    gen_dir = stress_dir / "gen" / gen_id

    # Write current.json (summary SHA already computed by caller)
    summary_sha = hashlib.sha256(
        (tmp_dir / "summary.json").read_bytes()
    ).hexdigest()
    cur = {"gen_id": gen_id, "summary_sha256": summary_sha}
    (tmp_dir / "current.json").write_text(
        json.dumps(cur, indent=2), encoding="utf-8"
    )

    # Archive to gen/<gen_id>/ before the rename (so it survives a crash)
    gen_dir.parent.mkdir(parents=True, exist_ok=True)
    if gen_dir.exists():
        shutil.rmtree(gen_dir)
    shutil.copytree(tmp_dir, gen_dir)

    # Atomic swap
    if inventory_dir.exists():
        inventory_dir.rename(old_dir)
    tmp_dir.rename(inventory_dir)
    if old_dir.exists():
        shutil.rmtree(old_dir)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
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
                        watch_p: Path, verified_p: Path, exclude_p: Path,
                        section_manifest_paths: list[Path],
                        norm_paths: list[Path],
                        top_n: int) -> dict:
    """SHA-256 fingerprints of all inputs that determine the report content."""
    def _sha(p: Path) -> str:
        return _file_sha256(p) if p.exists() else "absent"

    return {
        "algo_version": INVENTORY_ALGO_VERSION,
        "top_n": top_n,
        "dict": {"path": str(omograph_path), "sha256": _sha(omograph_path)},
        "pronounce": {"sha256": _sha(pronounce_p)},
        "watch": {"sha256": _sha(watch_p)},
        "verified": {"sha256": _sha(verified_p)},
        "exclude": {"sha256": _sha(exclude_p)},
        "manifests": {
            mp.parent.name: _sha(mp) for mp in section_manifest_paths
        },
        "norm_texts": {
            np.name: _sha(np) for np in norm_paths
        },
        "ruaccent": _ruaccent_meta(),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def run(config: dict) -> int:  # noqa: C901
    params = stress_params(config)
    top_n = params["top_n"]
    paragraph_ms = params["paragraph_ms"]

    # Recover any interrupted atomic publish BEFORE failure-prone loaders.
    stress_dir = paths.OUT / "stress"
    stress_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = _prepare_tmp_dir(stress_dir)

    exclude_p = paths.TEXT / "stress_inventory_exclude.yaml"
    omographs = _omograph_dict()
    exclude_forms = _load_exclude_forms(exclude_p)
    section_skip = _load_section_skip(exclude_p)
    verified = _load_verified(paths.TEXT / "stress_verified.yaml")
    pronounce_forms = _load_pronounce_forms(paths.TEXT / "pronounce.yaml")
    watch_forms = _load_watch_forms(paths.TEXT / "stress_watch.yaml")

    # --- section scan ---------------------------------------------------------
    form_count: Counter[str] = Counter()
    form_example: dict[str, str] = {}
    form_example_len: dict[str, int] = {}

    cap_in_mid: set[str] = set()
    form_lowercase_seen: set[str] = set()

    occ_rows: list[dict] = []
    occ_sents: list[str] = []

    manifest_paths: list[Path] = []
    norm_paths: list[Path] = []
    skipped_sections: list[str] = []
    sections_validated = 0
    invalid_context_count = 0
    excluded_tokens = 0

    for norm_path in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm_path.stem.replace(".norm", "")
        norm_paths.append(norm_path)
        manifest_path = paths.OUT / "sections" / section / "manifest.jsonl"

        if section in section_skip:
            if manifest_path.exists():
                raise SystemExit(
                    f"stress-inventory: секция '{section}' в allowlist, но манифест существует.\n"
                    "Удали запись из sections: в stress_inventory_exclude.yaml.\n"
                    "Статус: blocked."
                )
            actual = len(_cyrillic_tokens(norm_path.read_text(encoding="utf-8")))
            expected = section_skip[section]["tokens"]
            if actual != expected:
                raise SystemExit(
                    f"stress-inventory: секция '{section}' в allowlist: "
                    f"токенов {actual}, ожидалось {expected}.\n"
                    "Обнови tokens: в stress_inventory_exclude.yaml.\n"
                    "Статус: blocked."
                )
            excluded_tokens += actual
            skipped_sections.append(section)
            continue

        if not manifest_path.exists():
            raise SystemExit(
                f"stress-inventory: манифест отсутствует для секции '{section}'.\n"
                "Добавь запись в sections: в stress_inventory_exclude.yaml "
                "или запусти chunker.\nСтатус: blocked."
            )


        manifest_paths.append(manifest_path)
        full_text, starts, chunk_ids = _build_section_data(section, paragraph_ms)
        sections_validated += 1

        for sent, sent_abs_start in _split_sentences_with_pos(full_text):
            sent_form_occ: Counter[str] = Counter()

            for wi, m in enumerate(_WORD.finditer(sent)):
                word = m.group()
                lower = word.lower()
                char_pos = m.start()           # relative to sent
                global_pos = sent_abs_start + char_pos  # absolute in full_text
                word_len = len(word)

                if word_len > 80:
                    _char_context(full_text, global_pos, word_len)  # raises

                form_count[lower] += 1

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
                        snippet = _char_context(full_text, global_pos, word_len)
                        form_example[lower] = snippet
                        form_example_len[lower] = 999
                elif slen <= 80 and slen < form_example_len[lower]:
                    form_example[lower] = stripped
                    form_example_len[lower] = slen

                if lower in omographs and len(omographs[lower]) > 1:
                    occ_in_sent = sent_form_occ[lower]
                    sent_form_occ[lower] += 1

                    chunk_id = _chunk_id_at(starts, chunk_ids, global_pos)
                    context = _char_context(full_text, global_pos, word_len)

                    form_text = full_text[global_pos:global_pos + word_len]
                    if form_text.lower() not in context.lower():
                        invalid_context_count += 1

                    occ_rows.append({
                        "form": lower,
                        "section": section,
                        "chunk": chunk_id,
                        "context": context,
                        "options": " / ".join(omographs[lower]),
                        "ruaccent": "",
                        "ruaccent_status": "",
                        "occ_in_sent": occ_in_sent,
                    })
                    occ_sents.append(sent)

    if skipped_sections:
        print(
            f"  ДИАГНОСТИКА: пропущено {len(skipped_sections)} секций (allowlist): "
            f"{', '.join(skipped_sections)}",
            file=sys.stderr,
        )

    if sections_validated == 0:
        raise SystemExit(
            "stress-inventory: ни одна секция не содержит манифест.\n"
            "Запусти chunker для генерации манифестов перед stress-inventory.\n"
            "Статус: blocked."
        )

    if not form_count:
        raise SystemExit(
            "stress-inventory: ни одной словоформы не найдено во всех секциях.\n"
            "Статус: blocked."
        )

    name_forms = cap_in_mid

    # --- RUAccent resolution (once per unique sentence) -----------------------
    process = _try_accentizer()
    ruaccent_resolved = 0
    ruaccent_no_stress = 0
    ruaccent_mismatch = 0

    if process and occ_rows:
        sent_to_indices: dict[str, list[int]] = {}
        for idx, sent in enumerate(occ_sents):
            sent_to_indices.setdefault(sent, []).append(idx)

        for sent, indices in sent_to_indices.items():
            try:
                accented = process(sent)
            except Exception as exc:
                raise SystemExit(
                    f"stress-inventory: RUAccent завершился с ошибкой:\n"
                    f"  {exc!r}\nСтатус: blocked."
                ) from exc

            for idx in indices:
                row = occ_rows[idx]
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

    # exclude_forms: strict exclusions (never appear regardless of reason)
    # verified: forms confirmed by ear (also excluded)
    excluded = exclude_forms | verified

    all_risk = (
        top_forms
        | omograph_forms
        | (name_forms & known_forms)
        | (pronounce_forms & known_forms)
        | (watch_forms & known_forms)
    ) - excluded

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

    # --- summary.json (written last before publish) ---------------------------
    by_reason: Counter[str] = Counter()
    occ_by_reason: Counter[str] = Counter()
    for r in risk_rows:
        for reason in r["reason"].split("+"):
            if reason in _REASON_ORDER:
                by_reason[reason] += 1
                occ_by_reason[reason] += r["freq"]

    total_tokens = sum(form_count.values()) + excluded_tokens
    risk_token_count = sum(form_count[f] for f in all_risk if f in form_count)
    risk_coverage = round(risk_token_count / total_tokens, 4) if total_tokens else 0.0

    gen_id = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    summary = {
        "schema_version": 1,
        "algo_version": INVENTORY_ALGO_VERSION,
        "gen_id": gen_id,
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
            exclude_p,
            manifest_paths,
            norm_paths,
            top_n,
        ),
        "counters": {
            "top": by_reason["top"],
            "homograph": by_reason["homograph"],
            "name": by_reason["name"],
            "dict": by_reason["dict"],
            "total_risk_forms": len(risk_rows),
            "total_occ_rows": len(occ_rows),
            "total_tokens": total_tokens,
            "risk_token_coverage": risk_coverage,
        },
        "diagnostics": {
            "sections_total": sections_validated + len(skipped_sections),
            "sections_processed": sections_validated,
            "sections_excluded": len(skipped_sections),
            "excluded_tokens": excluded_tokens,
            "sections_validated": sections_validated,
            "sections_skipped_no_manifest": len(skipped_sections),
            "skipped_sections": skipped_sections,
            "ruaccent_resolved": ruaccent_resolved,
            "ruaccent_unresolved_no_stress": ruaccent_no_stress,
            "ruaccent_unresolved_mismatch": ruaccent_mismatch,
            "ruaccent_errors": 0,
            "invalid_context_count": invalid_context_count,
            "ruaccent_available": process is not None,
        },
    }
    (tmp_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- atomic publish with gen archive -------------------------------------
    _atomic_publish_inventory(tmp_dir, stress_dir, gen_id)

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
    if exclude_forms:
        print(f"  исключено (exclude): {len(exclude_forms)} форм")
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
    if invalid_context_count:
        print(f"  ПРЕДУПРЕЖДЕНИЕ: invalid_context={invalid_context_count}", file=sys.stderr)
    print(f"  coverage={risk_coverage:.1%}  tokens={total_tokens}")
    print(f"  gen → {stress_dir / 'gen' / gen_id}")
    print(f"  summary → {inventory_dir / 'summary.json'}")
    return 0
