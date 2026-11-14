"""Synthetic end-to-end score adapter, current identities and private publication."""
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from audiobook import paths, stress_eval as evaluation, stress_metrics
from audiobook.unitmap import AnnotationError
from test_stress_eval_sample import context_for, setup_book
from test_stress_eval_merge import labeled, todo_rows, write_input, snapshot


def predictions(context, changes=None, *, homographs=None):
    changes = changes or {}
    rows = tuple(type(occ)(**{**asdict(occ), "f6_status": "resolved", "f6_vowel": 0,
                             **changes.get(occ.source_key, {})}) for occ in context.rows)
    return evaluation.EvalContext(rows, context.source_fp, context.analysis_fp, context.sources,
                                  frozenset(homographs or ()), context.names, context.generation)


def ready(tmp_path, monkeypatch, *, units=None, changes=None, homographs=None):
    units = setup_book(tmp_path, monkeypatch, units)
    monkeypatch.setattr(evaluation, "_load_context", lambda _: predictions(context_for(units), changes, homographs=homographs))
    evaluation.sample({})
    return units


def complete(tmp_path):
    return evaluation.merge({}, write_input(tmp_path, [labeled(row) for row in todo_rows()]))


def score_path():
    return next((paths.OUT / "stress" / "eval" / "score").glob("*.json"))


def test_complete_exact_schema_aggregates_and_owner_files_readonly(tmp_path, monkeypatch):
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    owner_before = {p: p.read_bytes() for p in paths.TEXT.glob("*.tsv")}
    # A corrupt archive cannot supply or invalidate active labels.
    archive = paths.TEXT / "stress_gold.archive.tsv"
    archive.write_text("non-authoritative synthetic garbage", encoding="utf-8")
    owner_before[archive] = archive.read_bytes()
    result = evaluation.score({})
    assert result["status"] == "COMPLETE"
    assert set(result) == {"source_fp", "analysis_fp", "sample_fp", "gold_sha256", "counts", "metrics", "wilson", "gates", "status"}
    assert result["gold_sha256"] == hashlib.sha256((paths.TEXT / "stress_gold.tsv").read_bytes()).hexdigest()
    assert result["counts"]["selected"] == result["counts"]["active_labels"] == result["counts"]["usable_gold"] == 3
    assert result["counts"]["missing_labels"] == 0
    assert result["metrics"]["overall"]["accuracy_resolved"]["rate"] == 1
    assert result["wilson"]["overall"]["accuracy_resolved"] == {"lower": 0.4385, "upper": 1.0}
    assert json.loads(score_path().read_text(encoding="utf-8")) == result
    assert {p: p.read_bytes() for p in paths.TEXT.glob("*.tsv")} == owner_before
    text = score_path().read_text(encoding="utf-8")
    for forbidden in ("source_key", "form_source", "context", "labeler", "synthetic-owner", "01_test", "Бета", "Гамма", "Альфа"):
        assert forbidden not in text
    before = snapshot(tmp_path)
    assert evaluation.score({}) == result
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("mode", ["missing", "empty", "partial", "stale"])
def test_incomplete_never_computes_partial_metrics_or_passing_gates(tmp_path, monkeypatch, mode):
    units = ready(tmp_path, monkeypatch)
    gold = paths.TEXT / "stress_gold.tsv"
    if mode == "missing":
        gold.unlink()
    elif mode in ("partial", "stale"):
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[1])]))
        if mode == "stale":
            units[0]["text"] = "Дельта."
            evaluation.sample({})
    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete gold must not produce partial metrics")
    monkeypatch.setattr(stress_metrics, "calculate_metrics", forbidden)
    before = {p: p.read_bytes() for p in paths.TEXT.glob("*.tsv")}
    result = evaluation.score({})
    assert result["status"] == "INCOMPLETE"
    assert result["counts"]["missing_labels"] == (2 if mode == "partial" else 3)
    assert result["metrics"] is result["wilson"] is result["gates"] is None
    assert {p: p.read_bytes() for p in paths.TEXT.glob("*.tsv")} == before


def test_stale_relabel_archive_score_uses_only_new_active_version(tmp_path, monkeypatch):
    units = ready(tmp_path, monkeypatch)
    complete(tmp_path)
    assert evaluation.score({})["metrics"]["overall"]["accuracy_resolved"]["k"] == 3
    units[0]["text"] = "Дельта."
    evaluation.sample({})
    assert evaluation.score({})["status"] == "INCOMPLETE"
    new = [labeled(row, "1" if row["source_key"] == "01_test|1|0" else "0") for row in todo_rows()]
    incoming = write_input(tmp_path, new)
    evaluation.merge({}, incoming)
    result = evaluation.score({})
    assert result["status"] == "COMPLETE"
    assert result["counts"]["stale_gold"] == 2
    assert (result["metrics"]["overall"]["accuracy_resolved"]["k"],
            result["metrics"]["overall"]["accuracy_resolved"]["n"]) == (2, 3)
    ledger = evaluation.parse_gold((paths.TEXT / "stress_gold.tsv").read_text(encoding="utf-8"))
    assert len(ledger) == 5
    archive = evaluation.parse_gold((paths.TEXT / "stress_gold.archive.tsv").read_text(encoding="utf-8"))
    assert len(archive) == 2
    before = snapshot(tmp_path)
    evaluation.merge({}, incoming)
    assert evaluation.score({}) == result
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("label", ["ambiguous", "unknown_name"])
def test_complete_ambiguous_human_gold_never_considered_correct(tmp_path, monkeypatch, label):
    ready(tmp_path, monkeypatch, homographs={"бета", "гамма", "альфа"})
    evaluation.merge({}, write_input(tmp_path, [labeled(row, label) for row in todo_rows()]))
    result = evaluation.score({})
    assert result["status"] == "COMPLETE" and result["counts"]["usable_gold"] == 0
    assert result["metrics"]["overall"]["coverage"]["rate"] == 1
    assert result["metrics"]["overall"]["suggestion_precision"]["n"] == 0
    assert result["gates"]["G_hint"] == "INCONCLUSIVE"
    assert not result["gates"]["hint_allows_ordering_only"]


@pytest.mark.parametrize("label,correct", [("0", True), ("1", False), ("variants:1|0", True), ("yo", True)])
def test_accepted_gold_variants_and_synth_yo(tmp_path, monkeypatch, label, correct):
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    monkeypatch.setattr(evaluation, "_load_context", lambda _: predictions(context_for(units, synth={"Елка.": "Ёлка."})))
    evaluation.sample({})
    evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], label, yo_correct="y")]))
    result = evaluation.score({})
    if label == "yo":
        # ADR §1.5/T05: form_source "Елка" has е but no ё → gold_vowel=yo is LEGACY_YO_UNRESOLVED.
        # Selected key has no active label → INCOMPLETE; metrics=null.
        assert result["metrics"] is None
    else:
        assert result["metrics"]["overall"]["accuracy_resolved"]["k"] == int(correct)
        assert result["metrics"]["overall"]["yo_precision"]["n"] == 1
        assert result["gates"]["YO"] == "YO_NO_EVIDENCE"


def test_native_yo_position_and_unresolved_not_correct(tmp_path, monkeypatch):
    ready(tmp_path, monkeypatch, units=[{"type": "text", "text": "Бетё."}],
          changes={"01_test|0|0": {"f6_vowel": 1}})
    evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "yo")]))
    assert evaluation.score({})["metrics"]["overall"]["accuracy_resolved"]["k"] == 1
    units = [{"type": "text", "text": "Бетё."}]
    monkeypatch.setattr(evaluation, "_load_context", lambda _: predictions(context_for(units),
                        {"01_test|0|0": {"f6_status": "no_stress", "f6_vowel": 1}}))
    result = evaluation.score({})
    assert result["metrics"]["overall"]["accuracy_resolved"]["n"] == 0
    assert result["metrics"]["overall"]["coverage"]["rate"] == 0


@pytest.mark.parametrize("k,n,gate", [(92, 100, "PASS"), (91, 100, "INCONCLUSIVE"),
                                    (0, 10, "FAIL"), (73, 73, "INCONCLUSIVE"), (40, 40, "INCONCLUSIVE")])
def test_end_to_end_wilson_hint_thresholds(tmp_path, monkeypatch, k, n, gate):
    units = [{"type": "text", "text": "Бета."} for _ in range(n)]
    changes = {f"01_test|{i}|0": {"f6_vowel": 1} for i in range(k, n)}
    ready(tmp_path, monkeypatch, units=units, changes=changes, homographs={"бета"})
    complete(tmp_path)
    result = evaluation.score({})
    assert result["gates"]["G_hint"] == gate
    rate = result["metrics"]["overall"]["suggestion_precision"]
    assert (rate["k"], rate["n"]) == (k, n)
    assert result["gates"]["hint_allows_ordering_only"] == (gate == "PASS")


def test_adapter_mapping_y_property_override_and_population_weights(tmp_path, monkeypatch):
    units = [{"type": "text", "text": "Елка."}, {"type": "text", "text": "Бета."}]
    setup_book(tmp_path, monkeypatch, units)
    base = context_for(units, synth={"Елка.": "Ёлка."})
    context = predictions(base, {"01_test|0|0": {"status": "covered_by_override", "f6_vowel": 1}}, homographs={"елка"})
    monkeypatch.setattr(evaluation, "_load_context", lambda _: context)
    evaluation.sample({})
    annotated = [labeled(row, yo_correct="n" if row["form_source"] == "Елка" else "na") for row in todo_rows()]
    evaluation.merge({}, write_input(tmp_path, annotated))
    result = evaluation.score({})
    metrics = result["metrics"]["overall"]
    assert (metrics["suggestion_precision"]["k"], metrics["suggestion_precision"]["n"]) == (0, 1)
    assert (metrics["override_disagreement"]["k"], metrics["override_disagreement"]["n"]) == (1, 1)
    assert (metrics["yo_precision"]["k"], metrics["yo_precision"]["n"]) == (0, 1)
    assert result["gates"]["YO"] == "YO_WARN"
    assert result["counts"]["by_stratum"]["yo_changed"]["selected"] == 0
    assert result["metrics"]["book_estimates"]["suggestion_precision"] == {
        "rate": 0, "covered_population": 1, "total_population": 2}


@pytest.mark.parametrize("fault", ["sample", "source_fp", "analysis_fp", "gold", "conflict", "yo_unstressed", "stale_generation"])
def test_validation_error_never_publishes_or_rewrites_old_score(tmp_path, monkeypatch, fault):
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    evaluation.score({})
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("*.json"))
    if fault in ("sample", "source_fp", "analysis_fp"):
        value = json.loads(record.read_text(encoding="utf-8"))
        value["keys" if fault == "sample" else fault] = [] if fault == "sample" else "corrupt"
        record.write_text(json.dumps(value), encoding="utf-8")
    elif fault == "stale_generation":
        def stale(_):
            raise AnnotationError("INVENTORY_STALE")
        monkeypatch.setattr(evaluation, "_load_context", stale)
    else:
        gold = paths.TEXT / "stress_gold.tsv"
        if fault == "gold":
            gold.write_text("malformed", encoding="utf-8")
        elif fault == "yo_unstressed":
            gold.write_text(gold.read_text(encoding="utf-8").replace("\t0\t", "\tyo_unstressed\t", 1), encoding="utf-8")
        else:
            rows = evaluation.parse_gold(gold.read_text(encoding="utf-8"))
            gold.write_text(evaluation.serialize_gold(rows + [labeled(rows[0], "1")]), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(AnnotationError):
        evaluation.score({})
    assert snapshot(tmp_path) == before


def test_duplicate_active_labels_logically_score_once(tmp_path, monkeypatch):
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    gold = paths.TEXT / "stress_gold.tsv"
    rows = evaluation.parse_gold(gold.read_text(encoding="utf-8"))
    gold.write_text(evaluation.serialize_gold(rows + [labeled(rows[0], labeler="another-synthetic-owner")]), encoding="utf-8")
    result = evaluation.score({})
    assert result["counts"]["duplicates"] == 1
    assert result["metrics"]["overall"]["accuracy_resolved"]["n"] == 3


@pytest.mark.parametrize("phase", ["before", "after"])
def test_atomic_score_crash_and_replay(tmp_path, monkeypatch, phase):
    ready(tmp_path, monkeypatch)
    evaluation.score({})
    target = score_path()
    old = target.read_bytes()
    complete(tmp_path)
    replace = evaluation.os.replace
    def crash(src, dst):
        if dst == target and phase == "before":
            raise OSError("synthetic pre-rename crash")
        replace(src, dst)
        if dst == target and phase == "after":
            raise OSError("synthetic post-rename crash")
    with monkeypatch.context() as patch:
        patch.setattr(evaluation.os, "replace", crash)
        with pytest.raises(AnnotationError, match="GOLD_WRITE_FAILED"):
            evaluation.score({})
    assert json.loads(target.read_bytes())["status"] == ("INCOMPLETE" if phase == "before" else "COMPLETE")
    if phase == "before":
        assert target.read_bytes() == old
    assert evaluation.score({})["status"] == "COMPLETE"
    assert not list(target.parent.glob("*.txn-*.json"))


@pytest.mark.parametrize("fault", ["guard", "gold_change", "sample_change", "generation_change"])
def test_late_change_and_p1_prevent_score_publication(tmp_path, monkeypatch, fault):
    units = ready(tmp_path, monkeypatch)
    complete(tmp_path)
    before = snapshot(tmp_path)
    if fault == "guard":
        def reject(path):
            raise AnnotationError("PRIVATE_OUTPUT_REQUIRED")
        monkeypatch.setattr(evaluation, "private_output_guard", reject)
    else:
        original = evaluation._assert_current
        def change(context, config):
            if fault == "gold_change":
                gold = paths.TEXT / "stress_gold.tsv"
                gold.write_text(gold.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            elif fault == "sample_change":
                next((paths.OUT / "stress" / "eval" / "sample").glob("*.json")).write_text("{}", encoding="utf-8")
            else:
                units[0]["text"] = "Дельта."
            original(context, config)
        monkeypatch.setattr(evaluation, "_assert_current", change)
    with pytest.raises(AnnotationError):
        evaluation.score({})
    assert not (paths.OUT / "stress" / "eval" / "score").exists()
    if fault in ("guard", "generation_change"):
        assert snapshot(tmp_path) == before


@pytest.mark.parametrize("mode,expected", [("complete", 0), ("incomplete", 2), ("error", 1)])
def test_cli_status_exit_codes(tmp_path, monkeypatch, capsys, mode, expected):
    from audiobook import __main__
    ready(tmp_path, monkeypatch)
    monkeypatch.setattr(__main__, "load_config", lambda: {})
    if mode == "complete":
        complete(tmp_path)
    elif mode == "error":
        (paths.TEXT / "stress_gold.tsv").write_text("malformed", encoding="utf-8")
    assert evaluation.main(["score"]) == expected
    output = capsys.readouterr().out
    assert {"complete": "COMPLETE", "incomplete": "INCOMPLETE", "error": "ERROR"}[mode] in output
    assert "01_test|" not in output and "synthetic-owner" not in output


def test_score_artifacts_deterministic_across_process_hashseeds(tmp_path):
    script = '''import sys,json
from pathlib import Path
sys.path.insert(0,str(Path("tests").resolve()))
from pytest import MonkeyPatch
from test_stress_eval_score import ready,complete,score_path
from audiobook import stress_eval
with MonkeyPatch.context() as patch:
 ready(Path(sys.argv[1]),patch)
 complete(Path(sys.argv[1]))
 stress_eval.score({})
 print(score_path().read_bytes().hex())
'''
    outputs = []
    for seed in (1, 2, 3):
        directory = tmp_path / str(seed)
        directory.mkdir()
        run = subprocess.run([sys.executable, "-B", "-c", script, str(directory)], capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONDONTWRITEBYTECODE": "1"})
        assert run.returncode == 0, run.stderr
        outputs.append(run.stdout)
    assert outputs[0] == outputs[1] == outputs[2]
