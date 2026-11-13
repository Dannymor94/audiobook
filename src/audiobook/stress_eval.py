"""Deterministic local sampling and versioned human annotation transactions.

The current inventory is read only through its validated v5 reader. Gold is an
evaluation ledger; nothing here changes synthesis or supplies machine labels.
Statistical scoring belongs to the separately confirmed integration contract.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
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


def _selection(context):
    return select_sample(context.rows, context.source_fp, context.analysis_fp,
                         homographs=context.homographs, names=context.names)


def _assert_current(context, config):
    fresh = _load_context(config)
    if (fresh.generation, fresh.source_fp, fresh.analysis_fp) != (context.generation, context.source_fp, context.analysis_fp):
        _error("INVENTORY_CHANGED")


def _safe_cell(value):
    return (type(value) is str and not any(unicodedata.category(c) in ("Cc", "Cs", "Zl", "Zp") for c in value))


def validate_gold(row, occ=None, *, allow_blank=False, historical=False):
    """Validate wire grammar; apply current ё evidence only to active versions.

    A stale historical 'yo' label may refer to its old, unstored synth spelling.
    Retain it without guessing its position; only a current valid row can score.
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
    if occ is not None and yo_changed(occ) and row["yo_correct"] not in ("y", "n"):
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
    if len(set(indices)) != len(indices) or any(index >= vowel_count(row["form_source"]) for index in indices):
        _error("GOLD_INVALID")
    result["gold_vowel"] = "variants:" + "|".join(map(str, sorted(indices))) if label.startswith("variants:") else label
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


def inspect_ledger(rows, context):
    by_key = {row.source_key: row for row in context.rows}
    active, stale = {}, []
    duplicates = 0
    for raw in rows:
        row = validate_gold(raw, historical=True)
        current = context.sources.resolve(row["source_key"])
        if current is None or any(row[name] != current[0][name] for name in IDENTITY_FIELDS):
            stale.append(row)
            continue
        occ = by_key.get(row["source_key"])
        usable_context = occ is not None and occ.alignment_status == "aligned" and vowel_count(occ.form_analysis) >= 2
        row = validate_gold(row, occ if usable_context else None, historical=not usable_context)
        key = row["source_key"]
        if key in active:
            if (active[key]["gold_vowel"], active[key]["yo_correct"]) != (row["gold_vowel"], row["yo_correct"]):
                _error("GOLD_ACTIVE_CONFLICT")
            duplicates += 1
            if tuple(row[n] for n in GOLD_FIELDS) < tuple(active[key][n] for n in GOLD_FIELDS):
                active[key] = row
        else:
            active[key] = row
    return GoldState(active, tuple(stale), duplicates)


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


def _apply(plan):
    data = plan.text.encode("utf-8")
    if _optional_bytes(plan.path) != plan.expected:
        _error("GOLD_OUTPUT_CHANGED")
    if plan.expected == data:
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
    context = _load_context(config)
    selection = _selection(context)
    gold = paths.TEXT / "stress_gold.tsv"
    archive = paths.TEXT / "stress_gold.archive.tsv"
    todo = paths.TEXT / "stress_gold.todo.tsv"
    ledger, gold_before = _read_ledger(gold)
    state = inspect_ledger(ledger, context)
    todo_before = _optional_bytes(todo)
    if todo_before is not None:
        try:
            existing_todo = parse_gold(todo_before.decode("utf-8"), allow_blank=True)
        except UnicodeError:
            _error("GOLD_INVALID")
        saved = {tuple(row[name] for name in IDENTITY_FIELDS) + (row["gold_vowel"], row["yo_correct"])
                 for row in ledger}
        for row in existing_todo:
            if any(row[field] for field in LABEL_FIELDS):
                signature = tuple(row[name] for name in IDENTITY_FIELDS) + (row["gold_vowel"], row["yo_correct"])
                if signature not in saved:
                    _error("TODO_HAS_UNMERGED_LABELS")
    by_key = {row.source_key: row for row in context.rows}
    requested = [_todo_row(by_key[key], context.sources) for key in selection.record["keys"] if key not in state.active]
    record_path = _sample_path(selection.record)
    record_before = _optional_bytes(record_path)
    if record_before is not None:
        _verify_sample(selection.record, record_path)
    plans = [_plan(record_path, _canonical(selection.record).decode("utf-8") + "\n", record_before),
             _plan(todo, serialize_gold(requested, allow_blank=True), todo_before)]
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


def merge(config, incoming: Path, sample_path: Path | None = None):
    context = _load_context(config)
    selection = _selection(context)
    _verify_sample(selection.record, sample_path if sample_path is not None else _sample_path(selection.record))
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
    return {"added": len(additions), "skipped": skipped, "unlabeled": blank,
            "active": len(updated_state.active), "stale": len(updated_state.stale),
            "duplicates": updated_state.duplicates}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stress-eval", description="Локальная выборка и журнал ручной разметки ударений")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sample", help="Создать детерминированную выборку и todo")
    merge_parser = commands.add_parser("merge", help="Проверить и объединить ручную разметку")
    merge_parser.add_argument("file", type=Path, help="Локальный TSV с разметкой")
    merge_parser.add_argument("--sample", type=Path, help="Запись текущей выборки JSON")
    args = parser.parse_args(argv)
    from audiobook.__main__ import load_config
    try:
        result = sample(load_config()) if args.command == "sample" else merge(load_config(), args.file, args.sample)
    except (AnnotationError, OSError, ValueError) as error:
        code = error.code if isinstance(error, AnnotationError) else "EVALUATION_INPUT_ERROR"
        print("stress-eval: ошибка " + code)
        return 1
    print("stress-eval: " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
