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


def _yo_sidecar_row(fp=None, *, source_key="01_test|0|0", yo_correct="y", identity=None,
                    restored_form="Ёлка", restored_indices="0"):
    """Return a valid yo_evidence sidecar row.

    If identity is supplied, use its five source-identity fields (authentic row).
    If fp is None, compute it from identity+restored_form+restored_indices automatically.
    """
    from audiobook.stress_yo_observer import restoration_fp as _rfp
    h = hashlib.sha256(b"test").hexdigest()
    base_id = {"source_key": source_key, "form_source": "Елка",
               "unit_text_sha256": h, "unit_kind": "text", "context_sha256": h}
    if identity is not None:
        for k in ("source_key", "form_source", "unit_text_sha256", "unit_kind", "context_sha256"):
            base_id[k] = identity[k]
    if fp is None:
        fp = _rfp(base_id, restored_form, [int(p) for p in restored_indices.split("|")])
    return {
        "schema_version": "yo-evidence/1", **base_id,
        "restored_form_pre_respell": restored_form,
        "restored_vowel_indices": restored_indices,
        "observation_contract_version": "yo-observation/1",
        "restoration_fp": fp, "norm_content_sha256": h, "yo_map_sha256": h,
        "prep_config_sha256": h, "yo_correct": yo_correct, "labeler": "test",
        "date": "2026-11-15",
    }


def _patch_yo_obs(monkeypatch, ctx):
    """Monkeypatch _yo_observe_key to return RESTORED_obs for the first occurrence; return (mock_fp, identity)."""
    from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
    occ = next(iter(ctx.rows))
    identity = ctx.sources.resolve(occ.source_key)[0]
    mock_fp = _rfp(identity, "Ёлка", [0])
    monkeypatch.setattr(evaluation, "_yo_observe_key",
                        lambda o, sources, cfg: RESTORED_obs("Ёлка", (0,), mock_fp))
    return mock_fp, identity


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
    return next((paths.OUT / "stress" / "eval" / "score").glob("s2-*.json"))


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
    assert set(result) == {"schema", "source_fp", "analysis_fp", "sample_fp",
                           "eligible_assignment_sha256", "selected_by_stratum_sha256",
                           "inventory_generation_fp", "observation_contract_version",
                           "norm_content_sha256", "yo_map_sha256", "prep_config_sha256",
                           "gold_sha256", "yo_evidence_sha256",
                           "counts", "metrics", "wilson", "gates", "status"}
    assert result["schema"] == "stress-score/2"
    assert result["yo_evidence_sha256"] is None
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
            _update_manifest(units)
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
    _update_manifest(units)
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


@pytest.mark.parametrize("label,correct", [("0", True), ("1", False), ("variants:0|1", True), ("yo", True)])
def test_accepted_gold_variants_and_synth_yo(tmp_path, monkeypatch, label, correct):
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    ctx = predictions(context_for(units, synth={"Елка.": "Ёлка."}))
    monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
    evaluation.sample({})
    evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], label, yo_correct="y")]))
    # YO restoration enabled: observer confirms RESTORED_obs; sidecar verdict present → yo_missing=0.
    mock_fp, identity = _patch_yo_obs(monkeypatch, ctx)
    yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
    yo_path.write_text(evaluation.serialize_yo_evidence([_yo_sidecar_row(mock_fp, identity=identity)]), encoding="utf-8")
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
    # YO restoration enabled: Елка is in sample (omograph stratum); observer confirms RESTORED_obs.
    # Sidecar verdict present → yo_missing=0. YO_WARN comes from yo_correct="n" in gold (wrong verdict).
    mock_fp, identity = _patch_yo_obs(monkeypatch, context)
    yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
    yo_path.write_text(evaluation.serialize_yo_evidence([_yo_sidecar_row(mock_fp, yo_correct="n", identity=identity)]),
                       encoding="utf-8")
    result = evaluation.score({})
    metrics = result["metrics"]["overall"]
    assert (metrics["suggestion_precision"]["k"], metrics["suggestion_precision"]["n"]) == (0, 1)
    assert (metrics["override_disagreement"]["k"], metrics["override_disagreement"]["n"]) == (1, 1)
    assert (metrics["yo_precision"]["k"], metrics["yo_precision"]["n"]) == (0, 2)
    assert result["gates"]["YO"] == "YO_WARN"
    assert result["counts"]["by_stratum"]["yo_changed"]["selected"] == 0
    assert result["metrics"]["book_estimates"]["suggestion_precision"] == {
        "rate": 0, "covered_population": 1, "total_population": 2}


@pytest.mark.parametrize("fault", ["sample", "source_fp", "analysis_fp", "gold", "conflict", "yo_unstressed", "stale_generation"])
def test_validation_error_never_publishes_or_rewrites_old_score(tmp_path, monkeypatch, fault):
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    evaluation.score({})
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json"))
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
                next((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json")).write_text("{}", encoding="utf-8")
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
        """T29: YO_EVALUABLE word (RESTORED_obs, f1_rule=None, f1_flag='none') with no gold → INCOMPLETE.

        Both missing_labels=1 (no stress label) and missing_yo_verdicts=1 (no sidecar verdict) are 1.
        """
        units = [{"type": "text", "text": "Елка."}]
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units, synth={"Елка.": "Ёлка."}))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        # Observer patched BEFORE sample so stored assignment matches fresh recompute.
        _patch_yo_obs(monkeypatch, ctx)
        evaluation.sample({})
        # Intentionally skip merge → missing gold label
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_labels"] == 1
        assert result["counts"]["missing_yo_verdicts"] == 1  # RESTORED_obs, no sidecar verdict
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
        occ = next(iter(ctx.rows))
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        identity = ctx.sources.resolve(occ.source_key)[0]
        self._identity = identity
        mock_fp = _rfp(identity, "Ёлка", [0])
        # Patch BEFORE sample so stored eligible assignment includes "yo_changed" stratum,
        # matching what _verify_selection_fresh recomputes at score time.
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, sources, cfg: RESTORED_obs("Ёлка", (0,), mock_fp))
        evaluation.sample({})
        if merge_gold:
            evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        return ctx, mock_fp

    def _make_sidecar_with_fp(self, fp, pre_respell="Ёлка", indices="0"):
        """Return a valid sidecar row dict with given restoration_fp."""
        return _yo_sidecar_row(fp, identity=self._identity, restored_form=pre_respell, restored_indices=indices)

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
        """T38b: journal has authentic entry for candidate A (old fp), current obs gives candidate B (new fp) → INCOMPLETE."""
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        # "Еле." has two е-vowels: index 0 → "Ёле", index 1 → "Елё" — so old/new fps differ.
        units = [{"type": "text", "text": "Еле."}]
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units, synth={"Еле.": "Ёле."}))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        occ = next(iter(ctx.rows))
        identity = ctx.sources.resolve(occ.source_key)[0]
        self._identity = identity
        old_fp = _rfp(identity, "Ёле", [0])
        new_fp = _rfp(identity, "Елё", [1])
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, sources, cfg: RESTORED_obs("Елё", (1,), new_fp))
        evaluation.sample({})
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text(
            evaluation.serialize_yo_evidence([
                _yo_sidecar_row(old_fp, identity=identity, restored_form="Ёле", restored_indices="0")
            ]),
            encoding="utf-8",
        )
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 1

    def test_sidecar_present_no_entry_for_restored_key_is_incomplete(self, tmp_path, monkeypatch):
        """(б): journal present but empty (header-only), no entry for current fp → INCOMPLETE."""
        self._setup_yo_evaluable(tmp_path, monkeypatch)
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text("\t".join(evaluation.YO_FIELDS) + "\n", encoding="utf-8")
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
        occ = next(iter(ctx.rows))
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        # Patch BEFORE sample so stored and fresh assignments agree.
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, sources, cfg: RESTORED_obs("Ёлка", (0,), mock_fp))
        evaluation.sample({})
        # WITHOUT gold label: both missing_labels and missing_yo_verdicts are 1
        result_no_gold = evaluation.score({})
        assert result_no_gold["counts"]["missing_yo_verdicts"] == 1
        assert result_no_gold["counts"]["missing_labels"] == 1
        # WITH gold label: missing_labels=0 but missing_yo_verdicts=1 (Y is same)
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        result_with_gold = evaluation.score({})
        assert result_with_gold["counts"]["missing_yo_verdicts"] == 1
        assert result_with_gold["counts"]["missing_labels"] == 0

    def test_conflicting_same_fp_returns_error_without_score_overwrite(self, tmp_path, monkeypatch):
        """F1-reg: two sidecar rows with same restoration_fp but opposite y/n → YO_EVIDENCE_CONFLICT; score not overwritten."""
        ctx, mock_fp = self._setup_yo_evaluable(tmp_path, monkeypatch)
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        yo_path.write_text(
            evaluation.serialize_yo_evidence([_yo_sidecar_row(mock_fp, yo_correct="y", identity=self._identity)]),
            encoding="utf-8",
        )
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        score_before = score_path().read_bytes()
        # Two rows: same fp, opposite verdicts → conflict must be detected
        yo_path.write_text(
            evaluation.serialize_yo_evidence([
                _yo_sidecar_row(mock_fp, yo_correct="y", identity=self._identity),
                _yo_sidecar_row(mock_fp, yo_correct="n", identity=self._identity),
            ]),
            encoding="utf-8",
        )
        with pytest.raises(AnnotationError, match="YO_EVIDENCE_CONFLICT"):
            evaluation.score({})
        assert score_path().read_bytes() == score_before

    @pytest.mark.parametrize("first,second", [("y", "n"), ("n", "y")])
    def test_yo_conflict_both_orderings_score_and_protected_files_unchanged(
        self, tmp_path, monkeypatch, first, second
    ):
        """Integration: YO_EVIDENCE_CONFLICT detected via public score() in both row orderings.

        Both rows share the same source_key/identity/restoration_fp (internally consistent);
        they differ only in yo_correct and labeler. TSV is written with explicit row order
        (bypassing serialize_yo_evidence sorting) so both [y,n] and [n,y] orderings are tested.
        Verifies that score, gold ledger, and YO-evidence journal are all byte-identical
        after the failed score() call — no partial writes to any protected file.
        """
        ctx, mock_fp = self._setup_yo_evaluable(tmp_path, monkeypatch)
        gold_path = paths.TEXT / "stress_gold.tsv"
        yo_path = paths.TEXT / "stress_gold.yo_evidence.tsv"

        # Establish a COMPLETE score baseline with a single non-conflicting sidecar entry.
        yo_path.write_text(
            evaluation.serialize_yo_evidence([_yo_sidecar_row(mock_fp, yo_correct=first, identity=self._identity)]),
            encoding="utf-8",
        )
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"

        # Snapshot score and gold before the conflicting call.
        score_before = score_path().read_bytes()
        gold_before = gold_path.read_bytes()

        # Build two internally consistent rows: same source_key/identity/fp, different yo_correct.
        # Different labeler makes each row distinct; both pass validate_yo_row individually.
        row_first = {**_yo_sidecar_row(mock_fp, yo_correct=first, identity=self._identity), "labeler": "labeler-a"}
        row_second = {**_yo_sidecar_row(mock_fp, yo_correct=second, identity=self._identity), "labeler": "labeler-b"}
        assert evaluation.validate_yo_row(row_first)
        assert evaluation.validate_yo_row(row_second)

        # Write TSV with explicit ordering (not serialize_yo_evidence which sorts rows).
        tsv_lines = ["\t".join(evaluation.YO_FIELDS)]
        for row in (row_first, row_second):
            tsv_lines.append("\t".join(row[f] for f in evaluation.YO_FIELDS))
        yo_path.write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")

        # Snapshot YO-journal bytes AFTER writing the conflicting content, before score().
        yo_conflict_before = yo_path.read_bytes()

        with pytest.raises(AnnotationError, match="YO_EVIDENCE_CONFLICT"):
            evaluation.score({})

        # All three protected files must remain byte-identical after the failed call.
        assert score_path().read_bytes() == score_before, "score file must not change on conflict"
        assert gold_path.read_bytes() == gold_before, "gold ledger must not change on conflict"
        assert yo_path.read_bytes() == yo_conflict_before, "YO-journal must not change on conflict"


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

    # B2: _yo_observe_key returns UNSUPPORTED until WordOcc gains raw_fragment from chunk manifest;
    # observe_su call is deferred. Guard that it returns UNSUPPORTED_obs, not some silent wrong path.
    from audiobook.stress_yo_observer import UNSUPPORTED_obs
    from types import SimpleNamespace
    dummy_occ = SimpleNamespace(source_key="01_test|0|0")
    dummy_sources = SimpleNamespace(resolve=lambda k: None)
    result = _se._yo_observe_key(dummy_occ, dummy_sources, {})
    assert isinstance(result, UNSUPPORTED_obs), "_yo_observe_key must return UNSUPPORTED_obs (B2: no raw fragment)"


def test_f5_lock_unavailable_score_errors_no_overwrite(tmp_path, monkeypatch):
    """F5: EVAL_LOCK_UNAVAILABLE from acquire_eval_lock → score raises; score file not changed."""
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    evaluation.score({})
    score_before = score_path().read_bytes()
    before = snapshot(tmp_path)

    def lock_fail(*a, **kw):
        raise AnnotationError("EVAL_LOCK_UNAVAILABLE")

    monkeypatch.setattr(evaluation, "acquire_eval_lock", lock_fail)
    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        evaluation.score({})
    assert score_path().read_bytes() == score_before
    assert snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# B3: merge_yo freshness check (observer must confirm restoration)
# ---------------------------------------------------------------------------

def test_b3_merge_yo_stale_fp_rejected_even_if_internally_consistent(tmp_path, monkeypatch):
    """B3: internally consistent YO row is rejected when observer no longer confirms restoration."""
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    from audiobook.stress_yo_observer import NONE_obs, restoration_fp as _rfp
    # Monkeypatch observer to return NONE_obs (restoration no longer observed for this occ).
    monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())
    ctx = context_for(units, synth={"Елка.": "Ёлка."})
    occ = ctx.rows[0]
    identity = ctx.sources.resolve(occ.source_key)[0]
    fp = _rfp(identity, "Ёлка", [0])
    h = hashlib.sha256(b"test").hexdigest()
    yo_row = {
        "schema_version": "yo-evidence/1", "source_key": occ.source_key,
        "form_source": occ.form_source, "unit_text_sha256": identity["unit_text_sha256"],
        "unit_kind": identity["unit_kind"], "context_sha256": identity["context_sha256"],
        "restored_form_pre_respell": "Ёлка", "restored_vowel_indices": "0",
        "observation_contract_version": "yo-observation/1",
        "restoration_fp": fp, "norm_content_sha256": h, "yo_map_sha256": h,
        "prep_config_sha256": h, "yo_correct": "y", "labeler": "test", "date": "2026-11-15",
    }
    yo_path = tmp_path / "incoming.tsv"
    yo_path.write_text(evaluation.serialize_yo_evidence([yo_row]), encoding="utf-8")
    # Observer says no restoration → fp can't be verified fresh → YO_STALE_INPUT; no write.
    with pytest.raises(AnnotationError, match="YO_STALE_INPUT"):
        evaluation.merge_yo({}, yo_path)
    assert not (paths.TEXT / "stress_gold.yo_evidence.tsv").exists()


# ---------------------------------------------------------------------------
# B4: score() rejects stale sample/2 observation inputs
# ---------------------------------------------------------------------------

def test_b4_score_rejects_sample_with_stale_observation_inputs(tmp_path, monkeypatch):
    """B4: score() raises SAMPLE_STALE when norm/yo_map/prep_config digest changed since sample."""
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    score_dir = paths.OUT / "stress" / "eval" / "score"
    # Simulate norm_digest change by writing a .norm.txt file into paths.TEXT.
    (paths.TEXT / "synthetic.norm.txt").write_bytes(b"changed content")
    with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
        evaluation.score({})
    # Score file must not have been written.
    assert not score_dir.exists() or not any(score_dir.glob("s2-*.json"))


# ---------------------------------------------------------------------------
# Helpers shared by #13 / #10 / #11 regression tests
# ---------------------------------------------------------------------------

def _update_manifest(units):
    """Rewrite manifest.jsonl in paths.OUT/sections/01_test to match current units."""
    mdir = paths.OUT / "sections" / "01_test"
    mdir.mkdir(parents=True, exist_ok=True)
    with (mdir / "manifest.jsonl").open("w", encoding="utf-8") as mf:
        for i, unit in enumerate(units):
            mf.write(json.dumps({"id": f"{i+1:04d}", "n": i + 1,
                                 "text": unit["text"], "pause_after_ms": 900}) + "\n")


# ---------------------------------------------------------------------------
# Issue #10 regression: _check_todo_v2 must reject different bytes unconditionally
# ---------------------------------------------------------------------------

def test_t10_reg_different_bytes_blank_todo_raises_protected(tmp_path, monkeypatch):
    """T10-reg: existing todo with different bytes and no unmerged labels → OWNER_TODO_PROTECTED.

    Before fix: returned 'create'. After fix: raises OWNER_TODO_PROTECTED.
    """
    monkeypatch.setattr(evaluation, "private_output_guard", lambda p: None)
    todo_path = tmp_path / "stress_gold.todo.s2-fp16.tsv"
    blank_row = {f: "" for f in evaluation.GOLD_FIELDS}
    blank_row.update(source_key="01_test|0|0", form_source="слово",
                     unit_text_sha256="a" * 64, unit_kind="text",
                     context_sha256="b" * 64, context="тест")
    content = evaluation.serialize_gold([blank_row], allow_blank=True)
    todo_path.write_bytes(content.encode("utf-8"))
    with pytest.raises(AnnotationError, match="OWNER_TODO_PROTECTED"):
        evaluation._check_todo_v2(todo_path, [], [])


# ---------------------------------------------------------------------------
# Issue #13 regression: _yo_observe_key must use manifest, not unit text
# ---------------------------------------------------------------------------

def test_t13_reg_yo_observe_key_uses_manifest_not_stub(tmp_path, monkeypatch):
    """T13-reg: _yo_observe_key returns RESTORED_obs from manifest when YO map active.

    Before fix this returned UNSUPPORTED_obs("RAW_FRAGMENT_UNAVAILABLE").
    """
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    # norm.txt that makes build_map return {"елка": "ёлка"}.
    (paths.TEXT / "yo.norm.txt").write_text("елка ёлка ёлка\n", encoding="utf-8")
    from audiobook.stress_yo_observer import RESTORED_obs
    ctx = context_for(units)
    occ = ctx.rows[0]
    config = {"text_prep": {"yo_restore": True}}
    result = evaluation._yo_observe_key(occ, ctx.sources, config)
    assert isinstance(result, RESTORED_obs), f"Expected RESTORED_obs, got {result}"


def test_t13_reg_unsupported_obs_raises_in_yo_check(tmp_path, monkeypatch):
    """T13-reg: UNSUPPORTED from _yo_observe_key → score() raises YO_OBSERVER_UNSUPPORTED (fail closed)."""
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    from audiobook import stress_yo_observer as _obs
    monkeypatch.setattr(evaluation, "_yo_observe_key",
                        lambda o, s, c: _obs.UNSUPPORTED_obs("MANIFEST_UNAVAILABLE"))
    evaluation.sample({})
    with pytest.raises(AnnotationError, match="YO_OBSERVER_UNSUPPORTED"):
        evaluation.score({})




# ---------------------------------------------------------------------------
# Issue #11 regression: score result must include full ADR §5.5 schema fields
# ---------------------------------------------------------------------------

def test_t11_reg_score_result_has_full_schema(tmp_path, monkeypatch):
    """T11-reg: score result must include eligible_assignment_sha256, inventory_generation_fp etc.

    Before fix: these fields absent from result dict. After fix: present.
    """
    ready(tmp_path, monkeypatch)
    complete(tmp_path)
    result = evaluation.score({})
    required = {"eligible_assignment_sha256", "selected_by_stratum_sha256",
                "inventory_generation_fp", "observation_contract_version",
                "norm_content_sha256", "yo_map_sha256", "prep_config_sha256"}
    missing = required - set(result)
    assert not missing, f"Missing fields in score result: {missing}"


def test_t11_reg_stale_eligible_assignment_raises_sample_stale(tmp_path, monkeypatch):
    """T11-reg: _verify_selection_fresh raises SAMPLE_STALE when stored and fresh sample_fp differ.

    Directly unit-tests the function: stored sample_fp is intentionally wrong (simulates
    any kind of staleness — observer change, assignment change, etc.).
    """
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    ctx = context_for(units)
    from audiobook.stress_yo_observer import NONE_obs
    obs_map = {occ.source_key: NONE_obs()
               for occ in ctx.rows
               if occ.alignment_status == "aligned" and evaluation.vowel_count(occ.form_analysis) >= 2}
    fresh_sel = evaluation.select_sample_v2(
        ctx.rows, ctx.source_fp, ctx.analysis_fp,
        homographs=ctx.homographs, names=ctx.names, obs_map=obs_map,
        norm_digest="a" * 64, yo_map_digest="b" * 64, prep_config_digest="c" * 64,
    )
    stored = {**fresh_sel.record,
              "sample_fp": "0" * 64,  # Corrupt fp: won't match fresh computation.
              "observation_inputs": {"norm_content_sha256": "a" * 64,
                                     "yo_map_sha256": "b" * 64, "prep_config_sha256": "c" * 64}}
    monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())
    with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
        evaluation._verify_selection_fresh(stored, ctx, {})


# ---------------------------------------------------------------------------
# Gate B2 / R4: score() independently authenticates every stored YO-evidence row
# ---------------------------------------------------------------------------

def _r4_snapshot(root):
    """Record bytes AND existence, including absent protected publication paths."""
    expected = {paths.TEXT / name for name in (
        "stress_gold.tsv", "stress_gold.yo_evidence.tsv", "stress_gold.archive.tsv",
        "stress_gold.todo.tsv", "stress_gold.yo.todo.tsv")}
    expected.update(p for p in root.rglob("*") if p.is_file())
    samples = list((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json"))
    assert samples, "Saved sample must be present in the protected snapshot"
    expected.update(paths.OUT / "stress" / "eval" / "score" / p.name for p in samples)
    return {p: (p.exists(), p.read_bytes() if p.exists() else None) for p in expected}


class TestGateB2R4:
    """Approved R4-T01..T12 oracles; all inputs are synthetic."""

    def _setup(self, tmp_path, monkeypatch):
        """Book + sample + gold with RESTORED_obs patched; return (ctx, mock_fp, identity)."""
        units = [{"type": "text", "text": "Елка."}]
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units, synth={"Елка.": "Ёлка."}))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        occ = next(iter(ctx.rows))
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, sources, cfg: RESTORED_obs("Ёлка", (0,), mock_fp))
        evaluation.sample({})
        evaluation.merge({}, write_input(tmp_path, [labeled(todo_rows()[0], "0", yo_correct="y")]))
        # Synthetic protected outputs ensure error snapshots check existing bytes too.
        (paths.TEXT / "stress_gold.yo.todo.tsv").write_bytes(b"synthetic pending verdicts\n")
        evidence = paths.OUT / "stress" / "eval" / "evidence" / "synthetic.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b"{}\n")
        return ctx, mock_fp, identity

    def _write(self, rows):
        path = paths.TEXT / "stress_gold.yo_evidence.tsv"
        path.write_text("\t".join(evaluation.YO_FIELDS) + "\n" + "".join(
            "\t".join(row[f] for f in evaluation.YO_FIELDS) + "\n" for row in rows), encoding="utf-8")

    def _error_unchanged(self, root, monkeypatch, code):
        from audiobook import __main__ as cli
        monkeypatch.setattr(cli, "load_config", lambda: {})
        before = _r4_snapshot(root)
        with pytest.raises(AnnotationError, match=code):
            evaluation.score({})
        assert _r4_snapshot(root) == before
        assert evaluation.main(["score"]) == 1
        assert _r4_snapshot(root) == before

    def test_T01_missing(self, tmp_path, monkeypatch):
        from audiobook import __main__ as cli
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(cli, "load_config", lambda: {})
        before = _r4_snapshot(tmp_path)
        assert evaluation.main(["score"]) == 2
        result = json.loads(score_path().read_bytes())
        assert result["status"] == "INCOMPLETE"
        assert all(result[k] is None for k in ("metrics", "wilson", "gates"))
        after = _r4_snapshot(tmp_path)
        assert {p: v for p, v in after.items() if p != score_path()} == {
            p: v for p, v in before.items() if p != score_path()}

    @pytest.mark.parametrize("prior_score", [False, True])
    def test_T02_empty(self, tmp_path, monkeypatch, prior_score):
        self._setup(tmp_path, monkeypatch)
        if prior_score:
            evaluation.score({})
        (paths.TEXT / "stress_gold.yo_evidence.tsv").write_bytes(b"")
        self._error_unchanged(tmp_path, monkeypatch, "YO_EVIDENCE_INVALID")

    @pytest.mark.parametrize("field,value", [
        ("restoration_fp", "0" * 64), ("unit_text_sha256", "1" * 64),
        ("context_sha256", "2" * 64), ("source_key", "02_other|0|0"),
        ("unit_kind", "heading"), ("form_source", "Елке"),
        ("restored_form_pre_respell", "Ёлкё"), ("restored_vowel_indices", "1")])
    @pytest.mark.parametrize("prior_score", [False, True])
    def test_T03_T04_tampered(self, tmp_path, monkeypatch, field, value, prior_score):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        if prior_score:
            evaluation.score({})
        self._write([{**_yo_sidecar_row(identity=identity), field: value}])
        self._error_unchanged(tmp_path, monkeypatch, "YO_EVIDENCE_INVALID")

    @pytest.mark.parametrize("source,candidate,indices", [
        ("Елка", "Ёлкё", "0|1"), ("Еее", "Ёёе", "0"),
        ("Елка", "ёлка", "0"), ("Елка", "ЁЛка", "0"),
        ("Елка", "Ёлкаа", "0"), ("Елка", "Елка", "0"),
        ("Ёлка", "Ёлка", "0"), ("Елка", "Ёлка", "5"),
        ("Еее", "Ёёе", "1|0"), ("Еее", "Ёёе", "0|0|1"),
        ("Еее", "Ёее", "1"), ("Елка", "Е\u0308лка", "0")])
    @pytest.mark.parametrize("prior_score", [False, True])
    def test_T05_semantic_invalid(self, tmp_path, monkeypatch, source, candidate, indices, prior_score):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        if prior_score:
            evaluation.score({})
        # Fingerprint matches the forged payload, so hashing alone cannot catch it.
        self._write([_yo_sidecar_row(identity={**identity, "form_source": source},
                                    restored_form=candidate, restored_indices=indices)])
        self._error_unchanged(tmp_path, monkeypatch, "YO_EVIDENCE_INVALID")

    @pytest.mark.parametrize("reverse", [False, True])
    @pytest.mark.parametrize("prior_score", [False, True])
    def test_T06_historical_conflict(self, tmp_path, monkeypatch, reverse, prior_score):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        if prior_score:
            evaluation.score({})
        historical = {**identity, "source_key": "02_other|0|0", "unit_text_sha256": "1" * 64}
        row = _yo_sidecar_row(identity=historical)
        rows = [row, {**row, "yo_correct": "n"}]
        self._write(rows[::-1] if reverse else rows)
        self._error_unchanged(tmp_path, monkeypatch, "YO_EVIDENCE_CONFLICT")

    @pytest.mark.parametrize("mode", ["header", "schema", "contract", "utf8"])
    @pytest.mark.parametrize("prior_score", [False, True])
    def test_T07_malformed(self, tmp_path, monkeypatch, mode, prior_score, capsys):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        if prior_score:
            evaluation.score({})
        row = _yo_sidecar_row(identity=identity)
        if mode == "schema":
            row["schema_version"] = "yo-evidence/99"
        if mode == "contract":
            row["observation_contract_version"] = "yo-observation/99"
        self._write([row])
        if mode in ("header", "utf8"):
            (paths.TEXT / "stress_gold.yo_evidence.tsv").write_bytes(
                b"wrong header\n" if mode == "header" else b"\xff\n")
        code = "YO_OBSERVATION_UNSUPPORTED" if mode == "contract" else "YO_EVIDENCE_INVALID"
        self._error_unchanged(tmp_path, monkeypatch, code)
        assert code in capsys.readouterr().out

    @pytest.mark.parametrize("change", ["removed", "identity", "candidate"])
    def test_T08_historical_no_transfer(self, tmp_path, monkeypatch, change):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        if change == "removed":
            identity = {**identity, "source_key": "02_other|0|0"}
        elif change == "identity":
            identity = {**identity, "unit_text_sha256": "1" * 64}
        else:
            identity = {**identity, "form_source": "Еле"}
        self._write([_yo_sidecar_row(identity=identity,
                                    restored_form="Ёле" if change == "candidate" else "Ёлка")])
        before = _r4_snapshot(tmp_path)
        result = evaluation.score({})
        assert result["status"] == "INCOMPLETE"
        assert result["counts"]["missing_yo_verdicts"] == 1
        assert all(result[k] is None for k in ("metrics", "wilson", "gates"))
        after = _r4_snapshot(tmp_path)
        assert {p: v for p, v in after.items() if p != score_path()} == {
            p: v for p, v in before.items() if p != score_path()}

    @pytest.mark.parametrize("verdict", ["y", "n"])
    def test_T09_current_idempotent(self, tmp_path, monkeypatch, verdict):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        self._write([_yo_sidecar_row(identity=identity, yo_correct=verdict)])
        result = evaluation.score({})
        assert result["status"] == "COMPLETE"
        assert all(result[k] is not None for k in ("metrics", "wilson", "gates"))
        assert result["metrics"]["overall"]["yo_precision"]["k"] == (verdict == "y")
        assert result["counts"]["yo_wrong"] == (verdict == "n")
        before = _r4_snapshot(tmp_path)
        assert evaluation.score({}) == result
        assert _r4_snapshot(tmp_path) == before

    @pytest.mark.parametrize("verdict", ["y", "n"])
    def test_T10_duplicates(self, tmp_path, monkeypatch, verdict):
        _, _, identity = self._setup(tmp_path, monkeypatch)
        row = _yo_sidecar_row(identity=identity, yo_correct=verdict)
        self._write([row])
        single = evaluation.score({})
        self._write([row, row])
        before = _r4_snapshot(tmp_path)
        duplicate = evaluation.score({})
        for key in ("status", "counts", "metrics", "wilson", "gates"):
            assert duplicate[key] == single[key]
        after = _r4_snapshot(tmp_path)
        assert {p: v for p, v in after.items() if p != score_path()} == {
            p: v for p, v in before.items() if p != score_path()}

    def test_T11_f1_excluded_observer_required(self, tmp_path, monkeypatch):
        from audiobook.stress_yo_observer import UNSUPPORTED_obs
        ctx, _, _ = self._setup(tmp_path, monkeypatch)
        excluded = predictions(ctx, {ctx.rows[0].source_key: {"f1_flag": "excluded"}})
        monkeypatch.setattr(evaluation, "_load_context", lambda _: excluded)
        # New sample is created after exclusion, with no old todo to protect.
        for todo in paths.TEXT.glob("stress_gold.todo.s2-*.tsv"):
            todo.unlink()
        evaluation.sample({})
        assert evaluation.score({})["status"] == "COMPLETE"
        monkeypatch.setattr(evaluation, "_yo_observe_key", lambda *args: UNSUPPORTED_obs("TEST"))
        self._error_unchanged(tmp_path, monkeypatch, "YO_OBSERVER_UNSUPPORTED")

    def test_T12_real_A_B_A(self, tmp_path, monkeypatch):
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp
        _, _, identity_a = self._setup(tmp_path, monkeypatch)
        historical = _yo_sidecar_row(identity=identity_a)
        for field in ("norm_content_sha256", "yo_map_sha256", "prep_config_sha256"):
            historical[field] = "3" * 64
        self._write([historical])
        assert evaluation.score({})["status"] == "COMPLETE"
        for token, candidate, expected in [("Еле", "Ёле", "INCOMPLETE"), ("Елка", "Ёлка", "COMPLETE")]:
            units = [{"type": "text", "text": token + "."}]
            _update_manifest(units)
            ctx = predictions(context_for(units, synth={token + ".": candidate + "."}))
            monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
            identity = ctx.sources.resolve(ctx.rows[0].source_key)[0]
            fp = restoration_fp(identity, candidate, [0])
            calls = []
            def observe(*args):
                calls.append(fp)
                return RESTORED_obs(candidate, (0,), fp)
            monkeypatch.setattr(evaluation, "_yo_observe_key", observe)
            for todo in paths.TEXT.glob("stress_gold.todo.s2-*.tsv"):
                todo.unlink()
            evaluation.sample({})
            todo = todo_rows()
            if todo:
                evaluation.merge({}, write_input(tmp_path, [labeled(todo[0], "0", yo_correct="y")]))
            calls.clear()
            before = _r4_snapshot(tmp_path)
            result = evaluation.score({})
            assert result["status"] == expected
            assert calls, "Reactivation must require a fresh observation"
            target = paths.OUT / "stress" / "eval" / "score" / ("s2-" + result["sample_fp"][:16] + ".json")
            after = _r4_snapshot(tmp_path)
            assert {p: v for p, v in after.items() if p != target} == {
                p: v for p, v in before.items() if p != target}
            if expected == "COMPLETE":
                assert fp == historical["restoration_fp"]
            else:
                assert fp != historical["restoration_fp"]
                assert all(result[k] is None for k in ("metrics", "wilson", "gates"))


# ---------------------------------------------------------------------------
# R9-T01..T10: B4 final publication fence
# ---------------------------------------------------------------------------

class TestR9FinalPublicationFence:
    """R9: B4 final publication fence — fence fires for all R9 coverage points."""

    def test_t01_prep_config_drift_raises_sample_stale(self, tmp_path, monkeypatch):
        """T01: prep config changes between _assert_current and fence → SAMPLE_STALE."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx, cfg):
            orig(ctx, cfg)
            cfg["text_prep"] = {"yo_restore": True}  # prep digest drifts in fence

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})
        assert score_path().read_bytes() == old_score

    def test_t02_yo_map_drift_raises_sample_stale(self, tmp_path, monkeypatch):
        """T02: YO-map content changes between _assert_current and fence → SAMPLE_STALE."""
        from audiobook.stress_yo_observer import NONE_obs
        units = setup_book(tmp_path, monkeypatch)
        (paths.TEXT / "yo.norm.txt").write_text("елка ёлка ёлка\n", encoding="utf-8")
        config = {"text_prep": {"yo_restore": True}}
        monkeypatch.setattr(evaluation, "_load_context",
                            lambda _: predictions(context_for(units)))
        monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())
        evaluation.sample(config)
        complete(tmp_path)
        evaluation.score(config)
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx, cfg):
            orig(ctx, cfg)
            (paths.TEXT / "yo.norm.txt").write_text(
                "елка ёлка ёлка\nберёза береза береза\n", encoding="utf-8")

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score(config)
        assert score_path().read_bytes() == old_score

    def test_t03_norm_content_drift_raises_sample_stale(self, tmp_path, monkeypatch):
        """T03: norm file content changes between _assert_current and fence → SAMPLE_STALE."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx, cfg):
            orig(ctx, cfg)
            (paths.TEXT / "extra.norm.txt").write_text("injected\n", encoding="utf-8")

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})
        assert score_path().read_bytes() == old_score

    def test_t04_per_key_witness_drift_raises_sample_stale(self, tmp_path, monkeypatch):
        """T04: per-key observer returns different result at fence → SAMPLE_STALE."""
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs, restoration_fp as _rfp
        units = setup_book(tmp_path, monkeypatch)
        (paths.TEXT / "yo.norm.txt").write_text("елка ёлка ёлка\n", encoding="utf-8")
        config = {"text_prep": {"yo_restore": True}}
        ctx = predictions(context_for(units))
        occ = ctx.rows[0]
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, s, c: RESTORED_obs("Ёлка", (0,), mock_fp))
        evaluation.sample(config)
        complete(tmp_path)
        evaluation.score(config)
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx2, cfg):
            orig(ctx2, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score(config)
        assert score_path().read_bytes() == old_score

    def test_t04b_restored_to_different_restored_raises_sample_stale(self, tmp_path, monkeypatch):
        """T04b: RESTORED(A) → RESTORED(B) with different form/indices/fp at fence → SAMPLE_STALE."""
        from audiobook.stress_yo_observer import RESTORED_obs, restoration_fp as _rfp
        units = setup_book(tmp_path, monkeypatch)
        (paths.TEXT / "yo.norm.txt").write_text("елка ёлка ёлка\n", encoding="utf-8")
        config = {"text_prep": {"yo_restore": True}}
        ctx = predictions(context_for(units))
        occ = ctx.rows[0]
        identity = ctx.sources.resolve(occ.source_key)[0]
        fp_a = _rfp(identity, "Ёлка", [0])
        fp_b = _rfp(identity, "ЁЛКА", [1])
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, s, c: RESTORED_obs("Ёлка", (0,), fp_a))
        evaluation.sample(config)
        complete(tmp_path)
        evaluation.score(config)
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx2, cfg):
            orig(ctx2, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key",
                                lambda o, s, c: RESTORED_obs("ЁЛКА", (1,), fp_b))

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score(config)
        assert score_path().read_bytes() == old_score

    def test_t04c_none_to_restored_raises_sample_stale(self, tmp_path, monkeypatch):
        """T04c: NONE → RESTORED at fence → SAMPLE_STALE."""
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs, restoration_fp as _rfp
        units = setup_book(tmp_path, monkeypatch)
        (paths.TEXT / "yo.norm.txt").write_text("елка ёлка ёлка\n", encoding="utf-8")
        config = {"text_prep": {"yo_restore": True}}
        ctx = predictions(context_for(units))
        occ = ctx.rows[0]
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())
        evaluation.sample(config)
        complete(tmp_path)
        evaluation.score(config)
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx2, cfg):
            orig(ctx2, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key",
                                lambda o, s, c: RESTORED_obs("Ёлка", (0,), mock_fp))

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score(config)
        assert score_path().read_bytes() == old_score

    def test_t04d_f1_excluded_witness_change_raises_sample_stale(self, tmp_path, monkeypatch):
        """T04d: F1-excluded key's observer changes at fence → SAMPLE_STALE (witness covers F1 keys)."""
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs, restoration_fp as _rfp
        units = setup_book(tmp_path, monkeypatch)
        (paths.TEXT / "yo.norm.txt").write_text("елка ёлка ёлка\n", encoding="utf-8")
        config = {"text_prep": {"yo_restore": True}}
        ctx = predictions(context_for(units), changes={"01_test|0|0": {"f1_rule": "F1_TEST", "f1_flag": "f1_exclude"}})
        occ = ctx.rows[0]
        identity = ctx.sources.resolve(occ.source_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        monkeypatch.setattr(evaluation, "_yo_observe_key",
                            lambda o, s, c: RESTORED_obs("Ёлка", (0,), mock_fp))
        evaluation.sample(config)
        complete(tmp_path)
        evaluation.score(config)
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx2, cfg):
            orig(ctx2, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score(config)
        assert score_path().read_bytes() == old_score

    def test_t04e_unsupported_at_fence_raises_yo_observer_unsupported(self, tmp_path, monkeypatch):
        """T04e: observer returns UNSUPPORTED at fence → YO_OBSERVER_UNSUPPORTED."""
        from audiobook.stress_yo_observer import UNSUPPORTED_obs
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx, cfg):
            orig(ctx, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key",
                                lambda o, s, c: UNSUPPORTED_obs("INJECTED_AT_FENCE"))

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="YO_OBSERVER_UNSUPPORTED"):
            evaluation.score({})
        assert score_path().read_bytes() == old_score

    @pytest.mark.parametrize("noop_path", [False, True], ids=["rename", "noop"])
    def test_t04f_nonselected_eligible_assignment_change_raises_sample_stale(
        self, tmp_path, monkeypatch, noop_path
    ):
        """T04f: nonselected eligible key NONE→RESTORED changes eligible_assignment_sha256 → SAMPLE_STALE.

        Selected witnesses are unchanged; only the eligible assignment digest changes.
        Fires on both rename path (noop_path=False) and no-op path (noop_path=True).
        Without fix (_verify_selection_fresh absent from fence): no error raised.
        """
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs, restoration_fp as _rfp
        units = [{"type": "text", "text": "Бета."}, {"type": "text", "text": "Гамма."}]
        mini_strata = (("omograph", 0), ("top300", 0), ("name", 0),
                       ("override_covered", 0), ("yo_changed", 0), ("tail", 1))
        monkeypatch.setattr(evaluation, "STRATA", mini_strata)
        setup_book(tmp_path, monkeypatch, units)
        ctx = predictions(context_for(units))
        monkeypatch.setattr(evaluation, "_load_context", lambda _: ctx)
        monkeypatch.setattr(evaluation, "_yo_observe_key", lambda o, s, c: NONE_obs())
        evaluation.sample({})
        complete(tmp_path)
        if noop_path:
            evaluation.score({})
        # Determine the nonselected key by deterministic ranking (tail n=1: only ranked[0] selected).
        ranked = sorted(
            [occ.source_key for occ in ctx.rows],
            key=lambda k: hashlib.sha256(f"{evaluation.SEED_V2}|{k}".encode("utf-8")).hexdigest()
        )
        nonselected_key = ranked[1]
        nonselected_occ = next(occ for occ in ctx.rows if occ.source_key == nonselected_key)
        identity = ctx.sources.resolve(nonselected_key)[0]
        mock_fp = _rfp(identity, "Ёлка", [0])
        score_dir = paths.OUT / "stress" / "eval" / "score"
        old_bytes = score_path().read_bytes() if noop_path else None
        orig = evaluation._assert_current

        def inject(ctx2, cfg):
            orig(ctx2, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key",
                                lambda o, s, c: (RESTORED_obs("Ёлка", (0,), mock_fp)
                                                 if o.source_key == nonselected_key
                                                 else NONE_obs()))

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})
        if noop_path:
            assert score_path().read_bytes() == old_bytes
        else:
            assert not any(score_dir.glob("s2-*.json"))
        assert not any(score_dir.glob("*.txn-*"))

    @pytest.mark.parametrize("noop_path", [False, True], ids=["rename", "noop"])
    def test_t04g_unknown_observer_type_at_fence_raises_yo_observer_unsupported(
        self, tmp_path, monkeypatch, noop_path
    ):
        """T04g: unknown observer type at fence → YO_OBSERVER_UNSUPPORTED (fail-closed).

        Fires on both rename path (noop_path=False) and no-op path (noop_path=True).
        Without fix: unknown type silently treated as NONE; with fix: raises.
        """
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        if noop_path:
            evaluation.score({})
        score_dir = paths.OUT / "stress" / "eval" / "score"
        old_bytes = score_path().read_bytes() if noop_path else None
        orig = evaluation._assert_current

        class _UnknownObs:
            pass

        def inject(ctx, cfg):
            orig(ctx, cfg)
            monkeypatch.setattr(evaluation, "_yo_observe_key",
                                lambda o, s, c: _UnknownObs())

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="YO_OBSERVER_UNSUPPORTED"):
            evaluation.score({})
        if noop_path:
            assert score_path().read_bytes() == old_bytes
        else:
            assert not any(score_dir.glob("s2-*.json"))
        assert not any(score_dir.glob("*.txn-*"))

    def test_t05_gold_mutated_at_fence_raises_gold_output_changed(self, tmp_path, monkeypatch):
        """T05: gold mutated inside before_publish callback (post-fsync, pre-rename) → GOLD_OUTPUT_CHANGED."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        score_dir = paths.OUT / "stress" / "eval" / "score"
        gold = paths.TEXT / "stress_gold.tsv"
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            gold.write_bytes(gold.read_bytes() + b" ")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="GOLD_OUTPUT_CHANGED"):
            evaluation.score({})
        assert not any(score_dir.glob("s2-*.json"))
        assert not any(score_dir.glob("*.txn-*"))

    def test_t06_yo_mutated_at_fence_raises_yo_output_changed(self, tmp_path, monkeypatch):
        """T06: YO journal mutated inside before_publish callback (post-fsync, pre-rename) → YO_OUTPUT_CHANGED."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        score_dir = paths.OUT / "stress" / "eval" / "score"
        yo = evaluation._yo_path()
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            yo.parent.mkdir(parents=True, exist_ok=True)
            yo.write_bytes((yo.read_bytes() if yo.exists() else b"") + b"injected\n")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="YO_OUTPUT_CHANGED"):
            evaluation.score({})
        assert not any(score_dir.glob("s2-*.json"))
        assert not any(score_dir.glob("*.txn-*"))

    def test_t05r_gold_mutated_at_fence_rename_with_existing_score_preserves_old_bytes(
        self, tmp_path, monkeypatch
    ):
        """T05r: rename path with pre-existing score; gold mutated at fence → GOLD_OUTPUT_CHANGED, old bytes preserved."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        # Force rename path: append a byte so stored bytes ≠ new computation.
        score_path().write_bytes(score_path().read_bytes() + b" ")
        old_bytes = score_path().read_bytes()
        score_dir = paths.OUT / "stress" / "eval" / "score"
        gold = paths.TEXT / "stress_gold.tsv"
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            gold.write_bytes(gold.read_bytes() + b" ")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="GOLD_OUTPUT_CHANGED"):
            evaluation.score({})
        assert score_path().read_bytes() == old_bytes
        assert not any(score_dir.glob("*.txn-*"))

    def test_t06r_yo_mutated_at_fence_rename_with_existing_score_preserves_old_bytes(
        self, tmp_path, monkeypatch
    ):
        """T06r: rename path with pre-existing score; YO journal mutated at fence → YO_OUTPUT_CHANGED, old bytes preserved."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        score_path().write_bytes(score_path().read_bytes() + b" ")
        old_bytes = score_path().read_bytes()
        score_dir = paths.OUT / "stress" / "eval" / "score"
        yo = evaluation._yo_path()
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            yo.parent.mkdir(parents=True, exist_ok=True)
            yo.write_bytes((yo.read_bytes() if yo.exists() else b"") + b"injected\n")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="YO_OUTPUT_CHANGED"):
            evaluation.score({})
        assert score_path().read_bytes() == old_bytes
        assert not any(score_dir.glob("*.txn-*"))

    def test_t07_late_sample_mutation_raises_sample_invalid(self, tmp_path, monkeypatch):
        """T07: sample JSON mutated inside fence callback (post-fsync, pre-rename) → SAMPLE_INVALID."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        old_score = score_path().read_bytes()
        sample_dir = paths.OUT / "stress" / "eval" / "sample"
        sample_file = next(sample_dir.glob("*.json"))
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            sample_file.write_bytes(sample_file.read_bytes()[:-2])  # truncate closing brace → invalid JSON
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="SAMPLE_INVALID"):
            evaluation.score({})
        assert score_path().read_bytes() == old_score

    def test_t08_idempotent_second_score_does_not_raise(self, tmp_path, monkeypatch):
        """T08: calling score() twice returns identical result with same persisted bytes."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        score_dir = paths.OUT / "stress" / "eval" / "score"
        r1 = evaluation.score({})
        score_bytes_1 = score_path().read_bytes()
        r2 = evaluation.score({})
        score_bytes_2 = score_path().read_bytes()
        assert r1 == r2
        assert score_bytes_1 == score_bytes_2
        assert not any(score_dir.glob("*.txn-*")), "No temp files should remain"

    def test_t09_fence_fires_before_replace_so_target_absent_on_error(self, tmp_path, monkeypatch):
        """T09: fence fires inside _apply callback (post-fsync, pre-rename) — target absent on error."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        score_dir = paths.OUT / "stress" / "eval" / "score"
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            (paths.TEXT / "extra.norm.txt").write_text("injected-at-fence\n", encoding="utf-8")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})
        assert not any(score_dir.glob("s2-*.json")), "Target must not be written when fence raises"
        assert not any(score_dir.glob("*.txn-*")), "No temp files should remain after error"

    def test_t09b_pre_existing_score_preserved_when_fence_raises(self, tmp_path, monkeypatch):
        """T09b: fence raises in no-op path — pre-existing score bytes unchanged."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        old_score = score_path().read_bytes()
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            (paths.TEXT / "extra.norm.txt").write_text("injected-at-fence\n", encoding="utf-8")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})
        assert score_path().read_bytes() == old_score, "Pre-existing score must be preserved"

    def test_t09r_rename_with_existing_score_fence_raises_old_bytes_preserved(
        self, tmp_path, monkeypatch
    ):
        """T09r: rename path with pre-existing distinct score; fence raises → old bytes preserved, no temp residue."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})
        # Force rename path: append a byte so stored bytes ≠ new computation.
        score_path().write_bytes(score_path().read_bytes() + b" ")
        old_bytes = score_path().read_bytes()
        score_dir = paths.OUT / "stress" / "eval" / "score"
        orig_fence = evaluation._score_publication_fence

        def inject_fence(*args, **kwargs):
            (paths.TEXT / "extra.norm.txt").write_text("injected-at-fence\n", encoding="utf-8")
            orig_fence(*args, **kwargs)

        monkeypatch.setattr(evaluation, "_score_publication_fence", inject_fence)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})
        assert score_path().read_bytes() == old_bytes, "Pre-existing score must be preserved on rename path"
        assert not any(score_dir.glob("*.txn-*")), "No temp files should remain after error"

    def test_t10_no_op_path_fence_fires_on_idempotent_call(self, tmp_path, monkeypatch):
        """T10: second call takes no-op path but fence still fires and catches drift."""
        ready(tmp_path, monkeypatch)
        complete(tmp_path)
        evaluation.score({})  # write the file; second call will be no-op
        old_score = score_path().read_bytes()
        orig = evaluation._assert_current

        def inject(ctx, cfg):
            orig(ctx, cfg)
            (paths.TEXT / "extra.norm.txt").write_text("injected-for-noop\n", encoding="utf-8")

        monkeypatch.setattr(evaluation, "_assert_current", inject)
        with pytest.raises(AnnotationError, match="SAMPLE_STALE"):
            evaluation.score({})  # no-op path → fence fires → SAMPLE_STALE
        assert score_path().read_bytes() == old_score
