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
    # config={} → yo_restore=False → observer returns NONE_obs → not YO_EVALUABLE → yo_missing=0
    result = evaluation.score({})
    if label == "yo":
        # ADR §1.5/T05: form_source "Елка" has е but no ё → gold_vowel=yo is LEGACY_YO_UNRESOLVED.
        # Selected key has no active label → INCOMPLETE; metrics=null; CLI rc=2.
        assert result["status"] == "INCOMPLETE"
        assert result["metrics"] is None
        from audiobook import __main__ as _main_mod
        monkeypatch.setattr(_main_mod, "load_config", lambda: {})
        assert evaluation.main(["score"]) == 2
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
    # config={} → yo_restore=False → observer returns NONE_obs → not YO_EVALUABLE → yo_missing=0
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


# ---------------------------------------------------------------------------
# I3 oracles: T11, T12, T13, T29, T38, T41, T42 (ADR §5, §7)
# ---------------------------------------------------------------------------

class TestT11AmbiguousOnly:
    def test_ambiguous_gold_is_complete_with_inconclusive_hint(self, tmp_path, monkeypatch):
        """T11: only ambiguous labels → COMPLETE; usable_gold=0; G_hint=INCONCLUSIVE (n=0)."""
        units = [{"type": "text", "text": "Слово."}]
        ready(tmp_path, monkeypatch, units=units)
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "ambiguous")]))
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["counts"]["missing_labels"] == 0
        assert result["metrics"]["overall"]["accuracy_resolved"]["n"] == 0
        assert result["gates"]["G_hint"] == "INCONCLUSIVE"


class TestT12UnknownNameOnly:
    def test_unknown_name_gold_is_complete_zero_accuracy_denominator(self, tmp_path, monkeypatch):
        """T12: only unknown_name labels → COMPLETE; usable_gold=0; accuracy_resolved.n=0."""
        units = [{"type": "text", "text": "Слово."}]
        ready(tmp_path, monkeypatch, units=units)
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "unknown_name")]))
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["counts"]["missing_labels"] == 0
        assert result["metrics"]["overall"]["accuracy_resolved"]["n"] == 0
        assert result["metrics"]["overall"]["accuracy_resolved"]["rate"] is None


class TestT13NoGold:
    def test_no_gold_labels_is_incomplete(self, tmp_path, monkeypatch):
        """T13: selected key has no gold label → INCOMPLETE; metrics/wilson/gates=None."""
        units = [{"type": "text", "text": "Слово."}]
        ready(tmp_path, monkeypatch, units=units)
        # Intentionally skip merge → missing gold label
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_labels"] == 1
        assert result["metrics"] is None
        assert result["wilson"] is None
        assert result["gates"] is None


class TestT29YoEvaluableNoLabel:
    def test_yo_evaluable_key_without_gold_label_is_incomplete(self, tmp_path, monkeypatch):
        """T29: YO_EVALUABLE word (yo_changed, f1_rule=None, f1_flag='none') with no gold → INCOMPLETE."""
        units = [{"type": "text", "text": "Елка."}]
        setup_book(tmp_path, monkeypatch, units)
        monkeypatch.setattr(evaluation, "_load_context",
                            lambda _: predictions(context_for(units, synth={"Елка.": "Ёлка."})))
        evaluation.sample({})
        # Intentionally skip merge → missing gold label
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_labels"] == 1
        assert result["counts"]["missing_yo_verdicts"] == 0  # config={} → NONE_obs → not YO_EVALUABLE
        assert result["metrics"] is None


class TestT38YoSidecarFpCheck:
    """Oracle tests for YO-part of score(): observer-based YO_EVALUABLE, verdict by restoration_fp."""

    def _setup_yo_evaluable(self, tmp_path, monkeypatch, form_synth="Ёлка.", merge_gold=True):
        """Set up a YO-evaluable occurrence and monkeypatch _yo_observe_key to return RESTORED_obs.

        Returns (ctx, mock_fp) where mock_fp is the fp the monkeypatched observer returns.
        YO_EVALUABLE: observer returns RESTORED_obs ∧ f1_rule=None ∧ f1_flag='none'.
        """
        units = [{"type": "text", "text": "Елка."}]
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units, synth={"Елка.": form_synth}))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        evaluation.sample({})
        if merge_gold:
            evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        occ = next(iter(ctx.rows))
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, sources, cfg: RESTORED_obs("Ёлка", (0,), mock_fp))
        return ctx, mock_fp

    def _make_sidecar_with_fp(self, fp, pre_respell="Ёлка", indices="0"):
        """Return a valid sidecar row dict with given restoration_fp."""
        h = hashlib.sha256(b"test").hexdigest()
        return {
            "schema_version": "yo-evidence/1",
            "source_key": "01_test|0|0",
            "form_source": "Елка",
            "unit_text_sha256": h,
            "unit_kind": "text",
            "context_sha256": h,
            "restored_form_pre_respell": pre_respell,
            "restored_vowel_indices": indices,
            "observation_contract_version": "yo-observation/1",
            "restoration_fp": fp,
            "norm_content_sha256": h,
            "yo_map_sha256": h,
            "prep_config_sha256": h,
            "yo_correct": "y",
            "labeler": "test",
            "date": "2026-11-15",
        }

    def test_T38a_sidecar_absent_yo_evaluable_is_incomplete(self, tmp_path, monkeypatch):
        """T38a: journal absent when |Y|>0 → treated as empty → no verdict → INCOMPLETE rc 2."""
        self._setup_yo_evaluable(tmp_path, monkeypatch)
        # No sidecar file → yo_data_before=None → treated as empty → verdict_by_fp={}
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 1
        from audiobook import __main__ as _main_mod
        monkeypatch.setattr(_main_mod, "load_config", lambda: {})
        assert evaluation.main(["score"]) == 2

    def test_sidecar_present_wrong_fp_is_incomplete(self, tmp_path, monkeypatch):
        """T38b (scenario а): journal has entry for candidate A, current obs gives fp B → INCOMPLETE."""
        ctx, current_fp = self._setup_yo_evaluable(tmp_path, monkeypatch)
        # Sidecar records stale_fp (candidate A) ≠ current_fp (candidate B) → lookup fails
        stale_fp = hashlib.sha256(b"stale_candidate_A").hexdigest()
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text(evaluation.serialize_yo_evidence([self._make_sidecar_with_fp(stale_fp)]),
                           encoding="utf-8")
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 1

    def test_sidecar_present_no_entry_for_restored_key_is_incomplete(self, tmp_path, monkeypatch):
        """(б): journal present with entries for other fps, none matching current obs → INCOMPLETE."""
        ctx, current_fp = self._setup_yo_evaluable(tmp_path, monkeypatch)
        other_fp = hashlib.sha256(b"other_key_fp").hexdigest()
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text(evaluation.serialize_yo_evidence([self._make_sidecar_with_fp(other_fp)]),
                           encoding="utf-8")
        # verdict_by_fp = {other_fp: row}, current_fp not in it → yo_missing=1
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 1

    def test_sidecar_present_correct_fp_is_complete(self, tmp_path, monkeypatch):
        """T38c: sidecar has entry with fp matching current observation → COMPLETE."""
        ctx, current_fp = self._setup_yo_evaluable(tmp_path, monkeypatch)
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text(evaluation.serialize_yo_evidence([self._make_sidecar_with_fp(current_fp)]),
                           encoding="utf-8")
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 0
        assert result["metrics"] is not None

    def test_fp_uses_pre_respell_form_not_form_synth(self, tmp_path, monkeypatch):
        """T38d: form_synth ≠ pre-respell; observer's fp (pre-respell based) used for lookup → COMPLETE."""
        # Observer monkeypatched to return RESTORED_obs("Ёлка", fp=mock_fp) regardless of form_synth.
        # Score() must use the observer's fp for sidecar lookup; form_synth must not be consulted.
        ctx, pre_respell_fp = self._setup_yo_evaluable(tmp_path, monkeypatch, form_synth="Ёлка.")
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text(evaluation.serialize_yo_evidence([self._make_sidecar_with_fp(pre_respell_fp)]),
                           encoding="utf-8")
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 0

    def test_yo_from_respell_only_needs_no_verdict(self, tmp_path, monkeypatch):
        """T38e: form_synth has ё (from respell only); real observer with config={} → NONE_obs → COMPLETE."""
        # Real observer (not monkeypatched): config={} → yo_restore=False → NONE_obs → not YO_EVALUABLE
        units = [{"type": "text", "text": "Елка."}]
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units, synth={"Елка.": "Ёлка."}))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        evaluation.sample({})
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        # No sidecar, real observer → NONE_obs → yo_missing=0 → COMPLETE
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 0

    def test_yo_evaluable_independent_of_gold_label(self, tmp_path, monkeypatch):
        """(в): missing_yo_verdicts is counted regardless of active gold stress label."""
        units = [{"type": "text", "text": "Елка."}]
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units, synth={"Елка.": "Ёлка."}))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        evaluation.sample({})
        occ = next(iter(ctx.rows))
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, sources, cfg: RESTORED_obs("Ёлка", (0,), mock_fp))
        # WITHOUT gold label: both missing_labels and missing_yo_verdicts are 1
        result_no_gold = evaluation.score({})
        assert result_no_gold["counts"]["missing_yo_verdicts"] == 1
        assert result_no_gold["counts"]["missing_labels"] == 1
        # WITH gold label: missing_labels=0 but missing_yo_verdicts=1 (Y is same)
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        result_with_gold = evaluation.score({})
        assert result_with_gold["counts"]["missing_yo_verdicts"] == 1
        assert result_with_gold["counts"]["missing_labels"] == 0


class TestT41YoSidecarMutation:
    def test_yo_sidecar_mutated_during_score_errors_no_overwrite(self, tmp_path, monkeypatch):
        """T41: yo sidecar mutated between pin and freshness check → YO_OUTPUT_CHANGED; score not overwritten."""
        units = [{"type": "text", "text": "Слово."}]
        ready(tmp_path, monkeypatch, units=units)
        complete(tmp_path)
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text("\t".join(evaluation.YO_FIELDS) + "\n", encoding="utf-8")
        evaluation.score({})
        old_score = score_path().read_bytes()
        original_assert = evaluation._assert_current
        def mutate_and_assert(context, config):
            yo_path.write_bytes(b"mutated by test")
            original_assert(context, config)
        monkeypatch.setattr(evaluation, "_assert_current", mutate_and_assert)
        with pytest.raises(AnnotationError, match="YO_OUTPUT_CHANGED"):
            evaluation.score({})
        assert score_path().read_bytes() == old_score


class TestT42Oracles:
    def test_all_ambiguous_complete_inconclusive(self, tmp_path, monkeypatch):
        """T42a: all ambiguous/unknown_name gold → COMPLETE, G_hint=INCONCLUSIVE."""
        units = [{"type": "text", "text": "Слово."}, {"type": "text", "text": "Имя."}]
        ready(tmp_path, monkeypatch, units=units)
        rows = todo_rows()
        evaluation.merge({}, write_input(tmp_path, [
            labeled(rows[0], "ambiguous"), labeled(rows[1], "unknown_name")
        ]))
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["gates"]["G_hint"] == "INCONCLUSIVE"

    def test_no_yo_evaluable_no_sidecar_gives_yo_no_evidence(self, tmp_path, monkeypatch):
        """T42b: zero YO_EVALUABLE words, absent sidecar → COMPLETE, YO==YO_NO_EVIDENCE."""
        units = [{"type": "text", "text": "Слово."}]
        ready(tmp_path, monkeypatch, units=units)
        complete(tmp_path)
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert result["gates"]["YO"] == "YO_NO_EVIDENCE"

    @pytest.mark.parametrize("k,n,expected_lower", [
        (40, 40, 0.9124),
        (92, 100, 0.8500),
        (91, 100, 0.8377),
        (73, 73, 0.9500),
    ])
    def test_wilson_lower_bound_matches_adr_reference(self, k, n, expected_lower):
        """T42c: Wilson 95% lower bound matches ADR §7 reference values (4-decimal rounding)."""
        lo, _ = stress_metrics.wilson_interval(k, n)
        assert round(lo, 4) == expected_lower


# (д) AST guard: _yo_check body must not access form_synth or yo_changed; must call _yo_observe_key.
# score() must call _yo_check. _yo_observe_key must call observe_su.
def test_score_yo_part_ast_guard():
    import ast, inspect, textwrap
    import audiobook.stress_eval as _se

    def _func_body_src(fn):
        src = inspect.getsource(fn)
        return textwrap.dedent(src)

    # _yo_check must NOT access form_synth or yo_changed
    yo_check_src = _func_body_src(_se._yo_check)
    yo_check_tree = ast.parse(yo_check_src)
    names_in_yo_check = {n.id for n in ast.walk(yo_check_tree) if isinstance(n, ast.Name)}
    attr_in_yo_check = {n.attr for n in ast.walk(yo_check_tree) if isinstance(n, ast.Attribute)}
    forbidden = names_in_yo_check | attr_in_yo_check
    assert "form_synth" not in forbidden, "_yo_check must not access form_synth"
    assert "yo_changed" not in forbidden, "_yo_check must not access yo_changed"

    # _yo_check must call _yo_observe_key
    calls_in_yo_check = [
        n.func.id if isinstance(n.func, ast.Name) else
        (n.func.attr if isinstance(n.func, ast.Attribute) else "")
        for n in ast.walk(yo_check_tree) if isinstance(n, ast.Call)
    ]
    assert "_yo_observe_key" in calls_in_yo_check, "_yo_check must call _yo_observe_key"

    # score() must call _yo_check (search for the call in score body)
    score_src = _func_body_src(_se.score)
    score_tree = ast.parse(score_src)
    score_calls = [
        n.func.id if isinstance(n.func, ast.Name) else
        (n.func.attr if isinstance(n.func, ast.Attribute) else "")
        for n in ast.walk(score_tree) if isinstance(n, ast.Call)
    ]
    assert "_yo_check" in score_calls, "score() must call _yo_check"

    # _yo_observe_key must call observe_su
    observe_key_src = _func_body_src(_se._yo_observe_key)
    observe_key_tree = ast.parse(observe_key_src)
    observe_key_calls = [
        n.func.id if isinstance(n.func, ast.Name) else
        (n.func.attr if isinstance(n.func, ast.Attribute) else "")
        for n in ast.walk(observe_key_tree) if isinstance(n, ast.Call)
    ]
    assert "observe_su" in observe_key_calls, "_yo_observe_key must call observe_su"
