"""Deterministic local sampling and versioned human annotation transactions.

The current inventory is read only through its validated v5 reader. Gold is an
evaluation ledger; nothing here changes synthesis or supplies machine labels.
Statistical scoring uses the independently supplied pure metrics core.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from audiobook import paths
from audiobook.stress_fp import private_output_guard
from audiobook.unitmap import AnnotationError, validate_section
from audiobook.wordprov import gold_identity

SEED = "t15-7/1"
SEED_V2 = "t15-7/2"
STRATA = (("omograph", 100), ("top300", 60), ("name", 40),
          ("override_covered", 40), ("yo_changed", 40), ("tail", 40))
GOLD_FIELDS = ("source_key", "form_source", "unit_text_sha256", "unit_kind",
               "context_sha256", "context", "gold_vowel", "yo_correct", "labeler", "date")
IDENTITY_FIELDS = ("source_key", "form_source", "unit_text_sha256", "unit_kind", "context_sha256")
LABEL_FIELDS = GOLD_FIELDS[6:]
_WORD = re.compile(r"[а-яёА-ЯЁ]+")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)", re.ASCII)
_HEX = re.compile(r"[a-f0-9]{64}", re.ASCII)
_VOWELS = frozenset("аеёиоуыэюя")


def _error(code):
    raise AnnotationError(code) from None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fold(value):
    return value.lower().replace("ё", "е")


def vowel_count(value):
    return sum(c in _VOWELS for c in value.lower())


def yo_changed(occ):
    def without_yo(text):
        return text.replace("ё", "е").replace("Ё", "Е")
    return (occ.form_synth is not None and occ.form_synth != occ.form_source
            and without_yo(occ.form_synth) == without_yo(occ.form_source))


@dataclass(frozen=True)
class Selection:
    record: dict
    strata_by_key: dict
    one_vowel_aligned: int


def select_sample(rows, source_fp, analysis_fp, *, homographs, names, targets=STRATA):
    """Pure ADR §10 selection; fingerprint targets encode the sampling policy."""
    if (tuple(name for name, _ in targets) != tuple(name for name, _ in STRATA)
            or any(type(n) is not int or n < 0 for _, n in targets)):
        _error("SAMPLE_POLICY_INVALID")
    keys = [row.source_key for row in rows]
    if len(keys) != len(set(keys)):
        _error("OCCURRENCE_IDENTITY_DUPLICATE")
    eligible = [row for row in rows if row.alignment_status == "aligned" and vowel_count(row.form_analysis) >= 2]
    frequencies = Counter(_fold(row.form_source) for row in eligible)
    top = {form for form, _ in sorted(frequencies.items(), key=lambda pair: (-pair[1], pair[0]))[:300]}
    groups = {name: [] for name, _ in targets}
    assignment = {}
    for row in eligible:
        if row.form_source.lower() in homographs:
            name = "omograph"
        elif _fold(row.form_source) in top:
            name = "top300"
        elif row.form_source.lower() in names:
            name = "name"
        elif row.status == "covered_by_override":
            name = "override_covered"
        elif yo_changed(row):
            name = "yo_changed"
        else:
            name = "tail"
        groups[name].append(row.source_key)
        assignment[row.source_key] = name
    selected = []
    counts = {}
    for name, n in targets:
        ranked = sorted(groups[name], key=lambda key: (hashlib.sha256((SEED + "|" + key).encode("utf-8")).hexdigest(), key))
        selected.extend(ranked[:n])
        counts[name] = {"N": len(ranked), "n": min(n, len(ranked))}
    selected.sort()
    fingerprint = _hash({"algo": "sample/1", "source_fp": source_fp, "analysis_fp": analysis_fp,
                         "seed": SEED, "strata": [{"name": name, "n": n} for name, n in targets],
                         "selected_keys_sha256": _hash(selected)})
    return Selection({"sample_fp": fingerprint, "source_fp": source_fp, "analysis_fp": analysis_fp,
                      "strata": counts, "keys": selected}, assignment,
                     sum(row.alignment_status == "aligned" and vowel_count(row.form_analysis) == 1 for row in rows))


# ---------------------------------------------------------------------------
# Sample/2 — updated fingerprint with observer inputs and RESTORED-based stratum
# ---------------------------------------------------------------------------

def select_sample_v2(rows, source_fp, analysis_fp, *, homographs, names,
                     obs_map, norm_digest, yo_map_digest, prep_config_digest,
                     targets=STRATA):
    """Sample/2 selection (ADR G1 §3).

    obs_map: dict mapping source_key → ObsResult for every eligible occurrence.
    yo_changed stratum uses RESTORED (pre-respell forward observation), not form_synth.
    Returns Selection with sample/2 fingerprint; path helpers use _sample_path_v2.
    """
    from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs, UNSUPPORTED_obs
    if (tuple(name for name, _ in targets) != tuple(name for name, _ in STRATA)
            or any(type(n) is not int or n < 0 for _, n in targets)):
        _error("SAMPLE_POLICY_INVALID")
    keys = [row.source_key for row in rows]
    if len(keys) != len(set(keys)):
        _error("OCCURRENCE_IDENTITY_DUPLICATE")
    eligible = [row for row in rows if row.alignment_status == "aligned" and vowel_count(row.form_analysis) >= 2]
    frequencies = Counter(_fold(row.form_source) for row in eligible)
    top = {form for form, _ in sorted(frequencies.items(), key=lambda pair: (-pair[1], pair[0]))[:300]}
    assignment = {}
    groups = {name: [] for name, _ in targets}
    for row in eligible:
        obs = obs_map.get(row.source_key)
        if obs is not None and not isinstance(obs, (RESTORED_obs, NONE_obs, UNSUPPORTED_obs)):
            _error("YO_OBSERVER_UNSUPPORTED")
        is_restored = isinstance(obs, RESTORED_obs)
        if row.form_source.lower() in homographs:
            name = "omograph"
        elif _fold(row.form_source) in top:
            name = "top300"
        elif row.form_source.lower() in names:
            name = "name"
        elif row.status == "covered_by_override":
            name = "override_covered"
        elif is_restored:
            name = "yo_changed"
        else:
            name = "tail"
        groups[name].append(row.source_key)
        assignment[row.source_key] = name
    # Fingerprint: eligible assignment digest over ALL eligible keys.
    eligible_assign_sha = _hash(sorted([sk, assignment[sk]] for sk in assignment))
    # Per-stratum deterministic ranking and selection.
    selected_by_stratum = {}
    counts = {}
    for name, n in targets:
        ranked = sorted(groups[name], key=lambda key: (
            hashlib.sha256(f"{SEED_V2}|{key}".encode("utf-8")).hexdigest(), key
        ))
        selected_by_stratum[name] = ranked[:n]
        counts[name] = {"N": len(groups[name]), "n": min(n, len(groups[name]))}
    selected_by_stratum_sha = _hash(
        {name: sorted(selected_by_stratum[name]) for name, _ in STRATA}
    )
    fingerprint = _hash({
        "algo": "sample/2",
        "source_fp": source_fp,
        "analysis_fp": analysis_fp,
        "observation_contract_version": "yo-observation/1",
        "observation_inputs": {
            "norm_content_sha256": norm_digest,
            "yo_map_sha256": yo_map_digest,
            "prep_config_sha256": prep_config_digest,
        },
        "seed": SEED_V2,
        "strata_order": [name for name, _ in STRATA],
        "population": {name: counts[name]["N"] for name, _ in STRATA},
        "selected_n": {name: counts[name]["n"] for name, _ in STRATA},
        "eligible_assignment_sha256": eligible_assign_sha,
        "selected_by_stratum_sha256": selected_by_stratum_sha,
    })
    all_selected = sorted(sk for keys in selected_by_stratum.values() for sk in keys)
    strata_by_key = {sk: name for name, keys in selected_by_stratum.items() for sk in keys}
    record = {
        "sample_fp": fingerprint,
        "source_fp": source_fp,
        "analysis_fp": analysis_fp,
        "observation_contract_version": "yo-observation/1",
        "observation_inputs": {
            "norm_content_sha256": norm_digest,
            "yo_map_sha256": yo_map_digest,
            "prep_config_sha256": prep_config_digest,
        },
        "strata": counts,
        "eligible_assignment_sha256": eligible_assign_sha,
        "selected_by_stratum_sha256": selected_by_stratum_sha,
        "selected_by_stratum": {name: sorted(selected_by_stratum[name]) for name, _ in STRATA},
        "keys": all_selected,
    }
    return Selection(record, strata_by_key,
                     sum(row.alignment_status == "aligned" and vowel_count(row.form_analysis) == 1 for row in rows))


# ---------------------------------------------------------------------------
# Versioned paths for sample/2
# ---------------------------------------------------------------------------

def _sample_path_v2(sample_fp: str) -> Path:
    return paths.OUT / "stress" / "eval" / "sample" / f"s2-{sample_fp[:16]}.json"


def _todo_path_v2(sample_fp: str) -> Path:
    return paths.TEXT / f"stress_gold.todo.s2-{sample_fp[:16]}.tsv"


def _check_todo_v2(todo_path: Path, requested_rows, gold_rows):
    """Guard versioned sample/2 todo creation.

    absent → guarded creation allowed; same bytes → no-op; different bytes with
    unmerged labels → TODO_HAS_UNMERGED_LABELS; different bytes with all labels
    merged → safe to regenerate.
    """
    if not todo_path.exists():
        return "create"
    before = todo_path.read_bytes()
    expected = serialize_gold(requested_rows, allow_blank=True).encode("utf-8")
    if before == expected:
        return "noop"
    # Different bytes: check for unmerged labels.
    try:
        existing = parse_gold(before.decode("utf-8"), allow_blank=True)
    except (UnicodeError, AnnotationError):
        _error("OWNER_TODO_PROTECTED")
    saved_sigs = {tuple(r[n] for n in GOLD_FIELDS) for r in gold_rows}
    for row in existing:
        if any(row[f] for f in LABEL_FIELDS):
            sig = tuple(row[n] for n in GOLD_FIELDS)
            if sig not in saved_sigs:
                _error("TODO_HAS_UNMERGED_LABELS")
    _error("OWNER_TODO_PROTECTED")  # Different bytes: protected regardless of label state.


# ---------------------------------------------------------------------------
# OS-backed exclusive evaluation lock
# ---------------------------------------------------------------------------

_EVAL_LOCK_NAME = ".wp4.lock"


def _lock_path() -> Path:
    return paths.OUT / "stress" / "eval" / _EVAL_LOCK_NAME


def _open_eval_file(path: Path, *, create: bool = False) -> int:
    """Open a regular file through pinned, no-follow directory descriptors.

    ROOT is an already trusted canonical directory (including macOS aliases
    above it). Explicit paths outside ROOT, used by synthetic callers, traverse
    from the filesystem root without resolving any untrusted components.
    Platforms without atomic relative opens/mkdir fail closed: a path precheck
    is not a safe replacement, including on Windows without a native equivalent.
    The caller owns the returned FD; all directory FDs are closed here.
    """
    if (os.name != "posix" or not getattr(os, "O_NOFOLLOW", 0)
            or not getattr(os, "O_DIRECTORY", 0)
            or os.open not in os.supports_dir_fd
            or os.mkdir not in os.supports_dir_fd
            or os.stat not in os.supports_dir_fd
            or os.stat not in os.supports_follow_symlinks):
        raise OSError("Atomic no-follow directory operations unavailable")
    path = path.absolute()
    root = paths.ROOT
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        root = Path(path.anchor)
        parts = path.relative_to(root).parts
    if not parts or any(part in {".", ".."} for part in parts):
        raise OSError("Unsafe evaluation path")
    directories = []
    raw = -1
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directories.append(os.open(root, directory_flags))  # encoding=N/A: directory FD
        for part in parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directories[-1])  # encoding=N/A: directory FD
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, dir_fd=directories[-1])
                except FileExistsError:
                    pass  # A concurrent creator must still pass the no-follow open.
                child = os.open(part, directory_flags, dir_fd=directories[-1])  # encoding=N/A: directory FD
            directories.append(child)
        flags = os.O_NOFOLLOW | os.O_NONBLOCK
        flags |= (os.O_WRONLY | os.O_CREAT | os.O_APPEND) if create else os.O_RDONLY
        raw = os.open(parts[-1], flags, 0o666, dir_fd=directories[-1])  # encoding=N/A: regular file FD
        if not stat.S_ISREG(os.fstat(raw).st_mode):
            raise OSError("Evaluation target must be a regular file")
        # Detect detached/swapped directories before handing the FD to a reader
        # or lock owner. Security comes from the pinned FDs even if a later swap
        # races this check: no subsequent access resolves the untrusted path.
        for index, part in enumerate(parts[:-1]):
            entry = os.stat(part, dir_fd=directories[index], follow_symlinks=False)
            pinned = os.fstat(directories[index + 1])
            if (not stat.S_ISDIR(entry.st_mode)
                    or (entry.st_dev, entry.st_ino) != (pinned.st_dev, pinned.st_ino)):
                raise OSError("Evaluation directory replaced")
        result, raw = raw, -1
        return result
    finally:
        if raw >= 0:
            os.close(raw)
        for descriptor in reversed(directories):
            os.close(descriptor)


def acquire_eval_lock(lock_path: Path | None = None) -> object:
    """Acquire OS-backed exclusive evaluation lock. Returns opaque lock handle.

    Fails closed with EVAL_LOCK_UNAVAILABLE if unavailable, unsafe, or symlinked.
    Call release_eval_lock(handle) when done.
    """
    path = lock_path if lock_path is not None else _lock_path()
    raw = -1
    try:
        raw = _open_eval_file(path, create=True)
        fd = os.fdopen(raw, "a", encoding="utf-8")
        raw = -1  # Ownership transferred to the file object.
    except (OSError, NotImplementedError):
        _error("EVAL_LOCK_UNAVAILABLE")
    finally:
        if raw >= 0:
            os.close(raw)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        fd.close()
        _error("EVAL_LOCK_UNAVAILABLE")
    return fd


def release_eval_lock(handle: object) -> None:
    """Release a lock handle returned by acquire_eval_lock."""
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except (OSError, IOError):
        pass
    finally:
        handle.close()


def _split_key(key):
    try:
        section, uid, index = key.split("|")
        validate_section(section)
        if not _DECIMAL.fullmatch(uid) or not _DECIMAL.fullmatch(index):
            _error("GOLD_INVALID")
        return section, int(uid), int(index)
    except (ValueError, TypeError, AnnotationError):
        _error("GOLD_INVALID")


class SourceIndex:
    """Lazy normalized-source identities, including historical unselected keys."""
    def __init__(self, units=None):
        self.units = {} if units is None else units

    def resolve(self, key):
        section, uid, index = _split_key(key)
        if section not in self.units:
            from audiobook.chunker import load_units
            if not (paths.TEXT / f"{section}.norm.txt").is_file():
                return None
            try:
                self.units[section] = load_units(*section.split("_", 1))
            except (OSError, ValueError, KeyError, IndexError, SystemExit):
                _error("SOURCE_READ_ERROR")
        units = self.units[section]
        if uid >= len(units):
            return None
        words = list(_WORD.finditer(units[uid]["text"]))
        if index >= len(words):
            return None
        identity = gold_identity(section, units, uid, index)
        return identity, units[uid]["text"], words[index]


@dataclass(frozen=True)
class EvalContext:
    rows: tuple
    source_fp: str
    analysis_fp: str
    sources: SourceIndex
    homographs: frozenset
    names: frozenset
    generation: bytes


def _load_context(config):
    from audiobook.stress_fp import read_occurrences, load_current, stress_params
    from audiobook.stress_inventory import _omograph_dict, _build_section_data, _split_sentences_with_pos
    pointer = paths.OUT / "stress" / "inventory" / "current.json"
    before = pointer.read_bytes()
    rows = tuple(read_occurrences(config))
    summary = load_current(paths.OUT / "stress")
    names = set()
    for section in sorted({row.section for row in rows}):
        text, _, _, _ = _build_section_data(section, stress_params(config)["paragraph_ms"])
        for sentence, _ in _split_sentences_with_pos(text):
            for index, word in enumerate(_WORD.finditer(sentence)):
                if index > 0 and not word.group()[0].islower():
                    names.add(word.group().lower())
    homographs = {form for form, values in _omograph_dict().items() if len(values) > 1}
    if before != pointer.read_bytes() or not summary:
        _error("INVENTORY_CHANGED")
    return EvalContext(rows, summary["source_fp"], summary["analysis_fp"], SourceIndex(),
                       frozenset(homographs), frozenset(names), before)


def _selection(context, config):
    from audiobook.stress_yo_observer import (compute_norm_digest, compute_yo_map_digest,
                                               compute_prep_config_digest)
    yo_map = _load_yo_map(config)
    obs_map = {occ.source_key: _yo_observe_key(occ, context.sources, config)
               for occ in context.rows
               if occ.alignment_status == "aligned" and vowel_count(occ.form_analysis) >= 2}
    return select_sample_v2(
        context.rows, context.source_fp, context.analysis_fp,
        homographs=context.homographs, names=context.names, obs_map=obs_map,
        norm_digest=compute_norm_digest(paths.TEXT),
        yo_map_digest=compute_yo_map_digest(yo_map),
        prep_config_digest=compute_prep_config_digest(config),
    )


def _verify_selection_fresh(stored, context, config):
    """Recompute selection with stored observation inputs; raise SAMPLE_STALE if assignment changed."""
    obs_inputs = stored["observation_inputs"]
    obs_map = {occ.source_key: _yo_observe_key(occ, context.sources, config)
               for occ in context.rows
               if occ.alignment_status == "aligned" and vowel_count(occ.form_analysis) >= 2}
    fresh = select_sample_v2(
        context.rows, context.source_fp, context.analysis_fp,
        homographs=context.homographs, names=context.names, obs_map=obs_map,
        norm_digest=obs_inputs["norm_content_sha256"],
        yo_map_digest=obs_inputs["yo_map_sha256"],
        prep_config_digest=obs_inputs["prep_config_sha256"],
    )
    if fresh.record["sample_fp"] != stored["sample_fp"]:
        _error("SAMPLE_STALE")


def _assert_current(context, config):
    fresh = _load_context(config)
    if (fresh.generation, fresh.source_fp, fresh.analysis_fp) != (context.generation, context.source_fp, context.analysis_fp):
        _error("INVENTORY_CHANGED")


def _load_yo_map(config):
    if (config.get("text_prep") or {}).get("yo_restore"):
        from audiobook.yo import book_map
        return book_map()
    return {}


_V2_SAMPLE_FIELDS = frozenset({
    "sample_fp", "source_fp", "analysis_fp", "observation_contract_version",
    "observation_inputs", "strata", "eligible_assignment_sha256",
    "selected_by_stratum_sha256", "selected_by_stratum", "keys",
})


def _verify_saved_selection(stored, context):
    if set(stored.keys()) != _V2_SAMPLE_FIELDS:
        _error("SAMPLE_INVALID")
    try:
        expected_fp = _hash({
            "algo": "sample/2",
            "source_fp": stored["source_fp"],
            "analysis_fp": stored["analysis_fp"],
            "observation_contract_version": "yo-observation/1",
            "observation_inputs": stored["observation_inputs"],
            "seed": SEED_V2,
            "strata_order": [name for name, _ in STRATA],
            "population": {name: stored["strata"][name]["N"] for name, _ in STRATA},
            "selected_n": {name: stored["strata"][name]["n"] for name, _ in STRATA},
            "eligible_assignment_sha256": stored["eligible_assignment_sha256"],
            "selected_by_stratum_sha256": stored["selected_by_stratum_sha256"],
        })
    except (KeyError, TypeError, ValueError):
        _error("SAMPLE_INVALID")
    if stored.get("sample_fp") != expected_fp:
        _error("SAMPLE_INVALID")
    # Verify selected_by_stratum_sha256 is consistent with selected_by_stratum contents.
    # sample_fp only commits to the digest, not to the keys themselves; without this
    # check an attacker can replace selected_by_stratum keys while keeping sample_fp valid.
    try:
        actual_stratum_sha = _hash(
            {name: sorted(stored["selected_by_stratum"][name]) for name, _ in STRATA}
        )
    except (KeyError, TypeError):
        _error("SAMPLE_INVALID")
    if actual_stratum_sha != stored["selected_by_stratum_sha256"]:
        _error("SAMPLE_INVALID")
    # Verify strata counts are consistent with selected_by_stratum lengths.
    try:
        for name, _ in STRATA:
            if stored["strata"][name]["n"] != len(stored["selected_by_stratum"][name]):
                _error("SAMPLE_INVALID")
    except (KeyError, TypeError):
        _error("SAMPLE_INVALID")
    try:
        expected_keys = sorted(sk for name in stored["selected_by_stratum"]
                               for sk in stored["selected_by_stratum"][name])
    except (KeyError, TypeError):
        _error("SAMPLE_INVALID")
    if stored.get("keys") != expected_keys:
        _error("SAMPLE_INVALID")


def _load_saved_selection(context, config, sample_path=None):
    """Load a saved v2 Selection, verifying integrity. Returns (Selection, path)."""
    def _build(stored, path):
        _verify_saved_selection(stored, context)
        # Recompute the deterministic assignment from the authoritative context;
        # a forged or malformed selection with internally-consistent stored digests
        # but wrong keys cannot survive this check.
        _verify_selection_fresh(stored, context, config)
        strata_by_key = {sk: name
                         for name, keys in stored["selected_by_stratum"].items()
                         for sk in keys}
        one_vowel = sum(occ.alignment_status == "aligned" and vowel_count(occ.form_analysis) == 1
                        for occ in context.rows)
        return Selection(stored, strata_by_key, one_vowel), path

    if sample_path is not None:
        try:
            stored = json.loads(sample_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            _error("SAMPLE_INVALID")
        return _build(stored, sample_path)

    sample_dir = paths.OUT / "stress" / "eval" / "sample"
    candidates = sorted(sample_dir.glob("s2-*.json")) if sample_dir.exists() else []
    for path in candidates:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            continue
        if (stored.get("source_fp") == context.source_fp
                and stored.get("analysis_fp") == context.analysis_fp):
            return _build(stored, path)
    _error("SAMPLE_INVALID")


def _safe_cell(value):
    return (type(value) is str and not any(unicodedata.category(c) in ("Cc", "Cs", "Zl", "Zp") for c in value))


def validate_gold(row, occ=None, *, allow_blank=False, historical=False, allow_na_yo=False):
    """Validate wire grammar; apply current ё evidence only to active versions.

    A stale historical 'yo' label may refer to its old, unstored synth spelling.
    Retain it without guessing its position; only a current valid row can score.
    allow_na_yo=True: skip yo_correct∈{y,n} requirement (source-only merge paths).
    """
    if type(row) is not dict or set(row) != set(GOLD_FIELDS) or any(not _safe_cell(row[name]) for name in GOLD_FIELDS):
        _error("GOLD_INVALID")
    _split_key(row["source_key"])
    if (not _WORD.fullmatch(row["form_source"]) or not row["unit_kind"]
            or not _HEX.fullmatch(row["unit_text_sha256"]) or not _HEX.fullmatch(row["context_sha256"])
            or not row["context"] or len(row["context"]) > 80):
        _error("GOLD_INVALID")
    blank = all(row[field] == "" for field in LABEL_FIELDS)
    if blank and allow_blank:
        return dict(row)
    if any(not row[field] for field in LABEL_FIELDS) or not row["labeler"].strip():
        _error("GOLD_INVALID")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["date"]):
        _error("GOLD_INVALID")
    try:
        datetime.date.fromisoformat(row["date"])
    except ValueError:
        _error("GOLD_INVALID")
    if row["yo_correct"] not in ("y", "n", "na"):
        _error("GOLD_INVALID")
    if occ is not None and yo_changed(occ) and not allow_na_yo and row["yo_correct"] not in ("y", "n"):
        _error("GOLD_INVALID")
    result = dict(row)
    label = row["gold_vowel"]
    if label in ("ambiguous", "unknown_name"):
        return result
    if label == "yo":
        text = row["form_source"].lower()
        if text.count("ё") == 1:
            return result
        if occ is not None and yo_changed(occ) and occ.form_synth.lower().count("ё") == 1:
            return result
        if historical and "ё" not in text and "е" in text:
            return result  # Unverifiable historical spelling, never used as active evidence.
        _error("GOLD_INVALID")
    values = label.removeprefix("variants:").split("|") if label.startswith("variants:") else [label]
    if label.startswith("variants:") and len(values) < 2:
        _error("GOLD_INVALID")
    if any(not _DECIMAL.fullmatch(value) for value in values):
        _error("GOLD_INVALID")
    try:
        indices = [int(value) for value in values]
    except ValueError:
        _error("GOLD_INVALID")
    if (len(set(indices)) != len(indices) or indices != sorted(indices)
            or any(index >= vowel_count(row["form_source"]) for index in indices)):
        _error("GOLD_INVALID")
    result["gold_vowel"] = label
    return result


def parse_gold(text, *, allow_blank=False):
    if isinstance(text, str):
        text = text.replace("\r\n", "\n")  # Native human-editor exports; canonical writer always uses LF.
    if not isinstance(text, str) or not text.endswith("\n"):
        _error("GOLD_INVALID")
    lines = text[:-1].split("\n")
    if lines[0] != "\t".join(GOLD_FIELDS):
        _error("GOLD_INVALID")
    result = []
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) != len(GOLD_FIELDS):
            _error("GOLD_INVALID")
        result.append(validate_gold(dict(zip(GOLD_FIELDS, cells)), allow_blank=allow_blank, historical=True))
    return result


def serialize_gold(rows, *, allow_blank=False):
    validated = [validate_gold(row, allow_blank=allow_blank, historical=True) for row in rows]
    validated.sort(key=lambda row: tuple(row[name] for name in GOLD_FIELDS))
    return "\t".join(GOLD_FIELDS) + "\n" + "".join("\t".join(row[name] for name in GOLD_FIELDS) + "\n" for row in validated)


@dataclass(frozen=True)
class GoldState:
    active: dict
    stale: tuple
    duplicates: int
    legacy: tuple = ()  # LEGACY_YO_UNRESOLVED rows with current five-field identity


def _is_legacy_yo(row: dict) -> bool:
    """True when form_source has е but no ё and gold_vowel=yo: LEGACY_YO_UNRESOLVED."""
    text = row["form_source"].lower()
    return row["gold_vowel"] == "yo" and "ё" not in text and "е" in text


def _source_vowel_set(row: dict):
    """Canonical vowel index set from form_source; None for non-usable labels (ADR T09)."""
    gv = row["gold_vowel"]
    if gv in ("ambiguous", "unknown_name"):
        return None
    if gv == "yo":
        vowels = [c for c in row["form_source"].lower() if c in _VOWELS]
        yo_indices = [i for i, c in enumerate(vowels) if c == "ё"]
        return frozenset(yo_indices) if len(yo_indices) == 1 else None
    return frozenset(map(int, gv.removeprefix("variants:").split("|")))


def inspect_ledger(rows, context):
    by_key = {row.source_key: row for row in context.rows}
    active, stale, legacy_rows = {}, [], []
    duplicates = 0
    for raw in rows:
        row = validate_gold(raw, historical=True)
        current = context.sources.resolve(row["source_key"])
        if current is None or any(row[name] != current[0][name] for name in IDENTITY_FIELDS):
            stale.append(row)
            continue
        if _is_legacy_yo(row):
            # LEGACY_YO_UNRESOLVED: source predicate only (ADR §1.5); never consult observer.
            legacy_rows.append(row)
            continue
        occ = by_key.get(row["source_key"])
        usable_context = occ is not None and occ.alignment_status == "aligned" and vowel_count(occ.form_analysis) >= 2
        row = validate_gold(row, occ if usable_context else None, historical=not usable_context)
        key = row["source_key"]
        if key in active:
            vs_e, vs_n = _source_vowel_set(active[key]), _source_vowel_set(row)
            if (vs_e is None or vs_n is None or vs_e != vs_n) and \
               (active[key]["gold_vowel"], active[key]["yo_correct"]) != (row["gold_vowel"], row["yo_correct"]):
                _error("GOLD_ACTIVE_CONFLICT")
            duplicates += 1
            if tuple(row[n] for n in GOLD_FIELDS) < tuple(active[key][n] for n in GOLD_FIELDS):
                active[key] = row
        else:
            active[key] = row
    return GoldState(active, tuple(stale), duplicates, tuple(legacy_rows))


@dataclass(frozen=True)
class AuditResult:
    status: str
    code: str
    gold_rows: int
    archive_rows: int
    archive_only_rows: int
    excess_duplicates: int
    archive_missing: bool


def audit_archive_compatibility(config) -> AuditResult:
    """Read-only multiset audit: archive ⊆ gold (exact 10-field tuples).

    Explicit invocation only. No lock, no writes, no context/generation load.
    T15: parse_gold rejects noncanonical variants → GOLD_INVALID / ARCHIVE_INVALID.
    Always returns AuditResult; never raises AnnotationError.

    archive_only_rows: physical archive rows with no matching gold tuple.
    excess_duplicates: extra copies of tuples that DO exist in gold (ac > gc, gc > 0).
    archive_missing: True iff archive file is absent at time of initial read.
    """
    # Tri-state sentinels: distinct from bytes and from each other.
    _MISSING = object()     # FileNotFoundError — file genuinely absent
    _READ_ERROR = object()  # other OSError — file exists but unreadable

    def _read_state(path):
        """Return bytes, _MISSING (absent), or _READ_ERROR (unreadable)."""
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return _MISSING
        except OSError:
            return _READ_ERROR

    gold_path = paths.TEXT / "stress_gold.tsv"
    archive_path = paths.TEXT / "stress_gold.archive.tsv"

    # Phase 1: initial reads.
    # READ_ERROR on initial read → immediate structured error; never silently empty.
    gold_before = _read_state(gold_path)
    if gold_before is _READ_ERROR:
        return AuditResult(status="ERROR", code="GOLD_INVALID",
                           gold_rows=0, archive_rows=0,
                           archive_only_rows=0, excess_duplicates=0,
                           archive_missing=False)

    archive_before = _read_state(archive_path)
    if archive_before is _READ_ERROR:
        return AuditResult(status="ERROR", code="ARCHIVE_INVALID",
                           gold_rows=0, archive_rows=0,
                           archive_only_rows=0, excess_duplicates=0,
                           archive_missing=False)

    archive_missing = archive_before is _MISSING

    # Phase 2: parse — collect errors without returning
    gold_parse_error = None
    gold_rows_list: list = []
    if gold_before is not _MISSING:
        try:
            gold_rows_list = parse_gold(gold_before.decode("utf-8"))
        except (UnicodeError, AnnotationError):
            gold_parse_error = "GOLD_INVALID"

    archive_parse_error = None
    archive_rows_list: list = []
    if archive_before is not _MISSING:
        try:
            archive_rows_list = parse_gold(archive_before.decode("utf-8"))
        except (UnicodeError, AnnotationError):
            archive_parse_error = "ARCHIVE_INVALID"

    # Phase 3: staleness recheck using the same tri-state.
    # Any change (MISSING↔bytes↔READ_ERROR, or different bytes) → STALE.
    # _MISSING and _READ_ERROR use identity comparison; bytes use value comparison.
    gold_after = _read_state(gold_path)
    archive_after = _read_state(archive_path)

    def _err(code):
        return AuditResult(
            status="ERROR", code=code,
            gold_rows=0, archive_rows=0,
            archive_only_rows=0, excess_duplicates=0,
            archive_missing=archive_missing,
        )

    if gold_after != gold_before or archive_after != archive_before:
        return _err("ARCHIVE_AUDIT_STALE")

    if gold_parse_error:
        return _err(gold_parse_error)
    if archive_parse_error:
        return _err(archive_parse_error)

    gold_ctr: Counter = Counter(tuple(row[f] for f in GOLD_FIELDS) for row in gold_rows_list)
    archive_ctr: Counter = Counter(tuple(row[f] for f in GOLD_FIELDS) for row in archive_rows_list)

    # Physical archive rows with no gold match at all.
    archive_only_rows = sum(ac for t, ac in archive_ctr.items() if gold_ctr[t] == 0)
    # Extra copies of tuples that exist in gold but archive has more of.
    excess_duplicates = sum(ac - gold_ctr[t] for t, ac in archive_ctr.items()
                            if gold_ctr[t] > 0 and ac > gold_ctr[t])

    if archive_only_rows or excess_duplicates:
        return AuditResult(
            status="BLOCKED", code="ARCHIVE_COMPAT_BLOCKED",
            gold_rows=len(gold_rows_list), archive_rows=len(archive_rows_list),
            archive_only_rows=archive_only_rows, excess_duplicates=excess_duplicates,
            archive_missing=archive_missing,
        )
    return AuditResult(
        status="PASS", code="OK",
        gold_rows=len(gold_rows_list), archive_rows=len(archive_rows_list),
        archive_only_rows=0, excess_duplicates=0, archive_missing=archive_missing,
    )


def _todo_row(occ, sources):
    current = sources.resolve(occ.source_key)
    if current is None or current[0]["form_source"] != occ.form_source:
        _error("SOURCE_IDENTITY_MISMATCH")
    identity, text, word = current
    if (word.start(), word.end()) != (occ.norm_start, occ.norm_end):
        _error("SOURCE_IDENTITY_MISMATCH")
    from audiobook.stress_inventory import _char_context
    context = _char_context(text, word.start(), word.end() - word.start())
    return validate_gold({**identity, "context": context, **{field: "" for field in LABEL_FIELDS}}, allow_blank=True)


def _optional_bytes(path):
    return path.read_bytes() if path.exists() else None


def _read_ledger(path):
    data = _optional_bytes(path)
    try:
        return ([] if data is None else parse_gold(data.decode("utf-8"))), data
    except UnicodeError:
        _error("GOLD_INVALID")


def _windows_sync_directory(directory):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    create = api.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    flush, close = api.FlushFileBuffers, api.CloseHandle
    flush.argtypes = close.argtypes = (wintypes.HANDLE,)
    flush.restype = close.restype = wintypes.BOOL
    handle = create(str(directory), 0x40000000, 7, None, 3, 0x02000000, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise OSError("directory sync unavailable")
    try:
        if not flush(handle):
            raise OSError("directory sync unavailable")
    finally:
        close(handle)


def _sync_directory(directory):
    if os.name == "nt":
        _windows_sync_directory(directory)
    else:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))  # encoding=None: raw directory descriptor.
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@dataclass(frozen=True)
class WritePlan:
    path: Path
    temporary: Path
    text: str
    expected: bytes | None


def _plan(path, text, expected):
    temporary = path.with_name(path.stem + ".txn-" + uuid.uuid4().hex + path.suffix)
    private_output_guard(path)
    private_output_guard(temporary)
    return WritePlan(path, temporary, text, expected)


def _apply(plan, *, before_publish=None):
    data = plan.text.encode("utf-8")
    if _optional_bytes(plan.path) != plan.expected:
        _error("GOLD_OUTPUT_CHANGED")
    if plan.expected == data:
        if before_publish is not None:
            before_publish()
        return False
    parent = plan.path.parent
    existing = parent
    while not existing.exists():
        existing = existing.parent
    created = False
    try:
        _sync_directory(existing)  # Check durability capability before any write.
        parent.mkdir(parents=True, exist_ok=True)
        with plan.temporary.open("x", encoding="utf-8", newline="") as stream:
            created = True
            stream.write(plan.text)
            stream.flush()
            os.fsync(stream.fileno())
        if before_publish is not None:
            before_publish()
        if _optional_bytes(plan.path) != plan.expected:
            _error("GOLD_OUTPUT_CHANGED")
        os.replace(plan.temporary, plan.path)
        _sync_directory(parent)
    except OSError:
        _error("GOLD_WRITE_FAILED")
    finally:
        if created:
            plan.temporary.unlink(missing_ok=True)
    return True


def _obs_to_witness(obs, f1_rule=None, f1_flag="none"):
    """Canonical observer witness tuple for final publication fence (B4/R9)."""
    from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs
    OCV = "yo-observation/1"
    if isinstance(obs, RESTORED_obs):
        return ("RESTORED", obs.form, obs.indices, obs.fp, f1_rule, f1_flag, OCV)
    if isinstance(obs, NONE_obs):
        return ("NONE", f1_rule, f1_flag, OCV)
    return ("UNSUPPORTED", f1_rule, f1_flag, OCV)  # fail-closed: UNSUPPORTED_obs + unknown types


def _score_publication_fence(context, config, record, obs_witness, by_key, gold_before, yo_data_before, sample_path):
    """B4/R9: re-validate observation inputs and per-key witness at true publication boundary.

    Fires inside _apply for both no-op (existing==result) and atomic rename paths.
    Re-checks inventory/sample freshness, norm/map/prep content digests and exact per-key
    observation witness; also re-checks gold/YO authority bytes as belt-and-suspenders.
    """
    _assert_current(context, config)
    _verify_sample(record, sample_path)
    _verify_selection_fresh(record, context, config)
    from audiobook.stress_yo_observer import (compute_norm_digest, compute_yo_map_digest,
                                               compute_prep_config_digest)
    current_map = _load_yo_map(config)
    current_inputs = {
        "norm_content_sha256": compute_norm_digest(paths.TEXT),
        "yo_map_sha256": compute_yo_map_digest(current_map),
        "prep_config_sha256": compute_prep_config_digest(config),
    }
    if record.get("observation_inputs") != current_inputs:
        _error("SAMPLE_STALE")
    for key, expected in obs_witness.items():
        occ = by_key.get(key)
        if occ is None:
            _error("SAMPLE_STALE")
        fresh = _yo_observe_key(occ, context.sources, config)
        fresh_witness = _obs_to_witness(fresh, occ.f1_rule, occ.f1_flag)
        if fresh_witness[0] == "UNSUPPORTED":
            _error("YO_OBSERVER_UNSUPPORTED")
        if fresh_witness != expected:
            _error("SAMPLE_STALE")
    if _optional_bytes(paths.TEXT / "stress_gold.tsv") != gold_before:
        _error("GOLD_OUTPUT_CHANGED")
    if _optional_bytes(_yo_path()) != yo_data_before:
        _error("YO_OUTPUT_CHANGED")


def _sample_path(record):
    return paths.OUT / "stress" / "eval" / "sample" / (record["sample_fp"][:16] + ".json")


def _verify_sample(record, path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    try:
        stored = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, ValueError, UnicodeError):
        _error("SAMPLE_INVALID")
    if _canonical(stored) != _canonical(record):
        _error("SAMPLE_INVALID")


def sample(config):
    lock = acquire_eval_lock()
    try:
        context = _load_context(config)
        selection = _selection(context, config)
        gold = paths.TEXT / "stress_gold.tsv"
        archive = paths.TEXT / "stress_gold.archive.tsv"
        ledger, gold_before = _read_ledger(gold)
        state = inspect_ledger(ledger, context)
        by_key = {row.source_key: row for row in context.rows}
        requested = [_todo_row(by_key[key], context.sources) for key in selection.record["keys"] if key not in state.active]
        record_path = _sample_path_v2(selection.record["sample_fp"])
        record_before = _optional_bytes(record_path)
        if record_before is not None:
            _verify_sample(selection.record, record_path)
        todo_path = _todo_path_v2(selection.record["sample_fp"])
        _check_todo_v2(todo_path, requested, list(state.active.values()))
        plans = [_plan(record_path, _canonical(selection.record).decode("utf-8") + "\n", record_before),
                 _plan(todo_path, serialize_gold(requested, allow_blank=True), _optional_bytes(todo_path))]
        if gold_before is None:
            plans.append(_plan(gold, serialize_gold([]), None))
        # Archive is derived and independently replaceable; never an input to merge.
        plans.append(_plan(archive, serialize_gold(state.stale), _optional_bytes(archive)))
        _assert_current(context, config)
        if _optional_bytes(gold) != gold_before:
            _error("GOLD_OUTPUT_CHANGED")
        for plan in plans:
            _apply(plan)
        return {"sample_fp": selection.record["sample_fp"], "strata": selection.record["strata"],
                "selected": len(selection.record["keys"]), "todo": len(requested),
                "one_vowel_aligned": selection.one_vowel_aligned, "duplicates": state.duplicates}
    finally:
        release_eval_lock(lock)


def merge(config, incoming: Path, sample_path: Path | None = None):
    lock = acquire_eval_lock()
    try:
        context = _load_context(config)
        selection, _ = _load_saved_selection(context, config, sample_path)
        gold = paths.TEXT / "stress_gold.tsv"
        archive = paths.TEXT / "stress_gold.archive.tsv"
        if incoming.resolve() == archive.resolve():
            _error("GOLD_ARCHIVE_NOT_AUTHORITATIVE")
        ledger, gold_before = _read_ledger(gold)
        state = inspect_ledger(ledger, context)
        try:
            batch = parse_gold(incoming.read_text(encoding="utf-8"), allow_blank=True)
        except (OSError, UnicodeError):
            _error("GOLD_INPUT_INVALID")
        selected = set(selection.record["keys"])
        by_key = {row.source_key: row for row in context.rows}
        additions = {}
        skipped = blank = 0
        for row in batch:
            key = row["source_key"]
            if key not in selected:
                _error("GOLD_UNEXPECTED_KEY")
            expected = _todo_row(by_key[key], context.sources)
            if any(row[name] != expected[name] for name in GOLD_FIELDS[:6]):
                _error("GOLD_STALE_INPUT")
            if all(not row[field] for field in LABEL_FIELDS):
                blank += 1
                continue
            row = validate_gold(row, by_key[key])
            existing = additions.get(key, state.active.get(key))
            if existing is not None:
                if (existing["gold_vowel"], existing["yo_correct"]) != (row["gold_vowel"], row["yo_correct"]):
                    _error("GOLD_ACTIVE_CONFLICT")
                skipped += 1
            else:
                additions[key] = row
        updated = ledger + list(additions.values())
        updated_state = inspect_ledger(updated, context)
        plans = [_plan(gold, serialize_gold(updated), gold_before),
                 _plan(archive, serialize_gold(updated_state.stale), _optional_bytes(archive))]
        _assert_current(context, config)
        for plan in plans:
            _apply(plan)
        # Owner todo is not modified here: safe retirement policy is pending
        # architect decision (Issue #17). The versioned todo persists until
        # sample() regenerates it on the next run.
        return {"added": len(additions), "skipped": skipped, "unlabeled": blank,
                "active": len(updated_state.active), "stale": len(updated_state.stale),
                "duplicates": updated_state.duplicates}
    finally:
        release_eval_lock(lock)


def _accepted_vowels(gold, occ):
    """Translate validated human stress labels; never infer truth from F6."""
    label = validate_gold(gold, occ)["gold_vowel"]
    if label in ("ambiguous", "unknown_name"):
        return frozenset()
    if label == "yo":
        spelling = gold["form_source"].lower()
        if spelling.count("ё") != 1:
            spelling = occ.form_synth.lower()
        return frozenset([vowel_count(spelling[:spelling.index("ё")])])
    return frozenset(map(int, label.removeprefix("variants:").split("|")))


def _present(value):
    """Round report values only, after all decisions use full precision."""
    if isinstance(value, dict):
        return {key: _present(item) for key, item in value.items()}
    if type(value) is float:
        return round(value, 4)
    return value


def _yo_observe_key(occ, sources, config):
    """Call stress_yo_observer.observe_su for one occurrence (monkeypatchable in tests).

    Reads exact production SU fragment from chunk manifest at
    paths.OUT/sections/{section}/manifest.jsonl. UNSUPPORTED on any missing or
    ambiguous data; never skips — UNSUPPORTED → ERROR in _yo_check.
    """
    from audiobook import leadin
    from audiobook.pronounce import load_table
    from audiobook.stress_yo_observer import observe_su, UNSUPPORTED_obs
    resolved = sources.resolve(occ.source_key)
    if resolved is None:
        return UNSUPPORTED_obs("SOURCE_NOT_FOUND")
    identity, _, _ = resolved
    if occ.su_chunk_id is None:
        return UNSUPPORTED_obs("SU_ALIGNMENT_MISSING")
    manifest_path = paths.OUT / "sections" / occ.section / "manifest.jsonl"
    raw = -1
    try:
        raw = _open_eval_file(manifest_path)
        with os.fdopen(raw, "r", encoding="utf-8") as manifest:
            raw = -1  # Ownership transferred; close on read/decode errors too.
            manifest_text = manifest.read()
    except (OSError, UnicodeError, NotImplementedError):
        return UNSUPPORTED_obs("MANIFEST_UNAVAILABLE")
    finally:
        if raw >= 0:
            os.close(raw)
    try:
        rows = [json.loads(line) for line in manifest_text.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        return UNSUPPORTED_obs("MANIFEST_UNAVAILABLE")
    row = next((r for r in rows if r.get("id") == occ.su_chunk_id), None)
    if row is None:
        return UNSUPPORTED_obs("MANIFEST_UNAVAILABLE")
    if occ.su_fragment is None:
        from audiobook.synth import row_leadin
        raw_text = row["text"]
        phrase = row_leadin(row)
        open_end = row.get("open_end", False)
    else:
        from audiobook.synth import chunk_fragments
        try:
            frags = chunk_fragments(row["text"], config)
        except Exception:
            return UNSUPPORTED_obs("MANIFEST_UNAVAILABLE")
        fi = occ.su_fragment
        if fi >= len(frags):
            return UNSUPPORTED_obs("FRAGMENT_ORDINAL_MISMATCH")
        frag_text, _pause, is_enum = frags[fi]
        raw_text = frag_text.rstrip("?") if is_enum and frag_text.endswith("?") else frag_text
        phrase = leadin.AUTO
        open_end = False
    yo_map = _load_yo_map(config)
    table = load_table(paths.TEXT / "pronounce.yaml")
    sentinel = (config.get("model") or {}).get("sentinel", "")
    return observe_su(
        source_token=occ.form_source,
        raw_text=raw_text,
        token_idx=occ.su_token_index if occ.su_token_index is not None else 0,
        config=config or {},
        yo_map=yo_map, table=table, sentinel=sentinel,
        phrase=phrase, open_end=open_end,
        source_identity=identity,
    )


def _yo_check(keys, by_key, context, config, yo_data_before):
    """Count missing yo verdicts; return (yo_missing, verdict_by_fp, obs_by_key).

    Missing journal treated as empty. UNSUPPORTED observation raises ERROR.
    YO_EVALUABLE = RESTORED_obs ∧ ¬F1-excluded; verdict lookup by restoration_fp.
    """
    from audiobook.stress_yo_observer import UNSUPPORTED_obs, RESTORED_obs
    try:
        yo_entries = parse_yo_evidence(yo_data_before.decode("utf-8")) if yo_data_before is not None else []
    except UnicodeError:
        _error("YO_EVIDENCE_INVALID")
    # Historical versions authenticate themselves, independently of current sources.
    # F1 fix: build verdict_by_fp with conflict detection (loop, not dict comprehension).
    verdict_by_fp: dict = {}
    for entry in yo_entries:
        fp = entry["restoration_fp"]
        if fp in verdict_by_fp and verdict_by_fp[fp]["yo_correct"] != entry["yo_correct"]:
            _error("YO_EVIDENCE_CONFLICT")
        verdict_by_fp[fp] = entry
    obs_by_key: dict = {}
    yo_missing = 0
    for key in keys:
        occ = by_key.get(key)
        if occ is None:
            continue
        obs = _yo_observe_key(occ, context.sources, config)
        obs_by_key[key] = obs
        if isinstance(obs, UNSUPPORTED_obs):
            _error("YO_OBSERVER_UNSUPPORTED")  # Fail closed: never silently skip.
        if not isinstance(obs, RESTORED_obs):
            continue
        if occ.f1_rule is not None or occ.f1_flag != "none":
            continue
        if obs.fp not in verdict_by_fp:
            yo_missing += 1
    return yo_missing, verdict_by_fp, obs_by_key


def score(config):
    """Validate the current sample and ledger, then publish only aggregates.

    Incomplete samples expose counts, with no partial metrics or passing gates.
    Gold and its archive are read-only; the archive is never an input.
    Both authoritative ledger digests are pinned (T41/ADR §5).
    """
    from audiobook.stress_metrics import Observation, calculate_metrics
    from audiobook.stress_yo_observer import (RESTORED_obs, compute_norm_digest,
                                               compute_yo_map_digest, compute_prep_config_digest)
    lock = acquire_eval_lock()
    try:
        context = _load_context(config)
        selection, sample_path = _load_saved_selection(context, config)
        record = selection.record
        # B4: reject sample/2 whose observation inputs no longer match current state.
        _yo_map_cur = _load_yo_map(config)
        if record.get("observation_inputs") != {
            "norm_content_sha256": compute_norm_digest(paths.TEXT),
            "yo_map_sha256": compute_yo_map_digest(_yo_map_cur),
            "prep_config_sha256": compute_prep_config_digest(config),
        }:
            _error("SAMPLE_STALE")
        # B5: verify eligible assignment unchanged (observer behavior may have changed).
        _verify_selection_fresh(record, context, config)
        gold_path = paths.TEXT / "stress_gold.tsv"
        ledger, gold_before = _read_ledger(gold_path)
        yo_path = _yo_path()
        yo_data_before = _optional_bytes(yo_path)
        state = inspect_ledger(ledger, context)
        keys = record["keys"]
        by_key = {occ.source_key: occ for occ in context.rows}
        missing = sum(key not in state.active for key in keys)
        # T38/T41: call observer per key; absent journal = empty; UNSUPPORTED → ERROR (ADR §4.4)
        yo_missing, verdict_by_fp, obs_by_key = _yo_check(keys, by_key, context, config, yo_data_before)
        obs_witness = {key: _obs_to_witness(obs, by_key[key].f1_rule, by_key[key].f1_flag)
                       for key, obs in obs_by_key.items()}
        counts = {"selected": len(keys), "active_labels": len(keys) - missing,
                  "missing_labels": missing, "missing_yo_verdicts": yo_missing,
                  "stale_gold": len(state.stale),
                  "duplicates": state.duplicates, "one_vowel_aligned": selection.one_vowel_aligned,
                  "by_stratum": {name: {"N": record["strata"][name]["N"],
                                        "selected": record["strata"][name]["n"]} for name, _ in STRATA}}
        result = {
            "schema": "stress-score/2",
            "source_fp": context.source_fp, "analysis_fp": context.analysis_fp,
            "sample_fp": record["sample_fp"],
            "eligible_assignment_sha256": record["eligible_assignment_sha256"],
            "selected_by_stratum_sha256": record["selected_by_stratum_sha256"],
            "inventory_generation_fp": hashlib.sha256(context.generation).hexdigest(),
            "observation_contract_version": "yo-observation/1",
            "norm_content_sha256": record["observation_inputs"]["norm_content_sha256"],
            "yo_map_sha256": record["observation_inputs"]["yo_map_sha256"],
            "prep_config_sha256": record["observation_inputs"]["prep_config_sha256"],
            "gold_sha256": hashlib.sha256(gold_before).hexdigest() if gold_before is not None else None,
            "yo_evidence_sha256": hashlib.sha256(yo_data_before).hexdigest() if yo_data_before is not None else None,
            "counts": counts, "metrics": None, "wilson": None, "gates": None,
            "status": "INCOMPLETE" if (missing or yo_missing) else "COMPLETE",
        }
        if not (missing or yo_missing):
            observations = []
            for key in keys:
                occ = by_key[key]
                gold = state.active[key]
                accepted = _accepted_vowels(gold, occ)
                resolved = occ.f6_status == "resolved"
                obs = obs_by_key.get(key)
                yo_evaluable = (isinstance(obs, RESTORED_obs)
                                and occ.f1_rule is None and occ.f1_flag == "none")
                if yo_evaluable and obs.fp in verdict_by_fp:
                    yo_correct_val = verdict_by_fp[obs.fp]["yo_correct"]
                else:
                    yo_correct_val = "na"
                observations.append(Observation(
                    stratum=selection.strata_by_key[key],
                    eligible=occ.alignment_status == "aligned" and vowel_count(occ.form_analysis) >= 2,
                    resolved=resolved, usable_gold=bool(accepted),
                    correct=resolved and bool(accepted) and occ.f6_vowel in accepted,
                    yo_changed=yo_evaluable, yo_correct=yo_correct_val,
                    covered_by_override=occ.status == "covered_by_override"))
            calculated = calculate_metrics(observations, {name: record["strata"][name]["N"] for name, _ in STRATA})
            counts.update(calculated["counts"])
            counts["usable_gold"] = sum(row.usable_gold for row in observations)
            metrics = calculated["metrics"]
            bounds = lambda rates: {name: {bound: rate[bound] for bound in ("lower", "upper")}
                                    for name, rate in rates.items()}
            result.update(metrics=_present(metrics), gates=calculated["gates"], wilson=_present({
                "overall": bounds(metrics["overall"]),
                "by_stratum": {name: bounds(rates) for name, rates in metrics["by_stratum"].items()}}))
        target = paths.OUT / "stress" / "eval" / "score" / ("s2-" + record["sample_fp"][:16] + ".json")
        plan = _plan(target, _canonical(result).decode("utf-8") + "\n", _optional_bytes(target))
        _assert_current(context, config)
        _verify_sample(record, sample_path)
        if _optional_bytes(gold_path) != gold_before:
            _error("GOLD_OUTPUT_CHANGED")
        if _optional_bytes(yo_path) != yo_data_before:  # T41: dual ledger freshness
            _error("YO_OUTPUT_CHANGED")
        _apply(plan, before_publish=lambda: _score_publication_fence(
            context, config, record, obs_witness, by_key, gold_before, yo_data_before, sample_path))
        return result
    finally:
        release_eval_lock(lock)


# ---------------------------------------------------------------------------
# Source-only merge (C1 compliant): no sample dependency
# ---------------------------------------------------------------------------

def merge_source(config, incoming: Path):
    """M1-M5 without sample validation. Any source-current key is eligible (C1)."""
    lock = acquire_eval_lock()
    try:
        context = _load_context(config)
        gold = paths.TEXT / "stress_gold.tsv"
        archive = paths.TEXT / "stress_gold.archive.tsv"
        if incoming.resolve() == archive.resolve():
            _error("GOLD_ARCHIVE_NOT_AUTHORITATIVE")
        ledger, gold_before = _read_ledger(gold)
        state = inspect_ledger(ledger, context)
        try:
            batch = parse_gold(incoming.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            _error("GOLD_INPUT_INVALID")
        by_key = {occ.source_key: occ for occ in context.rows}
        additions, skipped = {}, 0
        for row in batch:
            key = row["source_key"]
            expected = context.sources.resolve(key)
            if expected is None:
                _error("GOLD_UNEXPECTED_KEY")
            identity, _, _ = expected
            if any(row[name] != identity[name] for name in IDENTITY_FIELDS):
                _error("GOLD_STALE_INPUT")
            occ = by_key.get(key)
            row = validate_gold(row, occ, allow_na_yo=True)
            existing = additions.get(key, state.active.get(key))
            if existing is not None:
                if (existing["gold_vowel"], existing["yo_correct"]) != (row["gold_vowel"], row["yo_correct"]):
                    _error("GOLD_ACTIVE_CONFLICT")
                skipped += 1
            else:
                additions[key] = row
        updated = ledger + list(additions.values())
        updated_state = inspect_ledger(updated, context)
        plans = [_plan(gold, serialize_gold(updated), gold_before),
                 _plan(archive, serialize_gold(updated_state.stale), _optional_bytes(archive))]
        _assert_current(context, config)
        for plan in plans:
            _apply(plan)
        return {"added": len(additions), "skipped": skipped,
                "active": len(updated_state.active), "stale": len(updated_state.stale),
                "duplicates": updated_state.duplicates}
    finally:
        release_eval_lock(lock)


# ---------------------------------------------------------------------------
# YO evidence ledger (G1.4 §5 / M5): two independent authoritative ledgers
# ---------------------------------------------------------------------------

YO_FIELDS = (
    "schema_version", "source_key", "form_source", "unit_text_sha256",
    "unit_kind", "context_sha256", "restored_form_pre_respell",
    "restored_vowel_indices", "observation_contract_version",
    "restoration_fp", "norm_content_sha256", "yo_map_sha256",
    "prep_config_sha256", "yo_correct", "labeler", "date",
)

_YO_INDICES = re.compile(r"(?:0|[1-9][0-9]*)(?:\|(?:0|[1-9][0-9]*))*", re.ASCII)


def validate_yo_row(row: dict) -> dict:
    """Validate one YO evidence row; raise YO_EVIDENCE_INVALID / YO_OBSERVATION_UNSUPPORTED."""
    if type(row) is not dict or set(row) != set(YO_FIELDS) or any(not _safe_cell(row[n]) for n in YO_FIELDS):
        _error("YO_EVIDENCE_INVALID")
    if row["schema_version"] != "yo-evidence/1":
        _error("YO_EVIDENCE_INVALID")
    if row["observation_contract_version"] != "yo-observation/1":
        _error("YO_OBSERVATION_UNSUPPORTED")
    _split_key(row["source_key"])
    if not _WORD.fullmatch(row["form_source"]) or not row["unit_kind"]:
        _error("YO_EVIDENCE_INVALID")
    for hex_field in ("unit_text_sha256", "context_sha256", "restoration_fp",
                      "norm_content_sha256", "yo_map_sha256", "prep_config_sha256"):
        if not _HEX.fullmatch(row[hex_field]):
            _error("YO_EVIDENCE_INVALID")
    idx_str = row["restored_vowel_indices"]
    if not _YO_INDICES.fullmatch(idx_str):
        _error("YO_EVIDENCE_INVALID")
    parts = [int(p) for p in idx_str.split("|")]
    if parts != sorted(set(parts)):
        _error("YO_EVIDENCE_INVALID")
    if not _WORD.fullmatch(row["restored_form_pre_respell"]):
        _error("YO_EVIDENCE_INVALID")
    source = row["form_source"]
    candidate = row["restored_form_pre_respell"]
    if (unicodedata.normalize("NFC", source) != source
            or unicodedata.normalize("NFC", candidate) != candidate
            or len(source) != len(candidate)):
        _error("YO_EVIDENCE_INVALID")
    changed_indices = []
    vowel_ordinal = 0
    for original, restored in zip(source, candidate):
        if original != restored:
            if (original, restored) not in (("е", "ё"), ("Е", "Ё")):
                _error("YO_EVIDENCE_INVALID")
            changed_indices.append(vowel_ordinal)
        if original.lower() in _VOWELS:
            vowel_ordinal += 1
    if not changed_indices or changed_indices != parts:
        _error("YO_EVIDENCE_INVALID")
    from audiobook.stress_yo_observer import restoration_fp
    identity = {name: row[name] for name in IDENTITY_FIELDS}
    if restoration_fp(identity, candidate, parts) != row["restoration_fp"]:
        _error("YO_EVIDENCE_INVALID")
    if row["yo_correct"] not in ("y", "n"):
        _error("YO_EVIDENCE_INVALID")
    if not row["labeler"].strip():
        _error("YO_EVIDENCE_INVALID")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["date"]):
        _error("YO_EVIDENCE_INVALID")
    try:
        datetime.date.fromisoformat(row["date"])
    except ValueError:
        _error("YO_EVIDENCE_INVALID")
    return dict(row)


def parse_yo_evidence(text: str) -> list:
    if isinstance(text, str):
        text = text.replace("\r\n", "\n")
    if not isinstance(text, str) or not text.endswith("\n"):
        _error("YO_EVIDENCE_INVALID")
    lines = text[:-1].split("\n")
    if lines[0] != "\t".join(YO_FIELDS):
        _error("YO_EVIDENCE_INVALID")
    result = []
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) != len(YO_FIELDS):
            _error("YO_EVIDENCE_INVALID")
        result.append(validate_yo_row(dict(zip(YO_FIELDS, cells))))
    return result


def serialize_yo_evidence(rows: list) -> str:
    validated = [validate_yo_row(row) for row in rows]
    validated.sort(key=lambda row: tuple(row[n] for n in YO_FIELDS))
    return "\t".join(YO_FIELDS) + "\n" + "".join(
        "\t".join(row[n] for n in YO_FIELDS) + "\n" for row in validated
    )


def _yo_path() -> Path:
    return paths.TEXT / "stress_gold.yo_evidence.tsv"


def merge_yo(config, incoming: Path):
    """Append verified YO evidence; validates observation version and fp conflict (G1.4 §6.3)."""
    from audiobook.stress_yo_observer import restoration_fp as _rfp_check, RESTORED_obs
    lock = acquire_eval_lock()
    try:
        context = _load_context(config)
        by_key = {occ.source_key: occ for occ in context.rows}
        yo_path = _yo_path()
        yo_data = _optional_bytes(yo_path)
        try:
            existing = [] if yo_data is None else parse_yo_evidence(yo_data.decode("utf-8"))
        except UnicodeError:
            _error("YO_EVIDENCE_INVALID")
        existing_by_fp: dict[str, dict] = {}
        for row in existing:
            fp = row["restoration_fp"]
            if fp in existing_by_fp and existing_by_fp[fp]["yo_correct"] != row["yo_correct"]:
                _error("YO_EVIDENCE_CONFLICT")
            existing_by_fp[fp] = row
        try:
            batch = parse_yo_evidence(incoming.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            _error("YO_EVIDENCE_INVALID")
        additions: list[dict] = []
        for row in batch:
            key = row["source_key"]
            current = context.sources.resolve(key)
            if current is None:
                _error("YO_UNEXPECTED_KEY")
            identity, _, _ = current
            if any(row[name] != identity[name] for name in IDENTITY_FIELDS):
                _error("YO_STALE_INPUT")
            # Internal fp consistency check.
            indices = [int(p) for p in row["restored_vowel_indices"].split("|")]
            if _rfp_check(identity, row["restored_form_pre_respell"], indices) != row["restoration_fp"]:
                _error("YO_STALE_INPUT")
            # B3: freshness check — observer must still produce RESTORED_obs with matching fp.
            occ = by_key.get(key)
            if occ is None:
                _error("YO_STALE_INPUT")
            obs = _yo_observe_key(occ, context.sources, config)
            if not isinstance(obs, RESTORED_obs) or obs.fp != row["restoration_fp"]:
                _error("YO_STALE_INPUT")
            fp = row["restoration_fp"]
            if fp in existing_by_fp:
                if existing_by_fp[fp]["yo_correct"] != row["yo_correct"]:
                    _error("YO_EVIDENCE_CONFLICT")
                continue  # idempotent: same fp, same verdict
            additions.append(row)
            existing_by_fp[fp] = row
        updated = existing + additions
        plan = _plan(yo_path, serialize_yo_evidence(updated), yo_data)
        _assert_current(context, config)
        _apply(plan)
        return {"added": len(additions), "skipped": len(batch) - len(additions)}
    finally:
        release_eval_lock(lock)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stress-eval", description="Локальная выборка и журнал ручной разметки ударений")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sample", help="Создать детерминированную выборку и todo")
    commands.add_parser("score", help="Проверить разметку и сохранить агрегированную оценку")
    merge_parser = commands.add_parser("merge", help="Проверить и объединить ручную разметку")
    merge_parser.add_argument("file", type=Path, help="Локальный TSV с разметкой")
    merge_parser.add_argument("--sample", type=Path, help="Запись текущей выборки JSON")
    merge_src_parser = commands.add_parser("merge-source", help="Объединить разметку (source-only, без sample)")
    merge_src_parser.add_argument("file", type=Path, help="Локальный TSV с разметкой")
    merge_yo_parser = commands.add_parser("merge-yo", help="Добавить YO-свидетельства")
    merge_yo_parser.add_argument("file", type=Path, help="Локальный YO TSV")
    commands.add_parser("audit-archive", help="Проверить совместимость архива с gold (только чтение)")
    args = parser.parse_args(argv)
    from audiobook.__main__ import load_config
    try:
        config = load_config()
        if args.command == "sample":
            result = sample(config)
        elif args.command == "score":
            result = score(config)
        elif args.command == "merge-source":
            result = merge_source(config, args.file)
        elif args.command == "merge-yo":
            result = merge_yo(config, args.file)
        elif args.command == "audit-archive":
            audit = audit_archive_compatibility(config)
            displayed = {"status": audit.status, "code": audit.code,
                         "gold_rows": audit.gold_rows, "archive_rows": audit.archive_rows,
                         "archive_only_rows": audit.archive_only_rows,
                         "excess_duplicates": audit.excess_duplicates,
                         "archive_missing": audit.archive_missing}
            print("stress-eval: " + json.dumps(displayed, ensure_ascii=False, sort_keys=True))
            if audit.status == "ERROR":
                return 1
            return 3 if audit.status == "BLOCKED" else 0
        else:
            result = merge(config, args.file, args.sample)
    except (AnnotationError, OSError, ValueError) as error:
        code = error.code if isinstance(error, AnnotationError) else "EVALUATION_INPUT_ERROR"
        print("stress-eval: ERROR (ошибка " + code + ")")
        return 1
    displayed = ({key: result[key] for key in ("status", "counts", "gates")}
                 if args.command == "score" else result)
    print("stress-eval: " + json.dumps(displayed, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("status") == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
