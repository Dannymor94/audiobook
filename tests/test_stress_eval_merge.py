"""Synthetic human labels, C3 version history and durable replacement oracles."""
import json
from pathlib import Path

import pytest

from audiobook import paths, stress_eval as evaluation
from audiobook.unitmap import AnnotationError
from test_stress_eval_sample import context_for, setup_book


def todo_rows():
    return evaluation.parse_gold((paths.TEXT / "stress_gold.todo.tsv").read_text(encoding="utf-8"), allow_blank=True)


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
                                  "variants:0", "variants:0|0", "variants:0|2", "variants:00|1", "variants:1|"])
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
    annotated = labeled(todo_rows()[0], "variants:1|0")
    canonical = evaluation.serialize_gold([annotated])
    assert evaluation.parse_gold(canonical)[0]["gold_vowel"] == "variants:0|1"
    assert evaluation.serialize_gold(evaluation.parse_gold(canonical.replace("\n", "\r\n"))) == canonical
    for text in (canonical.rstrip("\n"), canonical + "\n", canonical.replace("source_key", "key", 1),
                 canonical.replace("\t", "", 1), canonical.replace("synthetic-owner", "bad\tcell")):
        with pytest.raises(AnnotationError, match="GOLD_INVALID"):
            evaluation.parse_gold(text)


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
    first = labeled(row, "variants:1|0")
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
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    rows = todo_rows()
    todo = paths.TEXT / "stress_gold.todo.tsv"
    todo.write_text(evaluation.serialize_gold([labeled(rows[0]), *rows[1:]], allow_blank=True), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError, match="TODO_HAS_UNMERGED_LABELS"):
        evaluation.sample({})
    assert snapshot(tmp_path) == before
    assert evaluation.merge({}, todo)["added"] == 1
    assert evaluation.sample({})["todo"] == 2
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
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("*.json"))
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
    path = next((paths.OUT / "stress" / "eval" / "sample").glob("*.json"))
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
