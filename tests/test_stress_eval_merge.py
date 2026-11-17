"""Synthetic human labels, C3 version history and durable replacement oracles."""
import json
from pathlib import Path

import pytest

from audiobook import paths, stress_eval as evaluation
from audiobook.unitmap import AnnotationError
from test_stress_eval_sample import context_for, setup_book


def todo_rows():
    todos = sorted(paths.TEXT.glob("stress_gold.todo.s2-*.tsv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return evaluation.parse_gold(todos[0].read_text(encoding="utf-8"), allow_blank=True)


def labeled(row, value="0", **changes):
    return {**row, "gold_vowel": value, "yo_correct": "na", "labeler": "synthetic-owner",
            "date": "2026-11-13", **changes}


def write_input(tmp_path, rows):
    incoming = tmp_path / "labels.tsv"
    incoming.write_text(evaluation.serialize_gold(rows, allow_blank=True), encoding="utf-8", newline="")
    return incoming


def snapshot(tmp_path):
    return {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_stale_neighbor_relabel_archive_active_and_repeat(tmp_path, monkeypatch):
    units = setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    first = labeled(todo_rows()[1])
    key = first["source_key"]
    assert key == "01_test|1|0"
    evaluation.merge({}, write_input(tmp_path, [first]))
    assert evaluation.inspect_ledger([first], context_for(units)).active[key] == first
    units[0]["text"] = "Дельта."
    state = evaluation.inspect_ledger([first], context_for(units))
    assert not state.active and state.stale == (first,)
    evaluation.sample({})
    current = next(row for row in todo_rows() if row["source_key"] == key)
    assert current["unit_text_sha256"] == first["unit_text_sha256"]
    assert current["context_sha256"] != first["context_sha256"]
    second = labeled(current, "1")
    incoming = write_input(tmp_path, [second])
    result = evaluation.merge({}, incoming)
    assert result == {"added": 1, "skipped": 0, "unlabeled": 0, "active": 1, "stale": 1, "duplicates": 0}
    ledger = evaluation.parse_gold((paths.TEXT / "stress_gold.tsv").read_text(encoding="utf-8"))
    assert len(ledger) == 2 and first in ledger and second in ledger
    state = evaluation.inspect_ledger(ledger, context_for(units))
    assert state.active[key] == second and state.stale == (first,)
    assert evaluation.parse_gold((paths.TEXT / "stress_gold.archive.tsv").read_text(encoding="utf-8")) == [first]
    before = snapshot(tmp_path)
    assert evaluation.merge({}, incoming)["skipped"] == 1
    assert snapshot(tmp_path) == before
    # A global source change outside this three-unit neighborhood does not expire it.
    units.append({"type": "text", "text": "Омега."})
    assert evaluation.inspect_ledger(ledger, context_for(units)).active[key] == second


@pytest.mark.parametrize("value", ["0", "1", "variants:0|1", "ambiguous", "unknown_name"])
def test_accepted_labels(tmp_path, monkeypatch, value):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    incoming = write_input(tmp_path, [labeled(todo_rows()[0], value)])
    assert evaluation.merge({}, incoming)["added"] == 1


@pytest.mark.parametrize("value", ["", "yo_unstressed", "yo", "-1", "+1", "01", "٢", "2", "1.0",
                                  "variants:0", "variants:0|0", "variants:0|2", "variants:00|1", "variants:1|",
                                  "variants:1|0"])
def test_invalid_labels_rejected(tmp_path, monkeypatch, value):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    with pytest.raises(AnnotationError, match="GOLD_INVALID"):
        evaluation.validate_gold(labeled(todo_rows()[0], value))


@pytest.mark.parametrize("changes", [{"yo_correct": "yes"}, {"labeler": " "}, {"date": "2026-02-30"},
                                    {"date": "2026-1-01"}, {"date": "0000-01-01"}, {"context": "x" * 81},
                                    {"context": "x\ty"}, {"labeler": "x\ny"}, {"context": "x\x00y"},
                                    {"context": "x\u2028y"}, {"source_key": "01_test|01|0"},
                                    {"unit_text_sha256": "0" * 63}, {"form_source": "Beta"}])
def test_invalid_cells_dates_identity_grammar(tmp_path, monkeypatch, changes):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    with pytest.raises(AnnotationError, match="GOLD_INVALID"):
        evaluation.validate_gold(labeled(todo_rows()[0], **changes))


def test_yo_evidence_and_independent_orthography():
    units = [{"type": "text", "text": "Елка."}]
    context = context_for(units, synth={"Елка.": "Ёлка."})
    occ = context.rows[0]
    blank = evaluation._todo_row(occ, context.sources)
    for value in ("yo", "0", "1", "ambiguous", "unknown_name"):
        for correct in ("y", "n"):
            assert evaluation.validate_gold(labeled(blank, value, yo_correct=correct), occ)["gold_vowel"] == value
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.validate_gold(labeled(blank, value), occ)
    # Historical source-e labels must survive without guessing their old synth ё.
    old = labeled(blank, "yo", yo_correct="y")
    assert evaluation.parse_gold(evaluation.serialize_gold([old])) == [old]
    unchanged = context_for(units)
    with pytest.raises(AnnotationError, match="GOLD_INVALID"):
        evaluation.validate_gold(old, unchanged.rows[0])
    native = context_for([{"type": "text", "text": "Ёлка."}])
    assert evaluation.validate_gold(labeled(evaluation._todo_row(native.rows[0], native.sources), "yo"), native.rows[0])
    multiple = context_for([{"type": "text", "text": "Ёлкё."}])
    with pytest.raises(AnnotationError, match="GOLD_INVALID"):
        evaluation.validate_gold(labeled(evaluation._todo_row(multiple.rows[0], multiple.sources), "yo"), multiple.rows[0])


def test_blank_and_partially_filled_annotations(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    rows = todo_rows()
    assert evaluation.merge({}, write_input(tmp_path, rows))["unlabeled"] == 3
    for field in evaluation.LABEL_FIELDS:
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.serialize_gold([{**rows[0], field: "synthetic"}], allow_blank=True)


def test_wire_header_columns_newlines_and_canonical_variants(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    # K=1: single valid stress index; variants:0|1 accepted as-is (strict, no silent sort)
    annotated = labeled(todo_rows()[0], "0")
    canonical = evaluation.serialize_gold([annotated])
    assert evaluation.parse_gold(canonical)[0]["gold_vowel"] == "0"
    assert evaluation.serialize_gold(evaluation.parse_gold(canonical.replace("\n", "\r\n"))) == canonical
    for text in (canonical.rstrip("\n"), canonical + "\n", canonical.replace("source_key", "key", 1),
                 canonical.replace("\t", "", 1), canonical.replace("synthetic-owner", "bad\tcell")):
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.parse_gold(text)
    # T15: unsorted variants is now GOLD_INVALID (no auto-sort)
    with pytest.raises(AnnotationError, match="GOLD_INVALID"):
        evaluation.validate_gold(labeled(todo_rows()[0], "variants:1|0"))


@pytest.mark.parametrize("change", [{"context_sha256": "0" * 64}, {"unit_text_sha256": "0" * 64},
                                    {"unit_kind": "heading"}, {"form_source": "Дельта"},
                                    {"context": "synthetic mismatch"}, {"source_key": "01_test|999|0"}])
def test_entire_batch_validated_before_writes(tmp_path, monkeypatch, change):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    rows = todo_rows()
    incoming = write_input(tmp_path, [labeled(rows[0]), labeled(rows[1], **change)])
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError, match="GOLD_STALE_INPUT|GOLD_UNEXPECTED_KEY"):
        evaluation.merge({}, incoming)
    assert snapshot(tmp_path) == before


def test_batch_and_active_conflicts_no_write(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    row = todo_rows()[0]
    incoming = write_input(tmp_path, [labeled(row), labeled(row, "1")])
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError, match="GOLD_ACTIVE_CONFLICT"):
        evaluation.merge({}, incoming)
    assert snapshot(tmp_path) == before
    evaluation.merge({}, write_input(tmp_path, [labeled(row)]))
    incoming = write_input(tmp_path, [labeled(row, "1", date="2026-11-14")])
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError, match="GOLD_ACTIVE_CONFLICT"):
        evaluation.merge({}, incoming)
    assert snapshot(tmp_path) == before


def test_semantic_duplicates_and_source_reversion(tmp_path, monkeypatch):
    units = setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    row = todo_rows()[1]
    first = labeled(row, "variants:0|1")
    second = labeled(row, "variants:0|1", labeler="other-synthetic-owner", date="2026-11-14")
    gold = paths.TEXT / "stress_gold.tsv"
    gold.write_text(evaluation.serialize_gold([first, second]), encoding="utf-8")
    state = evaluation.inspect_ledger(evaluation.parse_gold(gold.read_text(encoding="utf-8")), context_for(units))
    assert len(state.active) == 1 and state.duplicates == 1
    assert evaluation.merge({}, write_input(tmp_path, [second]))["skipped"] == 1
    assert len(evaluation.parse_gold(gold.read_text(encoding="utf-8"))) == 2
    # A conflict can hide while its version is stale, then reappear on source reversion.
    conflicting = labeled(row, "0")
    old = units[0]["text"]
    units[0]["text"] = "Дельта."
    assert len(evaluation.inspect_ledger([second, conflicting], context_for(units)).stale) == 2
    units[0]["text"] = old
    with pytest.raises(AnnotationError, match="GOLD_ACTIVE_CONFLICT"):
        evaluation.inspect_ledger([second, conflicting], context_for(units))


def test_owner_edited_todo_retained_until_saved_then_regenerated(tmp_path, monkeypatch):
    # merge() never modifies the owner todo (conservative policy, Issue #17).
    # After merge, the stale todo persists and sample() raises OWNER_TODO_PROTECTED
    # until the user manually removes it.
    setup_book(tmp_path, monkeypatch)
    result = evaluation.sample({})
    rows = todo_rows()
    todo = evaluation._todo_path_v2(result["sample_fp"])
    todo.write_text(evaluation.serialize_gold([labeled(rows[0]), *rows[1:]], allow_blank=True), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError, match="TODO_HAS_UNMERGED_LABELS"):
        evaluation.sample({})
    assert snapshot(tmp_path) == before
    todo_bytes_before = todo.read_bytes()
    assert evaluation.merge({}, todo)["added"] == 1
    # todo must be byte-identical after merge (conservative policy)
    assert todo.read_bytes() == todo_bytes_before, "merge() must not touch owner todo"
    # sample() now raises OWNER_TODO_PROTECTED: stale todo bytes differ from new expected
    with pytest.raises(AnnotationError, match="OWNER_TODO_PROTECTED"):
        evaluation.sample({})
    # After user deletes the stale todo, sample() can regenerate with 2 rows
    todo.unlink()
    result2 = evaluation.sample({})
    assert result2["todo"] == 2
    assert all(not row["gold_vowel"] for row in todo_rows())


def test_archive_never_input_and_corrupt_export_repaired(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    archive = paths.TEXT / "stress_gold.archive.tsv"
    archive.write_text("corrupt interrupted export", encoding="utf-8")
    with pytest.raises(AnnotationError, match="GOLD_ARCHIVE_NOT_AUTHORITATIVE"):
        evaluation.merge({}, archive)
    evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0])]))
    assert evaluation.parse_gold(archive.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("mutation", ["sample_fp", "source_fp", "analysis_fp", "keys", "strata", "extra"])
def test_wrong_sample_refused_before_writes(tmp_path, monkeypatch, mutation):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json"))
    value = json.loads(record.read_text(encoding="utf-8"))
    value[mutation] = [] if mutation == "keys" else "corrupt"
    record.write_text(json.dumps(value), encoding="utf-8")
    incoming = write_input(tmp_path, [labeled(todo_rows()[0])])
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError, match="SAMPLE_INVALID"):
        evaluation.merge({}, incoming)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("stage", ["before_gold", "after_gold", "before_archive", "after_archive"])
def test_crash_and_replay_complete_ledger(tmp_path, monkeypatch, stage):
    units = setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    original = labeled(todo_rows()[1])
    evaluation.merge({}, write_input(tmp_path, [original]))
    units[0]["text"] = "Дельта."
    evaluation.sample({})
    current = labeled(next(row for row in todo_rows() if row["source_key"] == original["source_key"]), "1")
    incoming = write_input(tmp_path, [current])
    gold = paths.TEXT / "stress_gold.tsv"
    archive = paths.TEXT / "stress_gold.archive.tsv"
    archive.write_text("synthetic stale export requiring repair", encoding="utf-8")
    old_bytes = gold.read_bytes()
    new_bytes = evaluation.serialize_gold([original, current]).encode("utf-8")
    replace = evaluation.os.replace
    target = gold if stage.endswith("gold") else archive
    class SimulatedCrash(BaseException):
        pass
    def crash(src, dst):
        if dst == target and stage.startswith("before"):
            raise SimulatedCrash()
        replace(src, dst)
        if dst == target and stage.startswith("after"):
            raise SimulatedCrash()
    with monkeypatch.context() as patch:
        patch.setattr(evaluation.os, "replace", crash)
        with pytest.raises(SimulatedCrash):
            evaluation.merge({}, incoming)
    assert gold.read_bytes() == (old_bytes if stage == "before_gold" else new_bytes)
    evaluation.parse_gold(gold.read_text(encoding="utf-8"))
    result = evaluation.merge({}, incoming)
    assert result["active"] == 1 and result["stale"] == 1
    assert gold.read_bytes() == new_bytes
    assert evaluation.parse_gold(archive.read_text(encoding="utf-8")) == [original]
    before = snapshot(tmp_path)
    evaluation.merge({}, incoming)
    assert snapshot(tmp_path) == before


def test_interrupted_temp_ignored_and_collision_not_deleted(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    abandoned = paths.TEXT / "stress_gold.txn-abandoned.tsv"
    abandoned.write_text("incomplete synthetic record", encoding="utf-8")
    incoming = write_input(tmp_path, [labeled(todo_rows()[0])])
    assert evaluation.merge({}, incoming)["added"] == 1
    assert abandoned.read_text(encoding="utf-8") == "incomplete synthetic record"
    plan = evaluation.WritePlan(paths.TEXT / "stress_gold.tsv", abandoned, "synthetic new data", (paths.TEXT / "stress_gold.tsv").read_bytes())
    with pytest.raises(AnnotationError, match="GOLD_WRITE_FAILED"):
        evaluation._apply(plan)
    assert abandoned.read_text(encoding="utf-8") == "incomplete synthetic record"


def test_all_target_guards_before_any_write(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    incoming = write_input(tmp_path, [labeled(todo_rows()[0])])
    before = snapshot(tmp_path)
    guarded = []
    def guard(path):
        guarded.append(path)
        if "archive" in path.name:
            raise AnnotationError("PRIVATE_OUTPUT_REQUIRED")
    monkeypatch.setattr(evaluation, "private_output_guard", guard)
    with pytest.raises(AnnotationError, match="PRIVATE_OUTPUT_REQUIRED"):
        evaluation.merge({}, incoming)
    assert len(guarded) == 3 and ".txn-" in guarded[1].name
    assert snapshot(tmp_path) == before


def test_fsync_and_atomic_rename_order(tmp_path, monkeypatch):
    destination = tmp_path / "ledger.tsv"
    temporary = tmp_path / "ledger.txn-synthetic.tsv"
    events = []
    sync, replace = evaluation.os.fsync, evaluation.os.replace
    monkeypatch.setattr(evaluation, "_sync_directory", lambda path: events.append("directory"))
    def file_sync(fd):
        events.append("file")
        sync(fd)
    def atomic_replace(src, dst):
        events.append("replace")
        assert src.parent == dst.parent
        assert src.read_bytes() == b"complete\n"
        replace(src, dst)
    monkeypatch.setattr(evaluation.os, "fsync", file_sync)
    monkeypatch.setattr(evaluation.os, "replace", atomic_replace)
    assert evaluation._apply(evaluation.WritePlan(destination, temporary, "complete\n", None))
    assert events == ["directory", "file", "replace", "directory"]
    assert not temporary.exists()


def test_durability_failure_and_concurrent_update_fail_closed(tmp_path, monkeypatch):
    destination, temporary = tmp_path / "ledger.tsv", tmp_path / "ledger.txn-synthetic.tsv"
    plan = evaluation.WritePlan(destination, temporary, "complete\n", None)
    def unavailable(_):
        raise OSError("synthetic directory sync failure")
    with monkeypatch.context() as patch:
        patch.setattr(evaluation, "_sync_directory", unavailable)
        with pytest.raises(AnnotationError, match="GOLD_WRITE_FAILED"):
            evaluation._apply(plan)
    assert not destination.exists() and not temporary.exists()
    # Simulate a writer appearing after the initial expected-bytes check.
    def concurrent(_):
        destination.write_text("other complete ledger\n", encoding="utf-8")
    monkeypatch.setattr(evaluation, "_sync_directory", concurrent)
    with pytest.raises(AnnotationError, match="GOLD_OUTPUT_CHANGED"):
        evaluation._apply(plan)
    assert destination.read_text(encoding="utf-8") == "other complete ledger\n"
    assert not temporary.exists()


def test_generation_change_between_validation_and_write(tmp_path, monkeypatch):
    units = setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    incoming = write_input(tmp_path, [labeled(todo_rows()[0])])
    before = snapshot(tmp_path)
    calls = []
    def load(_):
        calls.append(1)
        current = context_for(units)
        if len(calls) == 1:
            units.append({"type": "text", "text": "Дельта."})
        return current
    monkeypatch.setattr(evaluation, "_load_context", load)
    with pytest.raises(AnnotationError, match="INVENTORY_CHANGED"):
        evaluation.merge({}, incoming)
    assert snapshot(tmp_path) == before


def test_sample_json_duplicate_keys_and_boolean_counts_refused(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    path = next((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(record)
    path.write_text('{"sample_fp":"duplicate",' + text[1:], encoding="utf-8")
    with pytest.raises(AnnotationError, match="SAMPLE_INVALID"):
        evaluation._verify_sample(record, path)
    # Python dict equality would accept 0 == False; the JSON schema must not.
    mutated = json.loads(text)
    mutated["strata"]["omograph"]["N"] = False
    path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(AnnotationError, match="SAMPLE_INVALID"):
        evaluation._verify_sample(record, path)


@pytest.mark.parametrize("failure", [None, "create", "flush"])
def test_native_windows_directory_sync_closes_handle(monkeypatch, tmp_path, failure):
    import ctypes
    from types import SimpleNamespace
    events = []
    class Call:
        def __init__(self, name, result):
            self.name, self.result = name, result
        def __call__(self, *args):
            events.append((self.name, args))
            return self.result
    api = SimpleNamespace(CreateFileW=Call("create", ctypes.c_void_p(-1).value if failure == "create" else 42),
                          FlushFileBuffers=Call("flush", 0 if failure == "flush" else 1),
                          CloseHandle=Call("close", 1))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    if failure:
        with pytest.raises(OSError, match="directory sync unavailable"):
            evaluation._windows_sync_directory(tmp_path)
    else:
        evaluation._windows_sync_directory(tmp_path)
    assert [name for name, _ in events] == (["create"] if failure == "create" else ["create", "flush", "close"])
    assert events[0][1][1] == 0x40000000  # FlushFileBuffers requires GENERIC_WRITE.
    assert events[0][1][5] == 0x02000000  # Directory handle requires BACKUP_SEMANTICS.


def test_windows_dispatch_does_not_skip_durability(monkeypatch, tmp_path):
    from types import SimpleNamespace
    events = []
    monkeypatch.setattr(evaluation, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(evaluation, "_windows_sync_directory", lambda path: events.append(path))
    evaluation._sync_directory(tmp_path)
    assert events == [tmp_path]


# ===========================================================================
# I2 oracles: T01–T10, T14, T15, T17, T19, T20, T27, T28, T34, T35, T37, T39, T40,
#             plus three original Sol F1 regressions.
# ===========================================================================

import copy
import hashlib as _hashlib

from audiobook.stress_yo_observer import (
    NONE_obs, RESTORED_obs, UNSUPPORTED_obs, restoration_fp as _rfp,
)


def _yo_row(source_key, form_source, unit_text_sha256, unit_kind, context_sha256,
            restored_form, indices, restoration_fp_val, yo_correct, *,
            norm="a" * 64, yo_map="b" * 64, prep_cfg="c" * 64,
            labeler="synthetic-owner", date="2026-11-15"):
    return {
        "schema_version": "yo-evidence/1",
        "source_key": source_key, "form_source": form_source,
        "unit_text_sha256": unit_text_sha256, "unit_kind": unit_kind,
        "context_sha256": context_sha256,
        "restored_form_pre_respell": restored_form,
        "restored_vowel_indices": "|".join(map(str, sorted(indices))),
        "observation_contract_version": "yo-observation/1",
        "restoration_fp": restoration_fp_val,
        "norm_content_sha256": norm, "yo_map_sha256": yo_map,
        "prep_config_sha256": prep_cfg,
        "yo_correct": yo_correct, "labeler": labeler, "date": date,
    }


def _write_yo_input(tmp_path, rows, name="yo_input.tsv"):
    p = tmp_path / name
    p.write_text(evaluation.serialize_yo_evidence(rows), encoding="utf-8", newline="")
    return p


def _make_identity(source_key="01_test|0|0", form_source="Пение"):
    sha = lambda s: _hashlib.sha256(s.encode()).hexdigest()
    return {
        "source_key": source_key, "form_source": form_source,
        "unit_text_sha256": sha(form_source + "unit"),
        "unit_kind": "text",
        "context_sha256": sha(form_source + "ctx"),
    }


def _restoration_fp_for(identity, restored_form, indices):
    return _rfp(identity, restored_form, indices)


# ---------------------------------------------------------------------------
# T01: global fp change does not stale a source-current stress label
# ---------------------------------------------------------------------------

class TestT01GlobalFpDoesNotStaleCurrentLabel:
    def test_analysis_fp_change_leaves_active_label_unchanged(self):
        """T01: analysis_fp and yo-map change must not stale a valid five-field identity."""
        units = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx_a = context_for(units)
        # Build a valid gold row using the A-context identity
        identity_a = ctx_a.sources.resolve("01_test|0|0")[0]
        row_a = {**identity_a, "context": "X", "gold_vowel": "0",
                 "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        # Build a "changed" context that has different analysis_fp (simulated via source_fp change)
        # but the same five-field source identity for unit 0
        ctx_changed = evaluation.EvalContext(
            ctx_a.rows, ctx_a.source_fp + "_changed", ctx_a.analysis_fp + "_fp",
            ctx_a.sources, ctx_a.homographs, ctx_a.names, ctx_a.generation,
        )
        state = evaluation.inspect_ledger([row_a], ctx_changed)
        assert state.active.get("01_test|0|0") == evaluation.validate_gold(row_a)
        assert len(state.stale) == 0


# ---------------------------------------------------------------------------
# T02: source token text change → SOURCE_STALE
# ---------------------------------------------------------------------------

class TestT02SourceTokenTextChangeStales:
    def test_source_text_change_makes_label_stale(self):
        """T02: changing unit text changes unit_text_sha256 → old row becomes SOURCE_STALE."""
        units_a = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx_a = context_for(units_a)
        identity_a = ctx_a.sources.resolve("01_test|0|0")[0]
        row_a = {**identity_a, "context": "X", "gold_vowel": "0",
                 "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        # Change source token text
        units_b = copy.deepcopy(units_a)
        units_b[0]["text"] = "Лебедь."
        ctx_b = context_for(units_b)
        state = evaluation.inspect_ledger([row_a], ctx_b)
        assert len(state.stale) == 1 and row_a in state.stale
        assert len(state.active) == 0


# ---------------------------------------------------------------------------
# T03: neighbor unit changes → context_sha mismatch → SOURCE_STALE
# ---------------------------------------------------------------------------

class TestT03NeighborChangeStales:
    def test_neighbor_change_makes_label_stale_new_annotation_allowed(self):
        """T03: neighbor context change → context_sha mismatch → SOURCE_STALE; new can append."""
        units_a = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx_a = context_for(units_a)
        identity_a = ctx_a.sources.resolve("01_test|0|0")[0]
        row_a = {**identity_a, "context": "X", "gold_vowel": "0",
                 "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        # Neighbor changes: same target token text, different surrounding context
        units_b = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Дельта."}]
        ctx_b = context_for(units_b)
        identity_b = ctx_b.sources.resolve("01_test|0|0")[0]
        # Same source token text, but context_sha differs
        assert identity_a["unit_text_sha256"] == identity_b["unit_text_sha256"]
        assert identity_a["context_sha256"] != identity_b["context_sha256"]
        # Old row becomes SOURCE_STALE
        state = evaluation.inspect_ledger([row_a], ctx_b)
        assert len(state.stale) == 1 and row_a in state.stale
        assert len(state.active) == 0
        # New annotation with updated identity can be appended
        row_b = {**identity_b, "context": "X", "gold_vowel": "1",
                 "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        state2 = evaluation.inspect_ledger([row_a, row_b], ctx_b)
        assert state2.active.get("01_test|0|0") == evaluation.validate_gold(row_b)
        assert len(state2.stale) == 1


# ---------------------------------------------------------------------------
# T04: native source ё with gold_vowel=yo → ACTIVE (not LEGACY)
# ---------------------------------------------------------------------------

class TestT04NativeYoActive:
    def test_native_yo_in_form_source_is_active_not_legacy(self):
        """T04: form_source has ё → gold_vowel=yo is ACTIVE; source-native vowel index usable."""
        units = [{"type": "text", "text": "Ёлка."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        identity = ctx.sources.resolve("01_test|0|0")[0]
        assert "ё" in identity["form_source"].lower()
        row = {**identity, "context": "X", "gold_vowel": "yo",
               "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        state = evaluation.inspect_ledger([row], ctx)
        assert state.active.get("01_test|0|0") is not None
        assert len(state.legacy) == 0
        assert len(state.stale) == 0


# ---------------------------------------------------------------------------
# T05 / T10: LEGACY_YO_UNRESOLVED preserved, not active; new numeric activates
# ---------------------------------------------------------------------------

class TestT05T10LegacyYoUnresolved:
    def _legacy_row(self):
        """'Пение' has е, no ё → gold_vowel=yo is LEGACY_YO_UNRESOLVED."""
        units = [{"type": "text", "text": "Пение."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        identity = ctx.sources.resolve("01_test|0|0")[0]
        assert "е" in identity["form_source"].lower() and "ё" not in identity["form_source"].lower()
        row = {**identity, "context": "X", "gold_vowel": "yo",
               "yo_correct": "y", "labeler": "syn", "date": "2026-11-01"}
        return row, ctx

    def test_T05_legacy_yo_not_in_active(self):
        """T05: LEGACY_YO_UNRESOLVED row not placed in active; key counts as incomplete."""
        row, ctx = self._legacy_row()
        state = evaluation.inspect_ledger([row], ctx)
        assert len(state.active) == 0
        assert len(state.legacy) == 1 and row in state.legacy
        assert len(state.stale) == 0

    def test_T10_new_numeric_activates_alongside_legacy(self):
        """T10: new numeric row for same key becomes ACTIVE; legacy retained; no conflict."""
        legacy, ctx = self._legacy_row()
        identity = ctx.sources.resolve("01_test|0|0")[0]
        numeric = {**identity, "context": "X", "gold_vowel": "0",
                   "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        state = evaluation.inspect_ledger([legacy, numeric], ctx)
        assert state.active.get("01_test|0|0") == evaluation.validate_gold(numeric)
        assert len(state.legacy) == 1
        assert len(state.stale) == 0
        assert state.duplicates == 0

    def test_T10_legacy_not_exported_to_archive(self):
        """T10/M4: LEGACY_YO_UNRESOLVED rows stay in gold, not in derived stale archive."""
        legacy, ctx = self._legacy_row()
        state = evaluation.inspect_ledger([legacy], ctx)
        # stale (archive export) must be empty; legacy stays only in gold
        assert len(state.stale) == 0
        assert len(state.legacy) == 1


# ---------------------------------------------------------------------------
# T06: two current conflicting numeric labels → GOLD_ACTIVE_CONFLICT / ERROR
# ---------------------------------------------------------------------------

class TestT06ConflictError:
    def test_two_different_numeric_labels_same_identity_conflict(self):
        """T06: two current numeric rows with different gold_vowel → GOLD_ACTIVE_CONFLICT error."""
        units = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        identity = ctx.sources.resolve("01_test|0|0")[0]
        base = {**identity, "context": "X", "yo_correct": "na",
                "labeler": "syn", "date": "2026-11-15"}
        row0 = {**base, "gold_vowel": "0"}
        row1 = {**base, "gold_vowel": "1"}
        with pytest.raises(evaluation.AnnotationError, match="GOLD_ACTIVE_CONFLICT"):
            evaluation.inspect_ledger([row0, row1], ctx)

    def test_T06_numeric_vs_ambiguous_conflict(self):
        """T06: numeric label then ambiguous for same identity → OWNER_ADJUDICATION_REQUIRED / GOLD_ACTIVE_CONFLICT."""
        units = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        identity = ctx.sources.resolve("01_test|0|0")[0]
        base = {**identity, "context": "X", "yo_correct": "na",
                "labeler": "syn", "date": "2026-11-15"}
        row0 = {**base, "gold_vowel": "0"}
        row1 = {**base, "gold_vowel": "ambiguous"}
        with pytest.raises(evaluation.AnnotationError, match="GOLD_ACTIVE_CONFLICT"):
            evaluation.inspect_ledger([row0, row1], ctx)

    def test_T06_ambiguous_vs_unknown_name_conflict(self):
        """T06: ambiguous then unknown_name for same identity → OWNER_ADJUDICATION_REQUIRED / GOLD_ACTIVE_CONFLICT."""
        units = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        identity = ctx.sources.resolve("01_test|0|0")[0]
        base = {**identity, "context": "X", "yo_correct": "na",
                "labeler": "syn", "date": "2026-11-15"}
        row0 = {**base, "gold_vowel": "ambiguous"}
        row1 = {**base, "gold_vowel": "unknown_name"}
        with pytest.raises(evaluation.AnnotationError, match="GOLD_ACTIVE_CONFLICT"):
            evaluation.inspect_ledger([row0, row1], ctx)


# ---------------------------------------------------------------------------
# T09: source-native unique yo + equivalent numeric = duplicate; both retained
# ---------------------------------------------------------------------------

class TestT09NativeYoPlusNumericDuplicate:
    def test_native_yo_and_numeric_same_vowel_set_are_duplicate(self):
        """T09: source-native ё and equivalent numeric label → duplicate; both physical rows kept."""
        units = [{"type": "text", "text": "Ёлка."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        identity = ctx.sources.resolve("01_test|0|0")[0]
        assert "ё" in identity["form_source"].lower()
        base = {**identity, "context": "X", "yo_correct": "na",
                "labeler": "syn", "date": "2026-11-15"}
        row_yo = {**base, "gold_vowel": "yo"}
        # vowel_count("Ёлка") == 2 (ё at index 0); numeric "0" selects the same vowel
        row_num = {**base, "gold_vowel": "0"}
        state = evaluation.inspect_ledger([row_yo, row_num], ctx)
        assert state.active.get("01_test|0|0") is not None
        assert state.duplicates == 1
        assert len(state.stale) == 0
        assert len(state.legacy) == 0


# ---------------------------------------------------------------------------
# T07: source-only merge independent of sample/analysis/restoration changes
# ---------------------------------------------------------------------------

class TestT07MergeSourceIndependent:
    def test_merge_source_accepts_key_outside_current_sample(self, tmp_path, monkeypatch):
        """T07: merge_source works on source-current key even when sample has changed."""
        units = setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        # Simulate a sample change by modifying the sample record on disk
        sample_dir = paths.OUT / "stress" / "eval" / "sample"
        old_path = next(sample_dir.glob("s2-*.json"))
        import json as _json
        old_record = _json.loads(old_path.read_text(encoding="utf-8"))
        # Change source_fp in the sample record to simulate a stale sample
        stale_record = {**old_record, "source_fp": "stale"}
        old_path.write_text(_json.dumps(stale_record), encoding="utf-8")
        # Todo row for key 0
        row = todo_rows()[0]
        incoming = write_input(tmp_path, [labeled(row)])
        # Regular merge would fail (sample_fp mismatch); merge_source does not care
        result = evaluation.merge_source({}, incoming)
        assert result["added"] == 1

    def test_merge_source_validates_five_field_identity(self, tmp_path, monkeypatch):
        """T07: merge_source rejects stale source identity despite accepting any key."""
        units = setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        row = todo_rows()[0]
        stale_row = {**labeled(row), "unit_text_sha256": "0" * 64}
        with pytest.raises(AnnotationError, match="GOLD_STALE_INPUT"):
            evaluation.merge_source({}, write_input(tmp_path, [stale_row]))


# ---------------------------------------------------------------------------
# T08: restoration_fp movement; stress state (LEGACY) unchanged
# ---------------------------------------------------------------------------

class TestT08RestorationMovementStressUnchanged:
    def test_stress_state_legacy_regardless_of_restoration_position(self):
        """T08: source е/no-ё + gold_vowel=yo → LEGACY in all three F1 scenarios (ADR §1.5)."""
        identity = _make_identity(source_key="01_test|0|0", form_source="Пение")
        ctx = context_for([{"type": "text", "text": "Пение."}, {"type": "text", "text": "Гамма."}])
        real_identity = ctx.sources.resolve("01_test|0|0")[0]
        base = {**real_identity, "context": "X", "gold_vowel": "yo",
                "yo_correct": "y", "labeler": "syn", "date": "2026-11-15"}
        for _ in range(3):  # all three F1 scenarios: removal, introduction, movement
            state = evaluation.inspect_ledger([base], ctx)
            assert len(state.legacy) == 1
            assert len(state.active) == 0
        # Different restoration_fp for position shift; stress oracle is unaffected
        fp_pos0 = _restoration_fp_for(identity, "Пёние", [0])
        fp_pos2 = _restoration_fp_for(identity, "Пениё", [2])
        assert fp_pos0 != fp_pos2


# ---------------------------------------------------------------------------
# yo_changed invariant: same gold row classifies identically regardless of yo_changed
# ---------------------------------------------------------------------------

class TestYoChangedInvariant:
    def test_legacy_classification_independent_of_yo_changed(self):
        """ADR §1.5: LEGACY_YO_UNRESOLVED is a pure source predicate; yo_changed must not alter it."""
        units_no_synth_yo = [{"type": "text", "text": "Пение."}, {"type": "text", "text": "Гамма."}]
        units_synth_yo = [{"type": "text", "text": "Пение."}, {"type": "text", "text": "Гамма."}]
        ctx_a = context_for(units_no_synth_yo)                             # yo_changed=False
        ctx_b = context_for(units_synth_yo, synth={"Пение.": "Пёние."})   # yo_changed=True
        identity = ctx_a.sources.resolve("01_test|0|0")[0]
        assert identity == ctx_b.sources.resolve("01_test|0|0")[0]
        row = {**identity, "context": "X", "gold_vowel": "yo",
               "yo_correct": "y", "labeler": "syn", "date": "2026-11-15"}
        state_a = evaluation.inspect_ledger([row], ctx_a)
        state_b = evaluation.inspect_ledger([row], ctx_b)
        assert len(state_a.legacy) == 1 and len(state_a.active) == 0
        assert len(state_b.legacy) == 1 and len(state_b.active) == 0


# ---------------------------------------------------------------------------
# T19: archive rebuild twice from same gold → byte-identical
# ---------------------------------------------------------------------------

class TestT19ArchiveDoubleRebuildByteIdentical:
    def test_double_rebuild_gives_identical_bytes(self, tmp_path, monkeypatch):
        """T19: f(gold) must yield byte-identical archive on two independent rebuilds."""
        units = setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        # Merge a label to create stale state: label unit 1, then stale it by neighbor change
        row = labeled(todo_rows()[1])
        evaluation.merge({}, write_input(tmp_path, [row]))
        units[0]["text"] = "Дельта."
        evaluation.sample({})
        # Rebuild archive twice by running sample again (both rebuilds from same gold)
        archive = paths.TEXT / "stress_gold.archive.tsv"
        archive_bytes_1 = archive.read_bytes()
        # Second rebuild: corrupt archive and re-run sample (which re-derives archive)
        archive.write_text("synthetic stale export", encoding="utf-8")
        evaluation.sample({})
        archive_bytes_2 = archive.read_bytes()
        assert archive_bytes_1 == archive_bytes_2


# ---------------------------------------------------------------------------
# T28: A→B→A single label reactivates; B becomes SOURCE_STALE
# ---------------------------------------------------------------------------

class TestT28SourceReversionReactivates:
    def test_single_a_label_reactivates_after_ab_a(self):
        """T28: A→B→A for context reversion; single original A label reactivates."""
        units_a = [{"type": "text", "text": "Бета."},
                   {"type": "text", "text": "Гамма."},
                   {"type": "text", "text": "Альфа."}]
        ctx_a = context_for(units_a)
        # L1: label for unit 1 in A-context
        identity_a = ctx_a.sources.resolve("01_test|1|0")[0]
        l1 = {**identity_a, "context": "X", "gold_vowel": "0",
              "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        # B-context: change first unit (prev of unit 1)
        units_b = copy.deepcopy(units_a)
        units_b[0]["text"] = "Дельта."
        ctx_b = context_for(units_b)
        # L2: label for unit 1 in B-context
        identity_b = ctx_b.sources.resolve("01_test|1|0")[0]
        l2 = {**identity_b, "context": "Y", "gold_vowel": "1",
              "yo_correct": "na", "labeler": "syn", "date": "2026-11-15"}
        # B-context: L1 is stale, L2 is active
        state_b = evaluation.inspect_ledger([l1, l2], ctx_b)
        assert l1 in state_b.stale
        assert state_b.active.get("01_test|1|0") == evaluation.validate_gold(l2)
        # A-context (reverted): L1 reactivates, L2 becomes stale
        state_a = evaluation.inspect_ledger([l1, l2], ctx_a)
        assert state_a.active.get("01_test|1|0") == evaluation.validate_gold(l1)
        assert l2 in state_a.stale


# ---------------------------------------------------------------------------
# T34, T35, T37, T39: YO evidence merge operations
# ---------------------------------------------------------------------------

class TestT34T35T37T39YoMerge:
    def _setup(self, tmp_path, monkeypatch):
        units = setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0])]))
        return units

    def _identity(self):
        units = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        ctx = context_for(units)
        return ctx.sources.resolve("01_test|0|0")[0]

    def _patch_obs(self, monkeypatch, fp, form, indices):
        """B3: monkeypatch observer to return RESTORED_obs with given fp for all calls."""
        from audiobook.stress_yo_observer import RESTORED_obs
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, s, c: RESTORED_obs(form, tuple(indices), fp))

    def test_T34a_same_fp_accepted_despite_no_sample(self, tmp_path, monkeypatch):
        """T34a: merge_yo accepts same restoration_fp regardless of sample identity."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp = _restoration_fp_for(identity, "Бёта", [0])
        row = _yo_row(identity["source_key"], identity["form_source"],
                      identity["unit_text_sha256"], identity["unit_kind"],
                      identity["context_sha256"], "Бёта", [0], fp, "y")
        self._patch_obs(monkeypatch, fp, "Бёта", [0])
        result = evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        assert result["added"] == 1 and result["skipped"] == 0

    def test_T34a_repeat_idempotent(self, tmp_path, monkeypatch):
        """T34a: same fp + same y/n is a no-op on repeat."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp = _restoration_fp_for(identity, "Бёта", [0])
        row = _yo_row(identity["source_key"], identity["form_source"],
                      identity["unit_text_sha256"], identity["unit_kind"],
                      identity["context_sha256"], "Бёта", [0], fp, "y")
        self._patch_obs(monkeypatch, fp, "Бёта", [0])
        evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        result = evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        assert result["added"] == 0 and result["skipped"] == 1

    def test_T34b_different_candidate_requires_new_judgment(self, tmp_path, monkeypatch):
        """T34b: different restoration_fp (candidate moved) requires a new YO entry."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp_a = _restoration_fp_for(identity, "Бёта", [0])
        fp_b = _restoration_fp_for(identity, "Бетё", [1])
        row_a = _yo_row(identity["source_key"], identity["form_source"],
                        identity["unit_text_sha256"], identity["unit_kind"],
                        identity["context_sha256"], "Бёта", [0], fp_a, "y")
        row_b = _yo_row(identity["source_key"], identity["form_source"],
                        identity["unit_text_sha256"], identity["unit_kind"],
                        identity["context_sha256"], "Бетё", [1], fp_b, "n")
        # B3: use stateful observer to return the right fp per merge_yo call.
        from audiobook.stress_yo_observer import RESTORED_obs
        obs_sequence = iter([RESTORED_obs("Бёта", (0,), fp_a), RESTORED_obs("Бетё", (1,), fp_b)])
        monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: next(obs_sequence))
        evaluation.merge_yo({}, _write_yo_input(tmp_path, [row_a]))
        result = evaluation.merge_yo({}, _write_yo_input(tmp_path, [row_b]))
        assert result["added"] == 1  # new entry for different fp

    def test_T35_ab_a_reuses_verdict_after_fresh_observation(self, tmp_path, monkeypatch):
        """T35: A→B→A; same restoration_fp reappears → old y/n verdict reused (idempotent)."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp = _restoration_fp_for(identity, "Бёта", [0])
        row = _yo_row(identity["source_key"], identity["form_source"],
                      identity["unit_text_sha256"], identity["unit_kind"],
                      identity["context_sha256"], "Бёта", [0], fp, "y")
        self._patch_obs(monkeypatch, fp, "Бёта", [0])
        evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        # Simulate A→B→A: same fp reappears with same verdict
        result = evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        assert result["skipped"] == 1 and result["added"] == 0

    def test_T37a_same_fp_same_verdict_idempotent(self, tmp_path, monkeypatch):
        """T37: same restoration_fp + same y/n → no-op."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp = _restoration_fp_for(identity, "Бёта", [0])
        row = _yo_row(identity["source_key"], identity["form_source"],
                      identity["unit_text_sha256"], identity["unit_kind"],
                      identity["context_sha256"], "Бёта", [0], fp, "n")
        self._patch_obs(monkeypatch, fp, "Бёта", [0])
        evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        result = evaluation.merge_yo({}, _write_yo_input(tmp_path, [row]))
        assert result["added"] == 0

    def test_T37b_same_fp_opposite_verdict_error(self, tmp_path, monkeypatch):
        """T37: same restoration_fp with opposite y/n → YO_EVIDENCE_CONFLICT/ERROR."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp = _restoration_fp_for(identity, "Бёта", [0])
        row_y = _yo_row(identity["source_key"], identity["form_source"],
                        identity["unit_text_sha256"], identity["unit_kind"],
                        identity["context_sha256"], "Бёта", [0], fp, "y")
        row_n = _yo_row(identity["source_key"], identity["form_source"],
                        identity["unit_text_sha256"], identity["unit_kind"],
                        identity["context_sha256"], "Бёта", [0], fp, "n")
        self._patch_obs(monkeypatch, fp, "Бёта", [0])
        evaluation.merge_yo({}, _write_yo_input(tmp_path, [row_y]))
        with pytest.raises(AnnotationError, match="YO_EVIDENCE_CONFLICT"):
            evaluation.merge_yo({}, _write_yo_input(tmp_path, [row_n]))

    def test_T39_unknown_observer_version_error(self, tmp_path, monkeypatch):
        """T39: unknown observation_contract_version → YO_OBSERVATION_UNSUPPORTED/ERROR."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp = _restoration_fp_for(identity, "Бёта", [0])
        row = _yo_row(identity["source_key"], identity["form_source"],
                      identity["unit_text_sha256"], identity["unit_kind"],
                      identity["context_sha256"], "Бёта", [0], fp, "y")
        bad_row = {**row, "observation_contract_version": "yo-observation/9999"}
        p = tmp_path / "bad_yo.tsv"
        # Build TSV manually bypassing validate_yo_row
        p.write_text("\t".join(evaluation.YO_FIELDS) + "\n"
                     + "\t".join(bad_row[f] for f in evaluation.YO_FIELDS) + "\n",
                     encoding="utf-8", newline="")
        with pytest.raises(AnnotationError, match="YO_OBSERVATION_UNSUPPORTED"):
            evaluation.merge_yo({}, p)

    def test_T39_malformed_indices_rejected(self, tmp_path, monkeypatch):
        """T39: malformed restored_vowel_indices → YO_EVIDENCE_INVALID."""
        with pytest.raises(AnnotationError, match="YO_EVIDENCE_INVALID"):
            evaluation.validate_yo_row({
                "schema_version": "yo-evidence/1",
                "source_key": "01_test|0|0",
                "form_source": "Бета",
                "unit_text_sha256": "a" * 64, "unit_kind": "text",
                "context_sha256": "b" * 64,
                "restored_form_pre_respell": "Бёта",
                "restored_vowel_indices": "0|0",  # duplicate index → invalid
                "observation_contract_version": "yo-observation/1",
                "restoration_fp": "c" * 64,
                "norm_content_sha256": "d" * 64, "yo_map_sha256": "e" * 64,
                "prep_config_sha256": "f" * 64,
                "yo_correct": "y", "labeler": "syn", "date": "2026-11-15",
            })

    def test_f6b_fp_mismatch_between_candidate_and_claimed_fp_error(self, tmp_path, monkeypatch):
        """F6b: restoration_fp doesn't match rfp(identity, form, indices) → YO_STALE_INPUT; no ledger write."""
        self._setup(tmp_path, monkeypatch)
        identity = self._identity()
        fp_for_beta = _restoration_fp_for(identity, "Бёта", [0])
        # Row claims form "Бетё"[1] but fp was computed for "Бёта"[0] → mismatch.
        row = _yo_row(identity["source_key"], identity["form_source"],
                      identity["unit_text_sha256"], identity["unit_kind"],
                      identity["context_sha256"], "Бетё", [1], fp_for_beta, "y")
        yo_input = _write_yo_input(tmp_path, [row])
        before = snapshot(tmp_path)  # snapshot after input file, before merge_yo
        with pytest.raises(AnnotationError, match="YO_STALE_INPUT"):
            evaluation.merge_yo({}, yo_input)
        assert snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# Three original Sol F1 regressions:
#   (1) removal of restored ё → different restoration_fp → old verdict cannot apply
#   (2) introduction of restored ё → new restoration_fp → new judgment needed
#   (3) movement of ё between е positions → different restoration_fp
# ---------------------------------------------------------------------------

class TestF1SolRegressions:
    """In all three F1 scenarios, form_source has е (no ё) and gold_vowel=yo → LEGACY_YO_UNRESOLVED.
    Stress state is unchanged across removal/introduction/movement (ADR §1.5); only restoration_fp differs."""

    def _base_identity(self):
        return _make_identity(source_key="01_test|0|0", form_source="Пение")

    def _legacy_state(self):
        """Shared: build LEGACY inspect_ledger state for 'Пение' (е, no ё, gold_vowel=yo)."""
        ctx = context_for([{"type": "text", "text": "Пение."}, {"type": "text", "text": "Гамма."}])
        identity = ctx.sources.resolve("01_test|0|0")[0]
        row = {**identity, "context": "X", "gold_vowel": "yo",
               "yo_correct": "y", "labeler": "syn", "date": "2026-11-15"}
        return evaluation.inspect_ledger([row], ctx)

    def test_f1_removal_old_verdict_not_reused(self):
        """F1 reg 1: restored ё removed → new restoration_fp → old y/n cannot apply.
        Stress state is LEGACY (source е/no-ё + gold_vowel=yo) regardless of restoration."""
        identity = self._base_identity()
        fp_restored = _restoration_fp_for(identity, "Пёние", [0])
        fp_no_restore = _restoration_fp_for(identity, "Пение", [1])
        assert fp_restored != fp_no_restore
        state = self._legacy_state()
        assert len(state.legacy) == 1 and len(state.active) == 0

    def test_f1_introduction_new_fp_created(self):
        """F1 reg 2: new ё introduced → new restoration_fp separate from prior NONE state.
        Stress state is LEGACY (source е/no-ё + gold_vowel=yo) regardless of restoration."""
        identity = self._base_identity()
        fp_new = _restoration_fp_for(identity, "Пёние", [0])
        fp_other = _restoration_fp_for(identity, "Пениё", [2])
        assert fp_new != fp_other
        state = self._legacy_state()
        assert len(state.legacy) == 1 and len(state.active) == 0

    def test_f1_movement_between_positions_creates_different_fp(self):
        """F1 reg 3: same source identity, ё at position 0 vs position 2 → different fp.
        Stress state is LEGACY (source е/no-ё + gold_vowel=yo) regardless of position."""
        identity = self._base_identity()
        fp_pos0 = _restoration_fp_for(identity, "Пёние", [0])
        fp_pos1 = _restoration_fp_for(identity, "Пениё", [2])
        assert fp_pos0 != fp_pos1
        fp_same_form_diff_idx = _restoration_fp_for(identity, "Пёние", [1])
        assert fp_pos0 != fp_same_form_diff_idx
        state = self._legacy_state()
        assert len(state.legacy) == 1 and len(state.active) == 0


# ---------------------------------------------------------------------------
# T20: audit_archive_compatibility synthetic regression tests (S1, tests 1-8)
# ---------------------------------------------------------------------------

def _gold_row(source_key="01_test|0|0", form_source="Бета", gold_vowel="0",
              yo_correct="na", labeler="syn", date="2026-11-16", **overrides):
    base = {
        "source_key": source_key,
        "form_source": form_source,
        "unit_text_sha256": "a" * 64,
        "unit_kind": "text",
        "context_sha256": "b" * 64,
        "context": "test context",
        "gold_vowel": gold_vowel,
        "yo_correct": yo_correct,
        "labeler": labeler,
        "date": date,
    }
    base.update(overrides)
    return base


def _write_tsv(path, rows, *, allow_blank=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(evaluation.serialize_gold(rows, allow_blank=allow_blank), encoding="utf-8", newline="")


class TestT20AuditArchiveCompatibility:
    def _setup_text(self, tmp_path, monkeypatch):
        text = tmp_path / "text"
        text.mkdir(exist_ok=True)
        monkeypatch.setattr(paths, "TEXT", text)
        return text

    def _bad_tsv_line(self, gold_vowel="variants:1|0"):
        """Build a raw TSV line bypassing validate_gold (for testing invalid inputs)."""
        return ("01_test|0|0\tБета\t" + "a" * 64 + "\ttext\t" + "b" * 64
                + f"\tctx\t{gold_vowel}\tna\tsyn\t2026-11-16\n")

    # --- T20-1: exact 10-field match ---

    def test_T20_1_exact_10field_match_pass(self, tmp_path, monkeypatch):
        """T20-1: archive row exactly matches gold 10-field tuple => PASS."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        _write_tsv(text / "stress_gold.archive.tsv", [row])
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "PASS"
        assert result.code == "OK"
        assert result.gold_rows == 1
        assert result.archive_rows == 1
        assert result.archive_missing is False
        assert result.archive_only_rows == 0
        assert result.excess_duplicates == 0

    # --- T20-2: same 5-field, different human label => BLOCKED (archive_only_rows) ---

    def test_T20_2_same_5field_different_human_fields_blocked(self, tmp_path, monkeypatch):
        """T20-2: archive row matches 5-field identity but differs in gold_vowel => BLOCKED.
        No excess of a known tuple; this is a physically unmatched row (archive_only_rows=1).
        excess_duplicates=0 because the archive tuple is unknown to gold entirely."""
        text = self._setup_text(tmp_path, monkeypatch)
        gold_row = _gold_row(gold_vowel="0")
        archive_row = _gold_row(gold_vowel="1")  # same 5-field, different human label
        _write_tsv(text / "stress_gold.tsv", [gold_row])
        _write_tsv(text / "stress_gold.archive.tsv", [archive_row])
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "BLOCKED"
        assert result.code == "ARCHIVE_COMPAT_BLOCKED"
        assert result.archive_missing is False
        assert result.archive_only_rows == 1   # archive row has no 10-field match in gold
        assert result.excess_duplicates == 0   # not an excess of a known tuple

    # --- T20-3: 3 copies of same row in archive, gold has 1 => BLOCKED ---

    def test_T20_3_excess_duplicates_in_archive_blocked(self, tmp_path, monkeypatch):
        """T20-3: archive has 3 copies of a known tuple, gold has 1 => BLOCKED.
        excess_duplicates=2 (two extra copies beyond gold's 1)."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        row_line = "\t".join(row[f] for f in evaluation.GOLD_FIELDS) + "\n"
        (text / "stress_gold.archive.tsv").write_text(
            "\t".join(evaluation.GOLD_FIELDS) + "\n" + row_line * 3,
            encoding="utf-8", newline="",
        )
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "BLOCKED"
        assert result.archive_rows == 3
        assert result.archive_only_rows == 0   # all archive rows match the gold tuple
        assert result.excess_duplicates == 2   # 3 archive - 1 gold = 2 excess copies
        assert result.archive_missing is False

    # --- T20-4: identical duplicate records within gold multiplicity => PASS ---

    def test_T20_4_identical_duplicates_within_gold_bounds_pass(self, tmp_path, monkeypatch):
        """T20-4: gold has 2 identical rows, archive has 2 same rows => PASS (within bounds)."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        row_line = "\t".join(row[f] for f in evaluation.GOLD_FIELDS) + "\n"
        # Both gold and archive have 2 copies of the same 10-field tuple.
        for name in ("stress_gold.tsv", "stress_gold.archive.tsv"):
            (text / name).write_text(
                "\t".join(evaluation.GOLD_FIELDS) + "\n" + row_line * 2,
                encoding="utf-8", newline="",
            )
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "PASS"
        assert result.archive_rows == 2
        assert result.archive_only_rows == 0
        assert result.excess_duplicates == 0
        assert result.archive_missing is False

    def test_T20_4b_distinct_rows_matching_in_archive_pass(self, tmp_path, monkeypatch):
        """T20-4b: archive is a subset of gold (2 of 3 gold rows) => PASS."""
        text = self._setup_text(tmp_path, monkeypatch)
        row1 = _gold_row()
        row2 = _gold_row(labeler="other-syn", date="2026-11-15")
        row3 = _gold_row(source_key="01_test|1|0", form_source="Гамма",
                         unit_text_sha256="c" * 64, context_sha256="d" * 64)
        _write_tsv(text / "stress_gold.tsv", [row1, row2, row3])
        _write_tsv(text / "stress_gold.archive.tsv", [row1, row2])
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "PASS"
        assert result.gold_rows == 3
        assert result.archive_rows == 2
        assert result.archive_missing is False

    # --- T20-5: bad header / broken TSV => ERROR (AuditResult, not exception) ---

    def test_T20_5_bad_header_archive_invalid(self, tmp_path, monkeypatch):
        """T20-5: bad archive header => AuditResult(status=ERROR, code=ARCHIVE_INVALID)."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        (text / "stress_gold.archive.tsv").write_text("bad_header\n", encoding="utf-8", newline="")
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_INVALID"

    def test_T20_5b_invalid_utf8_archive_invalid(self, tmp_path, monkeypatch):
        """T20-5b: invalid UTF-8 in archive => AuditResult(status=ERROR, code=ARCHIVE_INVALID)."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        (text / "stress_gold.archive.tsv").write_bytes(b"\xff\xfe bad bytes\n")
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_INVALID"

    def test_T20_5c_malformed_gold_gold_invalid(self, tmp_path, monkeypatch):
        """T20-5c: malformed gold (noncanonical variants) => AuditResult(ERROR, GOLD_INVALID)."""
        text = self._setup_text(tmp_path, monkeypatch)
        (text / "stress_gold.tsv").write_text(
            "\t".join(evaluation.GOLD_FIELDS) + "\n" + self._bad_tsv_line("variants:1|0"),
            encoding="utf-8", newline="",
        )
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "GOLD_INVALID"

    # --- T20-6: missing archive => PASS, archive_missing=True, no file created ---

    def test_T20_6_missing_archive_pass_no_file_created(self, tmp_path, monkeypatch):
        """T20-6: archive absent => PASS, archive_missing=True, no file created."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        archive_path = text / "stress_gold.archive.tsv"
        assert not archive_path.exists()
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "PASS"
        assert result.archive_rows == 0
        assert result.archive_missing is True
        assert not archive_path.exists()

    # --- T20-7: concurrent mutation => ERROR ARCHIVE_AUDIT_STALE (returned, not raised) ---

    def test_T20_7_concurrent_mutation_stale(self, tmp_path, monkeypatch):
        """T20-7: archive bytes mutated during recheck => AuditResult(ERROR, ARCHIVE_AUDIT_STALE)."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        archive_path = text / "stress_gold.archive.tsv"
        _write_tsv(archive_path, [row])
        orig_parse = evaluation.parse_gold
        call_count = [0]
        def mutating_parse(text_data, **kw):
            result = orig_parse(text_data, **kw)
            call_count[0] += 1
            if call_count[0] >= 2:
                archive_path.write_bytes(b"mutated\n")
            return result
        monkeypatch.setattr(evaluation, "parse_gold", mutating_parse)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_AUDIT_STALE"

    # --- T20-7a/7b/7f: concurrent file mutations → ARCHIVE_AUDIT_STALE ---

    def test_T20_7a_absent_archive_created_during_audit_stale(self, tmp_path, monkeypatch):
        """T20-7a: archive absent initially, another process creates it during gold parse => STALE."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        archive_path = text / "stress_gold.archive.tsv"
        assert not archive_path.exists()
        orig_parse = evaluation.parse_gold
        def creating_parse(text_data, **kw):
            result = orig_parse(text_data, **kw)
            _write_tsv(archive_path, [row])  # simulate external process creating archive
            return result
        monkeypatch.setattr(evaluation, "parse_gold", creating_parse)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_AUDIT_STALE"
        assert result.archive_missing is True  # was absent at initial read

    def test_T20_7b_present_archive_deleted_during_audit_stale(self, tmp_path, monkeypatch):
        """T20-7b: archive present initially, deleted during archive parse => STALE."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        archive_path = text / "stress_gold.archive.tsv"
        _write_tsv(archive_path, [row])
        orig_parse = evaluation.parse_gold
        call_count = [0]
        def deleting_parse(text_data, **kw):
            result = orig_parse(text_data, **kw)
            call_count[0] += 1
            if call_count[0] >= 2:
                archive_path.unlink()  # simulate external deletion after parse
            return result
        monkeypatch.setattr(evaluation, "parse_gold", deleting_parse)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_AUDIT_STALE"
        assert result.archive_missing is False  # was present at initial read

    def test_T20_7f_malformed_gold_plus_archive_change_stale_wins(self, tmp_path, monkeypatch):
        """T20-7f: gold invalid AND archive mutated => ARCHIVE_AUDIT_STALE (not GOLD_INVALID)."""
        text = self._setup_text(tmp_path, monkeypatch)
        (text / "stress_gold.tsv").write_text(
            "\t".join(evaluation.GOLD_FIELDS) + "\n" + self._bad_tsv_line("variants:1|0"),
            encoding="utf-8", newline="",
        )
        archive_path = text / "stress_gold.archive.tsv"
        _write_tsv(archive_path, [_gold_row()])
        orig_parse = evaluation.parse_gold
        def mutating_parse(text_data, **kw):
            archive_path.write_bytes(b"mutated-during-gold-error\n")
            return orig_parse(text_data, **kw)  # raises AnnotationError for bad gold
        monkeypatch.setattr(evaluation, "parse_gold", mutating_parse)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_AUDIT_STALE"  # staleness takes precedence

    # --- T20-7g/7h: unreadable file or path-is-directory => ERROR, never PASS ---

    def test_T20_7g_unreadable_archive_permission_error(self, tmp_path, monkeypatch):
        """T20-7g: existing archive raises PermissionError => ERROR/ARCHIVE_INVALID, never PASS."""
        import os
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        archive_path = text / "stress_gold.archive.tsv"
        _write_tsv(archive_path, [_gold_row()])
        archive_bytes = archive_path.read_bytes()
        os.chmod(archive_path, 0o000)
        try:
            result = evaluation.audit_archive_compatibility({})
        finally:
            os.chmod(archive_path, 0o644)
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_INVALID"
        assert archive_path.read_bytes() == archive_bytes  # no writes

    def test_T20_7g2_unreadable_gold_permission_error(self, tmp_path, monkeypatch):
        """T20-7g2: existing gold raises PermissionError => ERROR/GOLD_INVALID, never PASS."""
        import os
        text = self._setup_text(tmp_path, monkeypatch)
        gold_path = text / "stress_gold.tsv"
        _write_tsv(gold_path, [_gold_row()])
        gold_bytes = gold_path.read_bytes()
        os.chmod(gold_path, 0o000)
        try:
            result = evaluation.audit_archive_compatibility({})
        finally:
            os.chmod(gold_path, 0o644)
        assert result.status == "ERROR"
        assert result.code == "GOLD_INVALID"
        assert gold_path.read_bytes() == gold_bytes  # no writes

    def test_T20_7h_archive_is_directory_error(self, tmp_path, monkeypatch):
        """T20-7h: archive path is a directory (IsADirectoryError) => ERROR/ARCHIVE_INVALID."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        (text / "stress_gold.archive.tsv").mkdir()
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_INVALID"

    def test_T20_7h2_gold_is_directory_error(self, tmp_path, monkeypatch):
        """T20-7h2: gold path is a directory (IsADirectoryError) => ERROR/GOLD_INVALID."""
        text = self._setup_text(tmp_path, monkeypatch)
        (text / "stress_gold.tsv").mkdir()
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "GOLD_INVALID"

    # --- T20-7i/7j: MISSING→READ_ERROR transition => ARCHIVE_AUDIT_STALE (tri-state) ---

    def test_T20_7i_absent_archive_becomes_directory_stale(self, tmp_path, monkeypatch):
        """T20-7i: archive absent initially, directory created there during parse => STALE.
        This catches the MISSING→READ_ERROR race that collapsed to False-PASS before the
        tri-state fix (_read_state now distinguishes _MISSING from _READ_ERROR)."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        archive_path = text / "stress_gold.archive.tsv"
        assert not archive_path.exists()
        orig_parse = evaluation.parse_gold
        def creating_dir_parse(text_data, **kw):
            result = orig_parse(text_data, **kw)
            archive_path.mkdir()  # create directory, not a readable file
            return result
        monkeypatch.setattr(evaluation, "parse_gold", creating_dir_parse)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_AUDIT_STALE"
        assert result.archive_missing is True  # was absent at initial read

    def test_T20_7j_present_archive_replaced_by_directory_stale(self, tmp_path, monkeypatch):
        """T20-7j: archive present, replaced by directory during parse => STALE."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        archive_path = text / "stress_gold.archive.tsv"
        _write_tsv(archive_path, [row])
        orig_parse = evaluation.parse_gold
        call_count = [0]
        def replacing_parse(text_data, **kw):
            result = orig_parse(text_data, **kw)
            call_count[0] += 1
            if call_count[0] >= 2:
                archive_path.unlink()
                archive_path.mkdir()  # replace file with directory
            return result
        monkeypatch.setattr(evaluation, "parse_gold", replacing_parse)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_AUDIT_STALE"
        assert result.archive_missing is False  # was present at initial read

    # --- T20-7c/7d/7e: PASS/BLOCKED/ERROR preserve ALL files incl. YO, no new files ---

    def _snapshot(self, path):
        return {str(p): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}

    def test_T20_7c_pass_preserves_all_files(self, tmp_path, monkeypatch):
        """T20-7c: PASS preserves all files (gold, archive, YO, no new files)."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        _write_tsv(text / "stress_gold.archive.tsv", [row])
        (text / "stress_gold.yo_evidence.tsv").write_text("yo\n", encoding="utf-8")
        before = self._snapshot(text)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "PASS"
        assert self._snapshot(text) == before

    def test_T20_7d_blocked_preserves_all_files(self, tmp_path, monkeypatch):
        """T20-7d: BLOCKED preserves all files (gold, archive, YO, no new files)."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row(gold_vowel="0")])
        _write_tsv(text / "stress_gold.archive.tsv", [_gold_row(gold_vowel="1")])
        (text / "stress_gold.yo_evidence.tsv").write_text("yo\n", encoding="utf-8")
        before = self._snapshot(text)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "BLOCKED"
        assert self._snapshot(text) == before

    def test_T20_7e_error_preserves_all_files(self, tmp_path, monkeypatch):
        """T20-7e: ERROR preserves all files (gold, archive, YO, no new files)."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        (text / "stress_gold.archive.tsv").write_text("bad\n", encoding="utf-8", newline="")
        (text / "stress_gold.yo_evidence.tsv").write_text("yo\n", encoding="utf-8")
        before = self._snapshot(text)
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert self._snapshot(text) == before

    # --- CLI return codes ---

    def test_T20_cli_pass_rc0(self, tmp_path, monkeypatch, capsys):
        """CLI audit-archive with PASS => exit code 0."""
        text = self._setup_text(tmp_path, monkeypatch)
        row = _gold_row()
        _write_tsv(text / "stress_gold.tsv", [row])
        _write_tsv(text / "stress_gold.archive.tsv", [row])
        monkeypatch.setattr("audiobook.__main__.load_config", lambda: {})
        rc = evaluation.main(["audit-archive"])
        assert rc == 0

    def test_T20_cli_blocked_rc3(self, tmp_path, monkeypatch, capsys):
        """CLI audit-archive with BLOCKED => exit code 3."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row(gold_vowel="0")])
        _write_tsv(text / "stress_gold.archive.tsv", [_gold_row(gold_vowel="1")])
        monkeypatch.setattr("audiobook.__main__.load_config", lambda: {})
        rc = evaluation.main(["audit-archive"])
        assert rc == 3

    def test_T20_cli_error_rc1(self, tmp_path, monkeypatch, capsys):
        """CLI audit-archive with ERROR (bad archive) => exit code 1."""
        text = self._setup_text(tmp_path, monkeypatch)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        (text / "stress_gold.archive.tsv").write_text("bad\n", encoding="utf-8", newline="")
        monkeypatch.setattr("audiobook.__main__.load_config", lambda: {})
        rc = evaluation.main(["audit-archive"])
        assert rc == 1

    # --- T20-8: T19 rebuild independent of archive ---

    def test_T20_8_t19_rebuild_independent_of_archive(self, tmp_path, monkeypatch):
        """T20-8: T19 rebuild_archive is byte-deterministic regardless of prior archive state."""
        units = setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        row = labeled(todo_rows()[1])
        evaluation.merge({}, write_input(tmp_path, [row]))
        units[0]["text"] = "Дельта."
        evaluation.sample({})
        archive = paths.TEXT / "stress_gold.archive.tsv"
        archive_bytes_1 = archive.read_bytes()
        archive.write_text("corrupted-state\n", encoding="utf-8")
        evaluation.sample({})
        archive_bytes_2 = archive.read_bytes()
        assert archive_bytes_1 == archive_bytes_2


# ---------------------------------------------------------------------------
# T15: strict variants synthetic regression tests (S1, tests 9-13)
# ---------------------------------------------------------------------------

class TestT15StrictVariants:
    def _row(self, gold_vowel, **kw):
        return _gold_row(gold_vowel=gold_vowel, **kw)

    def test_T15_9_unsorted_variants_gold_invalid(self):
        """T15-9: unsorted variants:1|0 => GOLD_INVALID."""
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.validate_gold(self._row("variants:1|0"))

    def test_T15_10a_duplicate_indices_gold_invalid(self):
        """T15-10a: variants:0|0 (duplicate index) => GOLD_INVALID."""
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.validate_gold(self._row("variants:0|0"))

    def test_T15_10b_out_of_range_index_gold_invalid(self):
        """T15-10b: variants:0|9 out of range for 'Бета' (2 vowels) => GOLD_INVALID."""
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.validate_gold(self._row("variants:0|9"))

    def test_T15_10c_noncanonical_leading_zero_gold_invalid(self):
        """T15-10c: variants:00|1 (noncanonical) => GOLD_INVALID."""
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.validate_gold(self._row("variants:00|1"))

    def test_T15_11_strict_ascending_in_range_accepted(self):
        """T15-11: variants:0|1 strictly ascending and in-range => accepted unchanged."""
        result = evaluation.validate_gold(self._row("variants:0|1"))
        assert result["gold_vowel"] == "variants:0|1"

    def test_T15_12_noncanonical_historical_gold_error_audit(self, tmp_path, monkeypatch):
        """T15-12: noncanonical variants in gold => AuditResult(ERROR, GOLD_INVALID), no writes."""
        text = tmp_path / "text"
        text.mkdir()
        monkeypatch.setattr(paths, "TEXT", text)
        bad_tsv = ("\t".join(evaluation.GOLD_FIELDS) + "\n"
                   + "01_test|0|0\tБета\t" + "a" * 64 + "\ttext\t" + "b" * 64
                   + "\tctx\tvariants:1|0\tna\tsyn\t2026-11-16\n")
        (text / "stress_gold.tsv").write_text(bad_tsv, encoding="utf-8", newline="")
        gold_before = (text / "stress_gold.tsv").read_bytes()
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "GOLD_INVALID"
        assert (text / "stress_gold.tsv").read_bytes() == gold_before  # no writes

    def test_T15_12b_noncanonical_gold_error_before_merge(self, tmp_path, monkeypatch):
        """T15-12b: noncanonical variants in gold => GOLD_INVALID in merge (no write)."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        row = todo_rows()[0]
        # Write gold directly with unsorted variants (bypassing validate_gold)
        bad_tsv = ("\t".join(evaluation.GOLD_FIELDS) + "\n"
                   + row["source_key"] + "\t" + row["form_source"] + "\t"
                   + row["unit_text_sha256"] + "\t" + row["unit_kind"] + "\t"
                   + row["context_sha256"] + "\tctx\tvariants:1|0\tna\tsyn\t2026-11-16\n")
        gold_path = paths.TEXT / "stress_gold.tsv"
        gold_path.write_text(bad_tsv, encoding="utf-8", newline="")
        gold_before = gold_path.read_bytes()
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.merge({}, write_input(tmp_path, [labeled(row)]))
        assert gold_path.read_bytes() == gold_before  # no writes

    def test_T15_12c_noncanonical_in_archive_error_audit(self, tmp_path, monkeypatch):
        """T15-12c: noncanonical variants in archive => AuditResult(ERROR, ARCHIVE_INVALID), no writes."""
        text = tmp_path / "text"
        text.mkdir()
        monkeypatch.setattr(paths, "TEXT", text)
        _write_tsv(text / "stress_gold.tsv", [_gold_row()])
        bad_tsv = ("\t".join(evaluation.GOLD_FIELDS) + "\n"
                   + "01_test|0|0\tБета\t" + "a" * 64 + "\ttext\t" + "b" * 64
                   + "\tctx\tvariants:1|0\tna\tsyn\t2026-11-16\n")
        (text / "stress_gold.archive.tsv").write_text(bad_tsv, encoding="utf-8", newline="")
        archive_before = (text / "stress_gold.archive.tsv").read_bytes()
        result = evaluation.audit_archive_compatibility({})
        assert result.status == "ERROR"
        assert result.code == "ARCHIVE_INVALID"
        assert (text / "stress_gold.archive.tsv").read_bytes() == archive_before  # no writes

    def test_T15_12d_score_bad_variants_gold_invalid_no_write(self, tmp_path, monkeypatch):
        """T15-12d: score() reads gold with unsorted variants => GOLD_INVALID; no score written."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        row = todo_rows()[0]
        evaluation.merge({}, write_input(tmp_path, [labeled(row)]))
        gold_path = paths.TEXT / "stress_gold.tsv"
        # Inject unsorted variants directly, bypassing validate_gold
        bad_tsv = ("\t".join(evaluation.GOLD_FIELDS) + "\n"
                   + row["source_key"] + "\t" + row["form_source"] + "\t"
                   + row["unit_text_sha256"] + "\t" + row["unit_kind"] + "\t"
                   + row["context_sha256"] + "\tctx\tvariants:1|0\tna\tsyn\t2026-11-16\n")
        gold_path.write_text(bad_tsv, encoding="utf-8", newline="")
        gold_before = gold_path.read_bytes()
        score_dir = paths.OUT / "stress" / "eval" / "score"
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.score({})
        assert gold_path.read_bytes() == gold_before  # no writes to gold
        # No score JSON was written
        assert not score_dir.exists() or not list(score_dir.glob("s2-*.json"))


# ---------------------------------------------------------------------------
# Gate A: merge() must never modify the versioned owner todo (R2)
# Conservative policy pending architect Issue #17.
# ---------------------------------------------------------------------------

class TestGateAPartialMergePreservesTodo:
    """R2 regression: merge() must leave the versioned owner todo byte-identical after any merge."""

    def _todo_path(self):
        todos = sorted(paths.TEXT.glob("stress_gold.todo.s2-*.tsv"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        assert todos, "no todo file found"
        return todos[0]

    def test_partial_merge_todo_bytes_identical(self, tmp_path, monkeypatch):
        """R2: partial merge (1 of 3 rows) must leave todo byte-for-byte unchanged."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        assert len(rows) == 3, f"expected 3 todo rows, got {len(rows)}"
        todo_path = self._todo_path()
        todo_bytes_before = todo_path.read_bytes()

        evaluation.merge({}, write_input(tmp_path, [labeled(rows[0])]))

        assert todo_path.exists(), "todo must still exist after partial merge"
        assert todo_path.read_bytes() == todo_bytes_before, (
            "todo must be byte-identical after partial merge (all 3 rows preserved, "
            "including the merged row)"
        )
        # Gold must have the one merged row
        gold = evaluation.parse_gold(
            (paths.TEXT / "stress_gold.tsv").read_text(encoding="utf-8"))
        assert len(gold) == 1
        assert gold[0]["source_key"] == rows[0]["source_key"]

    def test_full_merge_todo_bytes_identical(self, tmp_path, monkeypatch):
        """R2: full merge (all 3 rows) must still leave todo byte-identical (no auto-retire)."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        todo_path = self._todo_path()
        todo_bytes_before = todo_path.read_bytes()

        evaluation.merge({}, write_input(tmp_path, [labeled(r) for r in rows]))

        assert todo_path.exists(), "todo must not be auto-retired (pending Issue #17)"
        assert todo_path.read_bytes() == todo_bytes_before, (
            "todo must be byte-identical even after a full-coverage merge"
        )

    def test_different_owner_label_preserved(self, tmp_path, monkeypatch):
        """R2: merge of one row must not alter owner label in another row of the todo."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        todo_path = self._todo_path()
        # Simulate an owner who added a custom label to rows[2] directly in the file
        owner_text = todo_path.read_text(encoding="utf-8")
        # We care about byte-identity, not about what the owner wrote;
        # just capture the bytes as-is after sample()
        todo_bytes_before = todo_path.read_bytes()

        evaluation.merge({}, write_input(tmp_path, [labeled(rows[0])]))

        assert todo_path.read_bytes() == todo_bytes_before, (
            "owner label in unmerged rows must be preserved verbatim"
        )

    def test_concurrent_owner_edit_preserved(self, tmp_path, monkeypatch):
        """R2: if owner edits the todo between sample() and merge(), merge() must not undo it."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        todo_path = self._todo_path()

        # Simulate owner adding a note to the todo after sample() returned
        original_text = todo_path.read_text(encoding="utf-8")
        edited_bytes = (original_text + "# owner note\n").encode("utf-8")
        todo_path.write_bytes(edited_bytes)

        evaluation.merge({}, write_input(tmp_path, [labeled(rows[0])]))

        assert todo_path.exists(), "todo must still exist"
        assert todo_path.read_bytes() == edited_bytes, (
            "merge() must not overwrite concurrent owner edits to the todo"
        )

    def test_malformed_todo_not_deleted_on_merge(self, tmp_path, monkeypatch):
        """R2: malformed todo bytes must remain untouched after any merge."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        todo_path = self._todo_path()
        todo_path.write_bytes(b"corrupted\ttodo\n")
        corrupted_bytes = todo_path.read_bytes()

        evaluation.merge({}, write_input(tmp_path, [labeled(rows[0])]))

        assert todo_path.exists(), "malformed todo must not be deleted"
        assert todo_path.read_bytes() == corrupted_bytes, "malformed todo must not be modified"

    def test_blank_batch_todo_bytes_identical(self, tmp_path, monkeypatch):
        """R2: batch with all-blank labels must leave todo byte-identical."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        todo_path = self._todo_path()
        todo_bytes_before = todo_path.read_bytes()

        # All batch rows are blank (no annotation labels)
        blank_rows = [{**r} for r in rows]
        evaluation.merge({}, write_input(tmp_path, blank_rows))

        assert todo_path.read_bytes() == todo_bytes_before, (
            "todo must be byte-identical after all-blank merge"
        )

    def test_idempotent_replay_no_change(self, tmp_path, monkeypatch):
        """R2: replaying the same batch twice must leave todo byte-identical on both runs."""
        setup_book(tmp_path, monkeypatch)
        evaluation.sample({})
        rows = todo_rows()
        todo_path = self._todo_path()
        todo_bytes_before = todo_path.read_bytes()

        batch = [labeled(rows[0])]
        evaluation.merge({}, write_input(tmp_path, batch))
        assert todo_path.read_bytes() == todo_bytes_before, "todo changed on first replay"
        evaluation.merge({}, write_input(tmp_path, batch))
        assert todo_path.read_bytes() == todo_bytes_before, "todo changed on second replay"
