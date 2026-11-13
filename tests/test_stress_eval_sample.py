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
    todo = evaluation.parse_gold((paths.TEXT / "stress_gold.todo.tsv").read_text(encoding="utf-8"), allow_blank=True)
    assert all(all(not row[field] for field in evaluation.LABEL_FIELDS) for row in todo)
    assert evaluation.parse_gold((paths.TEXT / "stress_gold.tsv").read_text(encoding="utf-8")) == []
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("*.json"))
    assert set(json.loads(record.read_text(encoding="utf-8"))) == {"sample_fp", "source_fp", "analysis_fp", "strata", "keys"}
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
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_existing_sample_mismatch_is_not_overwritten(tmp_path, monkeypatch):
    setup_book(tmp_path, monkeypatch)
    evaluation.sample({})
    record = next((paths.OUT / "stress" / "eval" / "sample").glob("*.json"))
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
