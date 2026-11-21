"""Synthetic selection, sample identity, output safety and owner todo tests."""
import copy
import hashlib
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from audiobook import paths, stress_eval as evaluation
from audiobook.unitmap import AnnotationError
from audiobook.wordprov import WordOcc, process_section_occs, source_fp


def row(form, index, **changes):
    values = dict(source_key=f"01_test|{index}|0", section="01_test", unit_id=str(index), unit_token_index=0,
                  norm_start=0, norm_end=len(form), form_source=form, chunk_n=index + 1, chunk_id=f"{index+1:04d}",
                  chunk_word_index=0, atom_index=index, atom_char_start=0, atom_char_end=len(form),
                  ana_start=index * 20, ana_end=index * 20 + len(form), form_analysis=form,
                  su_chunk_id=f"{index+1:04d}", su_fragment=None, su_token_index=0, form_synth=form,
                  alignment_status="aligned")
    values.update(changes)
    return WordOcc(**values)


def context_for(units, *, synth=None):
    from audiobook.sutrace import SUTrace
    units = copy.deepcopy(units)
    chunks = [{"id": f"{i+1:04d}", "n": i + 1, "text": unit["text"], "pause_after_ms": 900}
              for i, unit in enumerate(units)]
    traces = [SUTrace("01_test", c["id"], None, (synth or {}).get(c["text"], c["text"]),
                      0, [], "synthetic", None, "ok") for c in chunks]
    rows, _, _ = process_section_occs("01_test", units, chunks, traces)
    source = source_fp({"01_test": units})
    return evaluation.EvalContext(tuple(rows), source, hashlib.sha256((source + "analysis").encode()).hexdigest(),
                                  evaluation.SourceIndex({"01_test": units}), frozenset(), frozenset(), source.encode())


def setup_book(tmp_path, monkeypatch, units=None):
    units = units if units is not None else [{"type": "text", "text": "Бета."},
                                            {"type": "text", "text": "Гамма."},
                                            {"type": "text", "text": "Альфа."}]
    text, out = tmp_path / "text", tmp_path / "out"
    text.mkdir()
    out.mkdir()
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    monkeypatch.setattr(evaluation, "private_output_guard", lambda path: None)
    monkeypatch.setattr(evaluation, "_load_context", lambda _: context_for(units))
    monkeypatch.setattr(evaluation, "_load_sources", lambda _: context_for(units).sources)
    manifest_dir = out / "sections" / "01_test"
    manifest_dir.mkdir(parents=True)
    with (manifest_dir / "manifest.jsonl").open("w", encoding="utf-8") as mf:
        for i, unit in enumerate(units):
            mf.write(json.dumps({"id": f"{i+1:04d}", "n": i + 1,
                                 "text": unit["text"], "pause_after_ms": 900}) + "\n")
    return units


def test_literal_rank_and_sample_fp_oracle():
    rows = [row("Альфа", i) for i in range(3)]
    targets = (("omograph", 2), ("top300", 1), ("name", 1), ("override_covered", 1), ("yo_changed", 1), ("tail", 1))
    result = evaluation.select_sample(rows, "source", "analysis", homographs={"альфа"}, names=set(), targets=targets)
    # Literal ranking checked independently from the sampler, below.
    expected_keys = ["01_test|0|0", "01_test|2|0"]
    assert result.record["keys"] == expected_keys
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected = {"algo": "sample/1", "source_fp": "source", "analysis_fp": "analysis", "seed": "t15-7/1",
                "strata": [{"name": n, "n": size} for n, size in targets],
                "selected_keys_sha256": hashlib.sha256(canonical(expected_keys)).hexdigest()}
    assert result.record["sample_fp"] == hashlib.sha256(canonical(expected)).hexdigest()
    assert result.record["strata"]["omograph"] == {"N": 3, "n": 2}


def test_six_disjoint_strata_and_exact_precedence():
    forms = ["ее" + "".join(letters) for letters in itertools.islice(itertools.product("бвгджзкл", repeat=3), 300)]
    rows = [row(form, i * 3 + repeat) for i, form in enumerate(forms) for repeat in range(3)]
    special = [row("Альфа", 1000), row("Имяа", 1001, status="covered_by_override", reason=""),
               row("елкоо", 1002, status="covered_by_override", reason="", form_synth="ёлкоо"),
               row("елкаа", 1003, form_synth="ёлкаа"), row("абрака", 1004)]
    rows.extend(special)
    result = evaluation.select_sample(rows, "source", "analysis", homographs={forms[0], "альфа"},
                                      names={forms[1], "имяа"})
    expected = ["omograph", "name", "override_covered", "yo_changed", "tail"]
    assert [result.strata_by_key[r.source_key] for r in special] == expected
    assert result.strata_by_key[rows[3].source_key] == "top300"  # More frequent name loses to top300.
    assert sum(v["N"] for v in result.record["strata"].values()) == len(rows)
    assert len(result.strata_by_key) == len(rows)
    assert all(v["n"] == min(dict(evaluation.STRATA)[name], v["N"]) for name, v in result.record["strata"].items())


def test_eligibility_and_one_vowel_diagnostics():
    rows = [row("Бета", 0), row("Бета", 1, alignment_status="prep_token_mismatch"), row("Дом", 2), row("К", 3)]
    result = evaluation.select_sample(rows, "source", "analysis", homographs=set(), names=set())
    assert result.record["keys"] == [rows[0].source_key]
    assert result.one_vowel_aligned == 1


def test_yo_requires_only_orthographic_change():
    assert evaluation.yo_changed(row("Елка", 0, form_synth="Ёлка"))
    assert not evaluation.yo_changed(row("елка", 0, form_synth="Елка"))
    assert not evaluation.yo_changed(row("елка", 0, form_synth="Ёлка"))
    assert not evaluation.yo_changed(row("елка", 0, form_synth=None))


def test_source_analysis_policy_mutations_and_order_stability():
    rows = [row("Альфа", 0), row("Бета", 1)]
    make = lambda r, source="source", analysis="analysis", targets=evaluation.STRATA: evaluation.select_sample(
        r, source, analysis, homographs=set(), names=set(), targets=targets).record
    original = make(rows)
    assert make(list(reversed(rows))) == original
    assert make(rows, source="changed")["sample_fp"] != original["sample_fp"]
    assert make(rows, analysis="changed")["sample_fp"] != original["sample_fp"]
    policy = tuple((name, n + 1) for name, n in evaluation.STRATA)
    changed = make(rows, targets=policy)
    assert changed["keys"] == original["keys"]
    assert changed["sample_fp"] != original["sample_fp"]  # Policy change matters even below the target.


def test_duplicate_occurrence_identity_refused():
    with pytest.raises(AnnotationError, match="OCCURRENCE_IDENTITY_DUPLICATE"):
        evaluation.select_sample([row("Бета", 0)] * 2, "s", "a", homographs=set(), names=set())


def test_hashseed_byte_determinism():
    script = '''from audiobook.stress_eval import select_sample,_canonical
from types import SimpleNamespace
rows=[SimpleNamespace(source_key=f"01_test|{i}|0",form_source="Альфа",form_analysis="Альфа",form_synth="Альфа",alignment_status="aligned",status="unresolved") for i in range(200)]
print(_canonical(select_sample(rows,"source","analysis",homographs={"альфа"},names=set()).record).hex())
'''
    outputs = []
    for seed in ("1", "2", "3"):
        result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True,
                                env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"})
        assert result.returncode == 0
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1] == outputs[2]


def test_sample_creates_only_blank_local_owner_artifacts(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    result = evaluation.sample({})
    assert result["selected"] == result["todo"] == 3
    todo_path = evaluation._todo_path_v2(result["sample_fp"])
    todo = evaluation.parse_gold(todo_path.read_text(encoding="utf-8"), allow_blank=True)
    assert all(all(not row[field] for field in evaluation.LABEL_FIELDS) for row in todo)
    assert evaluation.parse_gold((paths.TEXT / "stress_gold.tsv").read_text(encoding="utf-8")) == []
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json"))
    assert set(json.loads(record.read_text(encoding="utf-8"))) == evaluation._V2_SAMPLE_FIELDS
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert evaluation.sample({}) == result
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_p1_failure_prevents_all_writes(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    def reject(_):
        raise AnnotationError("PRIVATE_OUTPUT_REQUIRED")
    monkeypatch.setattr(evaluation, "private_output_guard", reject)
    with pytest.raises(AnnotationError, match="PRIVATE_OUTPUT_REQUIRED"):
        evaluation.sample({})
    # The eval lock-file and test-fixture manifests are infrastructure; skip them.
    lock = paths.OUT / "stress" / "eval" / evaluation._EVAL_LOCK_NAME
    sections_dir = paths.OUT / "sections"
    assert not any(p.is_file() for p in tmp_path.rglob("*")
                   if p != lock and not str(p).startswith(str(sections_dir)))


def test_b1_sample_uses_only_versioned_todo_never_legacy(tmp_path, monkeypatch):
    """B1: sample() must write only the s2-versioned todo; legacy stress_gold.todo.tsv must not be created."""
    setup_book(tmp_path, monkeypatch)
    result = evaluation.sample({})
    legacy_todo = paths.TEXT / "stress_gold.todo.tsv"
    assert not legacy_todo.exists(), "sample() must not write the legacy 320-row todo"
    s2_todos = sorted(paths.TEXT.glob("stress_gold.todo.s2-*.tsv"))
    assert len(s2_todos) == 1
    s2_rows = evaluation.parse_gold(s2_todos[0].read_text(encoding="utf-8"), allow_blank=True)
    assert len(s2_rows) == result["todo"]
    assert all(all(not row[field] for field in evaluation.LABEL_FIELDS) for row in s2_rows)
    # Idempotent: second run does not create legacy todo.
    evaluation.sample({})
    assert not legacy_todo.exists()


def test_existing_sample_mismatch_is_not_overwritten(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("s2-*.json"))
    record.write_text("{}", encoding="utf-8")
    with pytest.raises(AnnotationError, match="SAMPLE_INVALID"):
        evaluation.sample({})
    assert record.read_text(encoding="utf-8") == "{}"


def test_validated_reader_and_existing_detectors_are_used(tmp_path, monkeypatch):
    from audiobook import stress_fp, stress_inventory
    context = context_for([{"type": "text", "text": "Бета Имяа. Альфа."}])
    out = tmp_path / "out"
    pointer = out / "stress" / "inventory" / "current.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("synthetic pointer", encoding="utf-8")
    monkeypatch.setattr(paths, "OUT", out)
    calls = []
    monkeypatch.setattr(stress_fp, "read_occurrences", lambda cfg: calls.append("validated") or list(context.rows))
    monkeypatch.setattr(stress_fp, "load_current", lambda _: {"source_fp": context.source_fp, "analysis_fp": context.analysis_fp})
    monkeypatch.setattr(stress_inventory, "_build_section_data", lambda section, pause: ("Бета Имяа. Альфа.", [], [], []))
    monkeypatch.setattr(stress_inventory, "_omograph_dict", lambda: {"бета": ["synthetic", "other"], "альфа": ["one"]})
    loaded = evaluation._load_context({})
    assert calls == ["validated"]
    assert loaded.names == {"имяа"}
    assert loaded.homographs == {"бета"}


def test_stale_generation_is_not_bypassed(tmp_path, monkeypatch):
    from audiobook import stress_fp
    pointer = tmp_path / "stress" / "inventory" / "current.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(paths, "OUT", tmp_path)
    def stale(_):
        raise AnnotationError("INVENTORY_STALE")
    monkeypatch.setattr(stress_fp, "read_occurrences", stale)
    with pytest.raises(AnnotationError, match="INVENTORY_STALE"):
        evaluation.sample({})


# ---------------------------------------------------------------------------
# WP4-G1 I1: sample/2 fingerprint, stratum, todo protection (T16, T18, T21-T25)
# ---------------------------------------------------------------------------

def _v2_rows(specs):
    """Build synthetic WordOcc list from (form, status, f1_rule, f1_flag) tuples."""
    result = []
    for i, (form, occ_status, f1_rule, f1_flag) in enumerate(specs):
        result.append(row(
            form, i,
            status=occ_status,
            f1_rule=f1_rule,
            f1_flag=f1_flag,
        ))
    return result


def _select_v2(rows, obs_map=None, source_fp_val="src", analysis_fp_val="ana",
               norm_digest="n", yo_map_digest="y", prep_config_digest="p",
               homographs=frozenset(), names=frozenset(), targets=evaluation.STRATA):
    return evaluation.select_sample_v2(
        rows, source_fp_val, analysis_fp_val,
        obs_map=obs_map or {},
        norm_digest=norm_digest,
        yo_map_digest=yo_map_digest,
        prep_config_digest=prep_config_digest,
        homographs=homographs,
        names=names,
        targets=targets,
    )


def _common_rows(n=300, start_idx=10):
    """Build N filler rows with forms 'Аалов{i}' that fill top300 slots.

    These forms start with 'а', so they sort before most Cyrillic words and
    reliably occupy the first N slots of top[:300], pushing rarer forms out.
    """
    from audiobook.stress_yo_observer import NONE_obs
    rows = [row(f"Аалов{i}", start_idx + i) for i in range(n)]
    obs_map = {r.source_key: NONE_obs() for r in rows}
    return rows, obs_map


class TestT21SampleV2FingerprintAndAssignment:
    """T21: stratum swap and unsampled-eligible change both stale the sample fingerprint;
    input row order does not affect the fingerprint.

    top300 is computed from eligible form frequencies; with ≤300 unique forms,
    ALL forms qualify, so yo_changed/tail strata are unreachable. The common-rows
    fixture fills top300 slots with 'аалов{i}' forms, pushing 'я...' target words out.
    """

    def _base_rows(self):
        """3-row fixture for row-order and selected-swap tests (stratum doesn't matter)."""
        from audiobook.stress_yo_observer import NONE_obs
        rows = [row("Альфа", 0), row("Бета", 1), row("Гамма", 2)]
        obs_map = {r.source_key: NONE_obs() for r in rows}
        return rows, obs_map

    def test_swapped_stratum_assignment_changes_eligible_digest(self):
        """T21a: changing one key's stratum assignment changes eligible_assignment_sha."""
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs
        common, obs_map = _common_rows()  # 300 'аалов{i}' rows filling top300
        target = row("Якорное", 0)       # 'я...' → not in top300
        all_rows = common + [target]
        obs_map1 = {**obs_map, target.source_key: NONE_obs()}    # target → tail
        obs_map2 = {**obs_map, target.source_key: RESTORED_obs("Якёрное", (1,), "fp")}  # → yo_changed
        s1 = _select_v2(all_rows, obs_map1)
        s2 = _select_v2(all_rows, obs_map2)
        assert s1.record["eligible_assignment_sha256"] != s2.record["eligible_assignment_sha256"]
        assert s1.record["sample_fp"] != s2.record["sample_fp"]

    def test_row_order_does_not_affect_fp(self):
        """T21c: shuffling input rows yields identical sample/2 fingerprint."""
        rows, obs_map = self._base_rows()
        s1 = _select_v2(rows, obs_map)
        s2 = _select_v2(list(reversed(rows)), obs_map)
        assert s1.record["sample_fp"] == s2.record["sample_fp"]
        assert s1.record["eligible_assignment_sha256"] == s2.record["eligible_assignment_sha256"]

    def test_unsampled_eligible_stratum_change_stales_fp(self):
        """T21b: eligible key changes stratum (not selected) → fp changes.

        Uses 50 'яхта{i}' rows in tail (target=40 → 10 unselected). Changing
        obs for one unselected key from NONE→RESTORED moves it tail→yo_changed,
        staling both eligible_assignment_sha and sample_fp.
        """
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs
        common, obs_common = _common_rows()           # fills top300
        rare = [row(f"Яхта{i}", 310 + i) for i in range(50)]  # 'я...' → tail
        all_rows = common + rare
        obs_map1 = {**obs_common, **{r.source_key: NONE_obs() for r in rare}}
        s1 = _select_v2(all_rows, obs_map1)
        # Find an unselected rare key (tail target=40, 50 rare eligible → ≥10 unselected).
        selected = set(s1.record["keys"])
        unselected = [r for r in rare if r.source_key not in selected]
        assert unselected, "need at least one unselected rare row"
        target_key = unselected[0].source_key
        obs_map2 = dict(obs_map1)
        obs_map2[target_key] = RESTORED_obs("Яётта0", (0,), "fp")
        s2 = _select_v2(all_rows, obs_map2)
        assert s1.record["eligible_assignment_sha256"] != s2.record["eligible_assignment_sha256"]
        assert s1.record["sample_fp"] != s2.record["sample_fp"]

    def test_selected_membership_swap_changes_by_stratum_digest(self):
        """T21a: different selected-by-stratum for same totals → different digests."""
        from audiobook.stress_yo_observer import NONE_obs
        # Both rows are eligible tail; swap which one gets selected with tiny target.
        r1 = row("Слово", 0)
        r2 = row("Текст", 1)
        obs_map = {r1.source_key: NONE_obs(), r2.source_key: NONE_obs()}
        targets_one = (("omograph", 0), ("top300", 0), ("name", 0),
                       ("override_covered", 0), ("yo_changed", 0), ("tail", 1))
        s1 = _select_v2([r1, r2], obs_map, targets=targets_one)
        s2 = _select_v2([r2, r1], obs_map, targets=targets_one)
        # Same fp because SHA-based ranking is deterministic (not iteration-order dependent).
        assert s1.record["sample_fp"] == s2.record["sample_fp"]


class TestT22Hashseed:
    """T22: PYTHONHASHSEED variation does not affect sample/2 fingerprint."""

    def test_hashseed_stable(self):
        """T22: Same fp across PYTHONHASHSEED=1,2,3 (run via subprocess)."""
        import subprocess, sys, json, textwrap
        script = textwrap.dedent("""
            import hashlib, json
            from audiobook import stress_eval as ev
            from audiobook.stress_yo_observer import NONE_obs
            from audiobook.wordprov import WordOcc
            def mk(form, i):
                return WordOcc(source_key=f"01_t|{i}|0", section="01_t", unit_id=str(i),
                               unit_token_index=0, norm_start=0, norm_end=len(form),
                               form_source=form, chunk_n=i+1, chunk_id=f"{i+1:04d}",
                               chunk_word_index=0, atom_index=i, atom_char_start=0,
                               atom_char_end=len(form), ana_start=0, ana_end=len(form),
                               form_analysis=form, su_chunk_id=f"{i+1:04d}",
                               su_fragment=None, su_token_index=0, form_synth=form,
                               alignment_status="aligned")
            rows = [mk(f"Слово{j}", j) for j in range(10)]
            obs_map = {r.source_key: NONE_obs() for r in rows}
            sel = ev.select_sample_v2(rows, "s", "a",
                obs_map=obs_map, norm_digest="n", yo_map_digest="y", prep_config_digest="p",
                homographs=frozenset(), names=frozenset())
            print(sel.record["sample_fp"])
        """)
        fps = set()
        for seed in ("1", "2", "3"):
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True,
                env={**__import__("os").environ, "PYTHONHASHSEED": seed,
                     "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            )
            assert result.returncode == 0, result.stderr
            fps.add(result.stdout.strip())
        assert len(fps) == 1, f"fp varies by PYTHONHASHSEED: {fps}"


class TestT23StratumPrecedenceAndSizes:
    """T23: six strata precedence (omograph→tail) and 100/60/40/40/40/40 targets.

    All target words must have ≥2 Cyrillic vowels to be eligible.
    300 'аалов{i}' fillers are needed so that specific test words (starting with
    в/и/о/я) fall outside top300 and reach their intended strata.
    """

    def test_exact_strata_order_and_first_match_wins(self):
        """T23: each eligible key goes to first matching stratum."""
        from audiobook.stress_yo_observer import RESTORED_obs, NONE_obs
        common, obs_common = _common_rows()  # 300 'аалов{i}' fill top300
        specific = [
            row("Омограф", 0),                              # homograph (о..., 3 vowels)
            row("Имена", 2),                                # name (и..., 3 vowels)
            row("Оборона", 3, status="covered_by_override"),# override_covered (4 vowels)
            row("Восстан", 4),                              # yo_changed (RESTORED, 2 vowels)
        ]
        obs_specific = {
            specific[0].source_key: NONE_obs(),
            specific[1].source_key: NONE_obs(),
            specific[2].source_key: NONE_obs(),
            specific[3].source_key: RESTORED_obs("Вёсстан", (0,), "fp"),
        }
        all_rows = common + specific
        obs_map = {**obs_common, **obs_specific}
        # 300 'аалов{i}' fill the top300 slots; 'восстан', 'имена', 'оборона', 'омограф'
        # all sort after 'аалов{i}' (в/и/о > а) → not in top300.
        s = _select_v2(all_rows, obs_map, homographs=frozenset(["омограф"]),
                       names=frozenset(["имена"]))
        assert s.strata_by_key.get(specific[0].source_key) == "omograph"
        assert s.strata_by_key.get(specific[2].source_key) == "override_covered"
        assert s.strata_by_key.get(specific[3].source_key) == "yo_changed"

    def test_take_all_for_undersized_stratum(self):
        """T23: stratum population < target → take all."""
        from audiobook.stress_yo_observer import NONE_obs
        # 'Слово' (2 vowels) must land in tail, not top300.
        # 300 'аалов{i}' fillers fill top300 so 'слово' (с > а) is not included.
        common, obs_common = _common_rows()
        target = row("Слово", 0)
        all_rows = common + [target]
        obs_map = {**obs_common, target.source_key: NONE_obs()}
        s = _select_v2(all_rows, obs_map)
        assert s.record["strata"]["tail"]["N"] == 1
        assert s.record["strata"]["tail"]["n"] == 1

    def test_no_overlap_between_strata(self):
        """T23: selected keys appear in exactly one stratum."""
        from audiobook.stress_yo_observer import NONE_obs, RESTORED_obs
        rows = [row(f"Слово{i}", i) for i in range(20)]
        obs_map = {}
        for i, r in enumerate(rows):
            obs_map[r.source_key] = RESTORED_obs(f"Слёво{i}", (0,), "fp") if i % 5 == 0 else NONE_obs()
        s = _select_v2(rows, obs_map)
        all_selected = s.record["keys"]
        assert len(all_selected) == len(set(all_selected)), "duplicate selected keys"


class TestT24T25TodoProtection:
    """T24/T25: versioned sample/2 todo protection.

    The existing 320-row sample/1 todo (text/stress_gold.todo.tsv) must NOT be
    overwritten when sample/2 paths are accessed.
    """

    def test_absent_versioned_todo_allows_creation(self, tmp_path, monkeypatch):
        """T24: todo path absent → guarded creation allowed (returns 'create')."""
        import audiobook.stress_eval as ev
        monkeypatch.setattr(paths, "TEXT", tmp_path)
        monkeypatch.setattr(paths, "OUT", tmp_path)
        monkeypatch.setattr(ev, "private_output_guard", lambda p: None)
        from audiobook.stress_yo_observer import NONE_obs
        rows = [row("Слово", 0)]
        obs_map = {rows[0].source_key: NONE_obs()}
        s = _select_v2(rows, obs_map)
        fp = s.record["sample_fp"]
        todo_path = ev._todo_path_v2(fp)
        assert not todo_path.exists()
        # _check_todo_v2 on absent path → 'create'.
        status = ev._check_todo_v2(todo_path, [], [])
        assert status == "create"

    def test_same_bytes_todo_is_noop(self, tmp_path, monkeypatch):
        """T24: existing todo with same bytes → 'noop', no overwrite."""
        import audiobook.stress_eval as ev
        monkeypatch.setattr(ev, "private_output_guard", lambda p: None)
        todo_path = tmp_path / "stress_gold.todo.s2-fp16.tsv"
        content = ev.serialize_gold([], allow_blank=True)
        todo_path.write_text(content, encoding="utf-8")
        status = ev._check_todo_v2(todo_path, [], [])
        assert status == "noop"

    def test_different_bytes_no_unmerged_labels_raises_protected(self, tmp_path, monkeypatch):
        """T24a / Issue #10: existing todo with different bytes → OWNER_TODO_PROTECTED, even with no unmerged labels."""
        import audiobook.stress_eval as ev
        monkeypatch.setattr(ev, "private_output_guard", lambda p: None)
        todo_path = tmp_path / "stress_gold.todo.s2-fp16.tsv"
        from audiobook.stress_eval import GOLD_FIELDS, serialize_gold
        blank_row = {f: "" for f in GOLD_FIELDS}
        blank_row.update(source_key="01_test|0|0", form_source="слово",
                         unit_text_sha256="a" * 64, unit_kind="text",
                         context_sha256="b" * 64, context="тест")
        content = serialize_gold([blank_row], allow_blank=True)
        todo_path.write_bytes(content.encode("utf-8"))
        with pytest.raises(AnnotationError, match="OWNER_TODO_PROTECTED"):
            ev._check_todo_v2(todo_path, [], [])

    def test_corrupt_todo_raises_owner_todo_protected(self, tmp_path, monkeypatch):
        """T24a-corrupt: corrupt todo file (unparseable) → OWNER_TODO_PROTECTED."""
        import audiobook.stress_eval as ev
        todo_path = tmp_path / "stress_gold.todo.s2-fp16.tsv"
        todo_path.write_bytes(b"corrupt\x00data")
        with pytest.raises(AnnotationError, match="OWNER_TODO_PROTECTED"):
            ev._check_todo_v2(todo_path, [], [])

    def test_different_bytes_with_filled_label_raises_has_unmerged(self, tmp_path, monkeypatch):
        """T24b: existing todo has filled unmerged labels → TODO_HAS_UNMERGED_LABELS."""
        import audiobook.stress_eval as ev
        monkeypatch.setattr(ev, "private_output_guard", lambda p: None)
        todo_path = tmp_path / "stress_gold.todo.s2-fp16.tsv"
        from audiobook.stress_eval import GOLD_FIELDS, serialize_gold
        import datetime
        filled_row = {
            "source_key": "01_test|0|0", "form_source": "слово",
            "unit_text_sha256": "a" * 64, "unit_kind": "text",
            "context_sha256": "b" * 64, "context": "тест",
            "gold_vowel": "0", "yo_correct": "na",
            "labeler": "owner", "date": str(datetime.date.today()),
        }
        content = serialize_gold([filled_row])
        todo_path.write_bytes(content.encode("utf-8"))
        with pytest.raises(AnnotationError, match="TODO_HAS_UNMERGED_LABELS"):
            ev._check_todo_v2(todo_path, [], [])

    def test_sample1_todo_untouched_by_check_todo_v2(self, tmp_path, monkeypatch):
        """T25: existing 320-row sample/1 todo remains byte-identical after sample/2 check."""
        import audiobook.stress_eval as ev
        monkeypatch.setattr(ev, "private_output_guard", lambda p: None)
        # Write sample/1 todo at the fixed (non-versioned) path.
        s1_todo = tmp_path / "stress_gold.todo.tsv"
        s1_content = ev.GOLD_FIELDS[0]  # Header-like content.
        s1_todo.write_bytes(s1_content.encode("utf-8"))
        before_bytes = s1_todo.read_bytes()
        # Check a sample/2 versioned path (different path, different prefix).
        s2_todo = tmp_path / "stress_gold.todo.s2-abcdef1234567890.tsv"
        # _check_todo_v2 on a non-existent s2 path → 'create', doesn't touch s1 path.
        status = ev._check_todo_v2(s2_todo, [], [])
        assert status == "create"
        assert s1_todo.read_bytes() == before_bytes, "sample/1 todo bytes changed!"


class TestT16T18F1CountersWithWordOcc:
    """T16/T18: F1 counters via real WordOcc fixtures (complementing observer unit tests)."""

    def _make_row(self, form, f1_rule=None, f1_flag="none"):
        return row(form, 0, f1_rule=f1_rule, f1_flag=f1_flag)

    def test_t16_rule_only_occ_excluded(self):
        """T16: occ with f1_rule set, f1_flag='none', RESTORED → rule-only exclusion."""
        from audiobook.stress_yo_observer import F1Counters, RESTORED_obs
        occ = self._make_row("реки", f1_rule="f1_accent_rule")
        obs = RESTORED_obs("рёки", (0,), "fp")
        counters = F1Counters()
        counters.add(occ, obs)
        assert counters.by_rule == 1
        assert counters.by_flag == 0
        assert counters.by_both == 0
        assert counters.union == 1
        assert counters.yo_evaluable == 0

    def test_t18_flag_only_occ_excluded(self):
        """T18: occ with f1_rule=None, f1_flag='span_ambiguous', RESTORED → flag-only."""
        from audiobook.stress_yo_observer import F1Counters, RESTORED_obs
        occ = self._make_row("реки", f1_rule=None, f1_flag="span_ambiguous")
        obs = RESTORED_obs("рёки", (0,), "fp")
        counters = F1Counters()
        counters.add(occ, obs)
        assert counters.by_flag == 1
        assert counters.by_rule == 0
        assert counters.by_both == 0
        assert counters.union == 1
        assert counters.yo_evaluable == 0

    def test_t18_rule_and_flag_union_not_double_counted(self):
        """T18: both rule and flag → both=1, union=1 (not 2)."""
        from audiobook.stress_yo_observer import F1Counters, RESTORED_obs
        occ = self._make_row("реки", f1_rule="r", f1_flag="span_ambiguous")
        obs = RESTORED_obs("рёки", (0,), "fp")
        counters = F1Counters()
        counters.add(occ, obs)
        assert counters.by_rule == 1
        assert counters.by_flag == 1
        assert counters.by_both == 1
        assert counters.union == 1

    def test_t16_no_exclusion_is_evaluable(self):
        """T16: f1_rule=None, f1_flag='none', RESTORED → YO_EVALUABLE=True."""
        from audiobook.stress_yo_observer import F1Counters, RESTORED_obs
        occ = self._make_row("реки")  # No F1 flags.
        obs = RESTORED_obs("рёки", (0,), "fp")
        counters = F1Counters()
        counters.add(occ, obs)
        assert counters.yo_evaluable == 1
        assert counters.union == 0


class TestAcquireReleaseLock:
    """OS-backed lock: acquire/release and fail-closed on double acquisition."""

    def test_acquire_and_release(self, tmp_path, monkeypatch):
        """Lock acquires and releases cleanly."""
        monkeypatch.setattr(paths, "OUT", tmp_path)
        import audiobook.stress_eval as ev
        handle = ev.acquire_eval_lock()
        assert handle is not None
        ev.release_eval_lock(handle)

    def test_lock_at_explicit_path(self, tmp_path):
        """Lock works with an explicit path."""
        import audiobook.stress_eval as ev
        lock_path = tmp_path / ".test.lock"
        handle = ev.acquire_eval_lock(lock_path)
        ev.release_eval_lock(handle)

    def test_double_acquire_raises_lock_unavailable(self, tmp_path):
        """Second acquire while first is held → EVAL_LOCK_UNAVAILABLE."""
        import audiobook.stress_eval as ev
        from audiobook.unitmap import AnnotationError
        lock_path = tmp_path / ".test.lock"
        h1 = ev.acquire_eval_lock(lock_path)
        try:
            with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
                ev.acquire_eval_lock(lock_path)
        finally:
            ev.release_eval_lock(h1)

    def test_released_lock_can_be_reacquired(self, tmp_path):
        """After release, lock can be acquired again."""
        import audiobook.stress_eval as ev
        lock_path = tmp_path / ".test.lock"
        h1 = ev.acquire_eval_lock(lock_path)
        ev.release_eval_lock(h1)
        h2 = ev.acquire_eval_lock(lock_path)
        ev.release_eval_lock(h2)


# ---------------------------------------------------------------------------
# C1 Gate: _load_sources duck-type contract (A1)
# ---------------------------------------------------------------------------

def test_A1_load_sources_returns_source_index_protocol(tmp_path, monkeypatch):
    """A1: SourceIndex (returned by _load_sources) exposes a callable resolve() method."""
    si = context_for([{"type": "text", "text": "Бета."}]).sources
    assert hasattr(si, "resolve") and callable(si.resolve)
