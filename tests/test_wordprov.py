"""Tests for src/audiobook/wordprov.py — T15-7.3"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------

def _make_unit(text: str, utype: str = "text") -> dict:
    return {"type": utype, "text": text}


def _make_chunk(n: int, text: str, **kw) -> dict:
    return {"id": f"{n:04d}", "n": n, "text": text,
            "hash": "aaa", "pause_after_ms": 0, "status": "pending",
            **kw}


def _make_trace(chunk_id, prep_text, pad_len=0, matches=None, status="ok"):
    from audiobook.sutrace import SUTrace
    return SUTrace(
        section="01_test",
        chunk_id=chunk_id,
        fragment=None,
        prep_text=prep_text,
        pad_len=pad_len,
        matches=matches or [],
        final_sha256=hashlib.sha256(prep_text.encode()).hexdigest(),
        phrase_sha256=None,
        status=status,
    )


def _run(units, chunks, traces=None, section="01_test"):
    """process_section_occs returns (occs, ana_text, offset_map)."""
    from audiobook.wordprov import process_section_occs
    return process_section_occs(section, units, chunks, traces)


# ---------------------------------------------------------------------------
# U+0301 guard
# ---------------------------------------------------------------------------

def test_check_source_marks_clean():
    from audiobook.wordprov import check_source_marks
    units = [_make_unit("Привет мир"), _make_unit("Без меток")]
    check_source_marks(units, section="01_test")  # must not raise


def test_check_source_marks_found():
    from audiobook.wordprov import check_source_marks
    from audiobook.unitmap import AnnotationError
    units = [_make_unit("Приве́т")]  # U+0301 stress mark
    with pytest.raises(AnnotationError):
        check_source_marks(units, section="01_test")


# ---------------------------------------------------------------------------
# L-a link (units[uid]["text"][norm_start:norm_end] == form_source)
# ---------------------------------------------------------------------------

def test_la_link():
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    occs, _, _ = _run(units, chunks)
    assert len(occs) == 2
    for occ in occs:
        uid = int(occ.unit_id)
        assert units[uid]["text"][occ.norm_start:occ.norm_end] == occ.form_source


def test_la_link_nonalpha_prefix():
    units = [_make_unit("«Мир добра»")]
    chunks = [_make_chunk(1, "«Мир добра»")]
    occs, _, _ = _run(units, chunks)
    for occ in occs:
        uid = int(occ.unit_id)
        assert units[uid]["text"][occ.norm_start:occ.norm_end] == occ.form_source


# ---------------------------------------------------------------------------
# L-b link (stream[atom_index].text[atom_char_start:atom_char_end] == form_source)
# ---------------------------------------------------------------------------

def test_lb_link():
    from audiobook.unitmap import map_section
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    occs, _, _ = _run(units, chunks)
    sm = map_section(units, chunks, section="01_test")
    for occ in occs:
        atom_text = sm.stream[occ.atom_index].text
        assert atom_text[occ.atom_char_start:occ.atom_char_end] == occ.form_source


# ---------------------------------------------------------------------------
# L-c link (ana_text[ana_start:ana_end] == form_analysis)
# ---------------------------------------------------------------------------

def test_lc_link():
    from audiobook.wordprov import build_analysis_text
    units = [_make_unit("Привет мир"), _make_unit("Снова привет")]
    ana_text, offset_map = build_analysis_text(units, {})
    assert "\n" in ana_text
    import re
    for uid, unit in enumerate(units):
        for m in re.finditer(r"[а-яёА-ЯЁ]+", unit["text"]):
            key = (uid, m.start(), m.end())
            if key in offset_map:
                start, end = offset_map[key]
                assert ana_text[start:end] == m.group()


def test_lc_link_with_substitution():
    from audiobook.wordprov import build_analysis_text
    units = [_make_unit("Идет дождь")]
    fm = {(0, 0, 4): "Идёт"}
    ana_text, offset_map = build_analysis_text(units, fm)
    assert ana_text.startswith("Идёт")
    start, end = offset_map[(0, 0, 4)]
    assert ana_text[start:end] == "Идёт"


def test_lc_link_via_provenance():
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    trace = _make_trace("0001", "Привет мир")
    occs, ana_text, _ = _run(units, chunks, [trace])
    for occ in occs:
        assert ana_text[occ.ana_start:occ.ana_end] == occ.form_analysis


# ---------------------------------------------------------------------------
# Source key stability
# ---------------------------------------------------------------------------

def test_source_key_stability_under_manifest_change():
    units = [_make_unit("Тест слово")]
    chunks_v1 = [_make_chunk(1, "Тест слово")]
    chunks_v2 = [_make_chunk(1, "Тест слово", pause_after_ms=500)]

    occs1, _, _ = _run(units, chunks_v1)
    occs2, _, _ = _run(units, chunks_v2)
    for o1, o2 in zip(occs1, occs2):
        assert o1.source_key == o2.source_key


def test_source_key_format():
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    occs, _, _ = _run(units, chunks)
    for occ in occs:
        parts = occ.source_key.split("|")
        assert len(parts) == 3
        assert parts[0] == "01_test"
        assert parts[1] == str(int(parts[1]))


# ---------------------------------------------------------------------------
# source_fp mutation tests
# ---------------------------------------------------------------------------

def test_source_fp_stable():
    from audiobook.wordprov import source_fp
    units = [_make_unit("Привет мир")]
    fp_a = source_fp({"01_test": units})
    fp_b = source_fp({"01_test": units})
    assert fp_a == fp_b


def test_source_fp_changes_on_unit_text():
    from audiobook.wordprov import source_fp
    assert source_fp({"01_test": [_make_unit("Привет мир")]}) != \
           source_fp({"01_test": [_make_unit("Привет свет")]})


def test_source_fp_changes_on_excluded_sections():
    from audiobook.wordprov import source_fp
    units = [_make_unit("Слово")]
    fp1 = source_fp({"01_a": units}, excluded_sections=[])
    fp2 = source_fp({"01_a": units}, excluded_sections=["00_b"])
    assert fp1 != fp2


def test_source_fp_stable_across_section_order():
    from audiobook.wordprov import source_fp
    fp1 = source_fp({"01_a": [_make_unit("Раз")], "02_b": [_make_unit("Два")]})
    fp2 = source_fp({"02_b": [_make_unit("Два")], "01_a": [_make_unit("Раз")]})
    assert fp1 == fp2


def test_source_fp_does_not_include_manifest():
    from audiobook.wordprov import source_fp
    units = [_make_unit("Слово")]
    assert source_fp({"01_a": units}) == source_fp({"01_a": units})


# ---------------------------------------------------------------------------
# manifest_fp mutation tests
# ---------------------------------------------------------------------------

def test_manifest_fp_sensitive_to_text_change():
    from audiobook.wordprov import manifest_fp
    rows_a = [{"id": "0001", "n": 1, "text": "Один", "pause_after_ms": 0, "open_end": False, "leadin": None}]
    rows_b = [{"id": "0001", "n": 1, "text": "Два", "pause_after_ms": 0, "open_end": False, "leadin": None}]
    assert manifest_fp({"01_t": rows_a}) != manifest_fp({"01_t": rows_b})


def test_manifest_fp_sensitive_to_pause_change():
    from audiobook.wordprov import manifest_fp
    rows_a = [{"id": "0001", "n": 1, "text": "Один", "pause_after_ms": 0, "open_end": False, "leadin": None}]
    rows_b = [{"id": "0001", "n": 1, "text": "Один", "pause_after_ms": 500, "open_end": False, "leadin": None}]
    assert manifest_fp({"01_t": rows_a}) != manifest_fp({"01_t": rows_b})


def test_manifest_fp_stable_on_status_change():
    from audiobook.wordprov import manifest_fp
    base = {"id": "0001", "n": 1, "text": "Один", "pause_after_ms": 0, "open_end": False, "leadin": None}
    assert manifest_fp({"01_t": [{**base, "status": "pending"}]}) == \
           manifest_fp({"01_t": [{**base, "status": "done", "duration_ms": 1234}]})


def test_manifest_fp_stable_on_seed_change():
    from audiobook.wordprov import manifest_fp
    base = {"id": "0001", "n": 1, "text": "Один", "pause_after_ms": 0, "open_end": False, "leadin": None}
    assert manifest_fp({"01_t": [{**base, "seed_override": None}]}) == \
           manifest_fp({"01_t": [{**base, "seed_override": 999}]})


# ---------------------------------------------------------------------------
# Gold identity / neighbor staleness
# ---------------------------------------------------------------------------

def test_gold_identity_basic():
    from audiobook.wordprov import gold_identity
    units = [_make_unit("Начало"), _make_unit("Привет мир"), _make_unit("Конец")]
    gi = gold_identity("01_test", units, unit_id=1, unit_token_index=0)
    assert gi["form_source"] == "Привет"
    assert gi["source_key"] == "01_test|1|0"
    assert "context_sha256" in gi


def test_gold_identity_neighbor_stale():
    from audiobook.wordprov import gold_identity
    units_a = [_make_unit("Начало"), _make_unit("Привет мир"), _make_unit("Конец")]
    units_b = [_make_unit("CHANGED"), _make_unit("Привет мир"), _make_unit("Конец")]
    gi_a = gold_identity("01_test", units_a, unit_id=1, unit_token_index=0)
    gi_b = gold_identity("01_test", units_b, unit_id=1, unit_token_index=0)
    assert gi_a["context_sha256"] != gi_b["context_sha256"]


def test_gold_identity_distant_stable():
    from audiobook.wordprov import gold_identity
    units_a = [_make_unit("Начало"), _make_unit("Привет мир"), _make_unit("Конец")]
    units_b = [_make_unit("Начало"), _make_unit("Привет мир"), _make_unit("Конец"), _make_unit("Дополнительно")]
    gi_a = gold_identity("01_test", units_a, unit_id=1, unit_token_index=0)
    gi_b = gold_identity("01_test", units_b, unit_id=1, unit_token_index=0)
    assert gi_a["context_sha256"] == gi_b["context_sha256"]


def test_gold_identity_context_changes_on_text_edit():
    from audiobook.wordprov import gold_identity
    gi_a = gold_identity("01_test", [_make_unit("Привет мир")], 0, 0)
    gi_b = gold_identity("01_test", [_make_unit("Привет свет")], 0, 0)
    assert gi_a["context_sha256"] != gi_b["context_sha256"]


# ---------------------------------------------------------------------------
# Alignment tests
# ---------------------------------------------------------------------------

def test_alignment_exact():
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    trace = _make_trace("0001", "Привет мир")
    occs, _, _ = _run(units, chunks, [trace])
    for occ in occs:
        assert occ.alignment_status == "aligned"
        assert occ.su_chunk_id == "0001"
        assert occ.form_synth is not None


def test_alignment_fold_yo():
    units = [_make_unit("Идет")]
    chunks = [_make_chunk(1, "Идет")]
    trace = _make_trace("0001", "Идёт")
    occs, _, _ = _run(units, chunks, [trace])
    assert occs[0].alignment_status == "aligned"
    assert occs[0].form_synth == "Идёт"
    assert occs[0].form_analysis == "Идёт"


def test_alignment_no_trace_unsupported():
    units = [_make_unit("Привет")]
    chunks = [_make_chunk(1, "Привет")]
    occs, _, _ = _run(units, chunks, traces=None)
    assert occs[0].alignment_status == "trace_unsupported"
    assert occs[0].su_chunk_id is None


def test_alignment_fragment_mismatch():
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    trace = _make_trace("0001", "Привет")  # one word instead of two
    occs, _, _ = _run(units, chunks, [trace])
    for occ in occs:
        assert occ.alignment_status == "fragment_mismatch"
        assert occ.su_chunk_id is None


def test_alignment_prep_token_mismatch():
    units = [_make_unit("Привет")]
    chunks = [_make_chunk(1, "Привет")]
    trace = _make_trace("0001", "Пока")  # different word
    occs, _, _ = _run(units, chunks, [trace])
    assert occs[0].alignment_status == "prep_token_mismatch"


def test_alignment_unaligned_uses_form_source():
    units = [_make_unit("Привет")]
    chunks = [_make_chunk(1, "Привет")]
    trace = _make_trace("0001", "Пока")
    occs, ana_text, _ = _run(units, chunks, [trace])
    assert occs[0].form_analysis == "Привет"
    assert ana_text[occs[0].ana_start:occs[0].ana_end] == "Привет"


# ---------------------------------------------------------------------------
# Multi-unit analysis string
# ---------------------------------------------------------------------------

def test_ana_text_separator():
    from audiobook.wordprov import build_analysis_text
    units = [_make_unit("Первый"), _make_unit("Второй")]
    ana_text, _ = build_analysis_text(units, {})
    assert ana_text == "Первый\nВторой"


def test_ana_text_substitution_second_unit():
    from audiobook.wordprov import build_analysis_text
    units = [_make_unit("Идет"), _make_unit("Дождь")]
    fm = {(0, 0, 4): "Идёт", (1, 0, 5): "Дождь"}
    ana_text, offset_map = build_analysis_text(units, fm)
    for key, word in [((0, 0, 4), "Идёт"), ((1, 0, 5), "Дождь")]:
        start, end = offset_map[key]
        assert ana_text[start:end] == word


def test_ana_text_multi_unit_lc():
    units = [_make_unit("Первый"), _make_unit("Второй")]
    chunks = [_make_chunk(1, "Первый"), _make_chunk(2, "Второй")]
    t1 = _make_trace("0001", "Первый")
    t2 = _make_trace("0002", "Второй")
    occs, ana_text, _ = _run(units, chunks, [t1, t2])
    assert "\n" in ana_text
    for occ in occs:
        assert ana_text[occ.ana_start:occ.ana_end] == occ.form_analysis


# ---------------------------------------------------------------------------
# TSV round-trip
# ---------------------------------------------------------------------------

def test_round_trip_tsv():
    from audiobook.wordprov import serialize_occ, parse_occ_row
    units = [_make_unit("Привет мир")]
    chunks = [_make_chunk(1, "Привет мир")]
    trace = _make_trace("0001", "Привет мир")
    occs, _, _ = _run(units, chunks, [trace])
    for occ in occs:
        row_str = serialize_occ(occ)
        parsed = parse_occ_row(row_str)
        assert parsed["source_key"] == occ.source_key
        assert parsed["form_source"] == occ.form_source
        assert parsed["unit_token_index"] == occ.unit_token_index
        assert parsed["norm_start"] == occ.norm_start
        assert parsed["norm_end"] == occ.norm_end
        assert parsed["alignment_status"] == occ.alignment_status
        assert parsed["su_fragment"] == occ.su_fragment


def test_round_trip_null_fields():
    from audiobook.wordprov import serialize_occ, parse_occ_row
    units = [_make_unit("Привет")]
    chunks = [_make_chunk(1, "Привет")]
    trace = _make_trace("0001", "Пока")
    occs, _, _ = _run(units, chunks, [trace])
    occ = occs[0]
    assert occ.su_chunk_id is None
    parsed = parse_occ_row(serialize_occ(occ))
    assert parsed["su_chunk_id"] is None
    assert parsed["su_fragment"] is None


def test_round_trip_full_serialize():
    from audiobook.wordprov import serialize_tsv, parse_tsv
    units = [_make_unit("Тест")]
    chunks = [_make_chunk(1, "Тест")]
    occs, _, _ = _run(units, chunks)
    text = serialize_tsv(occs)
    restored = parse_tsv(text)
    assert len(restored) == len(occs)
    assert restored[0].source_key == occs[0].source_key


# ---------------------------------------------------------------------------
# PYTHONHASHSEED determinism
# ---------------------------------------------------------------------------

def test_source_fp_determinism():
    script = """\
from audiobook.wordprov import source_fp
units = [{"type": "text", "text": "Привет мир"}]
print(source_fp({"01_test": units}))
"""
    hashes = set()
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0, result.stderr
        hashes.add(result.stdout.strip())
    assert len(hashes) == 1, f"source_fp differed across seeds: {hashes}"


def test_manifest_fp_determinism():
    script = """\
from audiobook.wordprov import manifest_fp
rows = [{"id": "0001", "n": 1, "text": "Один", "pause_after_ms": 0, "open_end": False, "leadin": None}]
print(manifest_fp({"01_t": rows}))
"""
    hashes = set()
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0, result.stderr
        hashes.add(result.stdout.strip())
    assert len(hashes) == 1


# ---------------------------------------------------------------------------
# I3: production modules must not import wordprov
# ---------------------------------------------------------------------------

def test_i3_no_production_import_of_wordprov():
    guarded = ["synth", "worker", "voicecfg", "pronounce", "engine"]
    src = REPO_ROOT / "src" / "audiobook"
    for name in guarded:
        p = src / f"{name}.py"
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "wordprov" not in alias.name, f"{name}.py imports wordprov"
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "wordprov" not in mod, f"{name}.py imports from wordprov"


def test_fix_r1_three_fragment_literal_oracle(monkeypatch):
    import dataclasses
    import numpy as np
    from audiobook import sutrace, synth
    from audiobook.stress_facts import apply_facts

    text = "Альфа, бета, гамма?"  # Synthetic enum, never manuscript text.
    cfg = {"text_prep": {"ensure_terminal": False}, "render": {},
           "pauses_ms": {"enum_pause_ms": 100, "sentence": 200}}
    row = _make_chunk(1, text)
    calls = []

    class FakeEngine:
        def synth(self, text, seed, **kw):
            calls.append(text)
            return np.zeros(0, dtype=np.float32)

    table = {"Альфа": "Альфа", "бета": "бета", "гамма": "гамма"}
    synth._synth_one_chunk(row, cfg, table, " .", FakeEngine(), retries=0)
    assert calls == ["Альфа .", "бета .", "гамма ."]
    monkeypatch.setattr(sutrace, "_read_manifest", lambda _: [row])
    traces = sutrace.trace_section("01_test", cfg, table, " .")
    assert [t.prep_text for t in traces] == calls
    occs, analysis, _ = _run([_make_unit(text)], [row], traces)
    assert [(o.alignment_status, o.su_fragment, o.su_token_index) for o in occs] == [
        ("aligned", 0, 0), ("aligned", 1, 0), ("aligned", 2, 0)]
    by_su = {(t.chunk_id, t.fragment): t for t in traces}
    enriched = [apply_facts(o, by_su[o.su_chunk_id, o.su_fragment]) for o in occs]
    assert [o.f1_rule for o in enriched] == ["Альфа", "бета", "гамма"]
    for before, after in zip(occs, enriched):
        assert dataclasses.astuple(before)[:21] == dataclasses.astuple(after)[:21]
        assert analysis[after.ana_start:after.ana_end] == after.form_analysis


@pytest.mark.parametrize("status,text", [
    ("trace_unsupported", ""), ("trace_unsupported", "Альфа"),
    ("trace_mismatch", "Альфа"),
])
def test_fix_r2_trace_status_before_alignment(status, text):
    trace = _make_trace("0001", text, status=status)
    occs, _, _ = _run([_make_unit("Альфа")], [_make_chunk(1, "Альфа")], [trace])
    assert [(o.alignment_status, o.su_chunk_id) for o in occs] == [(status, None)]


@pytest.mark.parametrize("status", ["trace_unsupported", "trace_mismatch"])
def test_fix_r2_mixed_fragment_failure(status):
    traces = []
    for i, (text, st) in enumerate([("Альфа", status), ("бета", "ok")]):
        trace = _make_trace("0001", text, status=st)
        trace.fragment = i
        traces.append(trace)
    occs, _, _ = _run([_make_unit("Альфа бета")], [_make_chunk(1, "Альфа бета")], traces)
    assert [o.alignment_status for o in occs] == [status, status]
    assert all(o.su_token_index is None for o in occs)


@pytest.mark.skipif(
    not (REPO_ROOT / "out" / "t15_7" / "baseline" / "baseline.json").exists(),
    reason="Protected S2 baseline unavailable; corpus gate BLOCKED",
)
def test_fix_real_snapshot_every_word(monkeypatch):
    """Read-only aggregate gate; never emit corpus values on failure."""
    import json
    import re
    from collections import Counter
    import yaml
    from audiobook import paths, sutrace
    from audiobook.chunker import load_units
    from audiobook.pronounce import load_table
    from audiobook.sutrace import trace_section
    from audiobook.unitmap import map_section
    from audiobook.wordprov import (process_section_occs, validate_manifest_accesses,
                                    MANIFEST_FP_FIELDS, RecordingManifestRow)

    baseline = json.loads((REPO_ROOT / "out" / "t15_7" / "baseline" / "baseline.json").read_bytes())
    cfg = yaml.safe_load((paths.ROOT / "config.yaml").read_text(encoding="utf-8"))
    table = load_table()
    counts = Counter()
    statuses = Counter()
    chunk_statuses = Counter()
    for section in baseline["sections"]:
        units = load_units(*section.split("_", 1))
        rows = [json.loads(line) for line in
                (paths.OUT / "sections" / section / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        trace_accesses = set()
        guarded = [RecordingManifestRow(r, trace_accesses) for r in rows]
        with monkeypatch.context() as scoped:
            scoped.setattr(sutrace, "_read_manifest", lambda _: guarded)
            traces = trace_section(section, cfg, table, cfg["model"].get("sentinel", ""))
        assert {"id", "text", "open_end", "leadin"} <= trace_accesses <= set(MANIFEST_FP_FIELDS)
        accessed = validate_manifest_accesses(rows, cfg, table, cfg["model"].get("sentinel", ""))
        assert accessed == frozenset(MANIFEST_FP_FIELDS), "Manifest access contract failure"
        expected = [r for r in baseline["su_records"] if r["section"] == section]
        parity = [(t.section, t.chunk_id, t.fragment, t.final_sha256, t.phrase_sha256)
                  for t in traces] == [(r["section"], r["chunk_id"], r["fragment"],
                                        r["final_sha256"], r["phrase_sha256"]) for r in expected]
        assert parity, "SU identity/order/input parity failure"
        assert all(t.status == "ok" for t in traces), "Non-ok real trace: STOP"
        sm = map_section(units, rows, section=section)
        spans = {s.chunk_id: s for s in sm.spans}
        by_su = {(t.chunk_id, t.fragment): t for t in traces}
        occs, analysis, _ = process_section_occs(section, units, rows, traces)
        expected_keys = [(uid, i) for uid, u in enumerate(units)
                         for i, _ in enumerate(re.finditer(r"[а-яёА-ЯЁ]+", u["text"]))]
        actual_keys = [(int(o.unit_id), o.unit_token_index) for o in occs]
        assert actual_keys == expected_keys, "Source word identity/order failure"
        for o in occs:
            atom = sm.stream[o.atom_index]
            span = spans[o.chunk_id]
            la = units[int(o.unit_id)]["text"][o.norm_start:o.norm_end] == o.form_source
            lb = (atom.text[o.atom_char_start:o.atom_char_end] == o.form_source
                  and o.norm_start == atom.start + o.atom_char_start
                  and span.atom_start <= o.atom_index < span.atom_end)
            lc = analysis[o.ana_start:o.ana_end] == o.form_analysis
            assert la and lb and lc, "Real source link failure: STOP"
            if o.alignment_status == "aligned":
                t = by_su[o.su_chunk_id, o.su_fragment]
                words = re.findall(r"[а-яёА-ЯЁ]+", t.prep_text[t.pad_len:])
                su_link = (words[o.su_token_index] == o.form_synth == o.form_analysis
                           and o.form_source.lower().replace("ё", "е") == o.form_synth.lower().replace("ё", "е"))
                assert su_link, "Real SU word link failure: STOP"
            statuses[o.alignment_status] += 1
        counts.update(sections=1, units=len(units), atoms=len(sm.stream),
                      sus=len(traces), occurrences=len(occs))
        for row in rows:
            aligned = all(o.alignment_status == "aligned" for o in occs if o.chunk_id == row["id"])
            chunk_statuses["aligned" if aligned else "mismatched"] += 1
    assert counts == {"sections": 56, "units": 4624, "atoms": 77998,
                      "sus": 5127, "occurrences": 76036}
    assert statuses == {"aligned": 76033, "prep_token_mismatch": 3}
    assert chunk_statuses == {"aligned": 5124, "mismatched": 3}


def test_fix_r4_excluded_source_payload():
    from audiobook.wordprov import source_fp
    data = {"01_test": [_make_unit("Альфа")], "02_test": [_make_unit("Бета")]}
    original = source_fp(data, ["02_test"])
    data["02_test"] = [_make_unit("Гамма")]
    assert source_fp(data, ["02_test"]) == original
    data["01_test"] = [_make_unit("Дельта")]
    assert source_fp(data, ["02_test"]) != original
    assert source_fp(data, []) != source_fp(data, ["02_test"])
    assert source_fp(dict(reversed(list(data.items()))), ["02_test"]) == source_fp(data, ["02_test"])


def test_fix_r5_unexpected_observed_manifest_read(monkeypatch):
    from audiobook import synth
    from audiobook.unitmap import AnnotationError
    from audiobook.wordprov import validate_manifest_accesses
    original = synth.row_leadin

    def added_reader(row):
        row.get("unexpected_analytic")
        return original(row)

    monkeypatch.setattr(synth, "row_leadin", added_reader)
    with pytest.raises(AnnotationError, match="MANIFEST_ACCESS_UNDECLARED"):
        validate_manifest_accesses([_make_chunk(1, "Альфа")], {}, {}, "")


@pytest.mark.parametrize("access", [lambda r: r["unexpected_analytic"],
                                   lambda r: r.get("unexpected_analytic"),
                                   lambda r: "unexpected_analytic" in r])
def test_fix_r5_analysis_read_guard(monkeypatch, access):
    from audiobook import unitmap
    original = unitmap.map_section

    def observed_reader(units, rows, **kw):
        access(rows[0])
        return original(units, rows, **kw)

    monkeypatch.setattr(unitmap, "map_section", observed_reader)
    with pytest.raises(unitmap.AnnotationError, match="MANIFEST_ACCESS_UNDECLARED"):
        _run([_make_unit("Альфа")], [_make_chunk(1, "Альфа", unexpected_analytic=1)])


@pytest.mark.parametrize("access", [lambda r: r["unexpected_analytic"],
                                   lambda r: r.get("unexpected_analytic"),
                                   lambda r: "unexpected_analytic" in r])
def test_fix_r5_actual_sutrace_read_guard(monkeypatch, access):
    from audiobook import sutrace, synth
    from audiobook.wordprov import RecordingManifestRow
    from audiobook.unitmap import AnnotationError
    row = RecordingManifestRow(_make_chunk(1, "Альфа", unexpected_analytic=1))
    original = synth.row_leadin

    def observed_reader(row):
        access(row)
        return original(row)

    monkeypatch.setattr(synth, "row_leadin", observed_reader)
    monkeypatch.setattr(sutrace, "_read_manifest", lambda _: [row])
    with pytest.raises(AnnotationError, match="MANIFEST_ACCESS_UNDECLARED"):
        sutrace.trace_section("01_test", {}, {}, "")


@pytest.mark.parametrize("field,value", [("n", 2), ("id", "0002"), ("text", "Бета"),
                                        ("pause_after_ms", 100), ("open_end", True), ("leadin", "Ввод")])
def test_fix_r5_every_manifest_field_mutates_fp(field, value):
    from audiobook.wordprov import manifest_fp
    row = _make_chunk(1, "Альфа", open_end=False, leadin=None)
    assert manifest_fp({"01_test": [row]}) != manifest_fp({"01_test": [{**row, field: value}]})


def test_fix_r5_optional_and_irrelevant_manifest_fields():
    from audiobook.wordprov import manifest_fp, validate_manifest_accesses, MANIFEST_FP_FIELDS
    row = _make_chunk(1, "Альфа")
    cfg = {"text_prep": {"ensure_terminal": False}}
    assert validate_manifest_accesses([row], cfg, {}, "") == frozenset(MANIFEST_FP_FIELDS)
    assert manifest_fp({"01_test": [row]}) != manifest_fp({"01_test": [{**row, "leadin": None}]})
    assert manifest_fp({"01_test": [row]}) != manifest_fp({"01_test": [{**row, "leadin": ""}]})
    for name in ("status", "qc", "duration_ms", "seed_override", "hash"):
        assert manifest_fp({"01_test": [row]}) == manifest_fp({"01_test": [{**row, name: 123}]})


def test_fix_r3_provenance_after_leadin_length_change():
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook.stress_facts import apply_facts
    text = "Альфа бета гамма"
    table = {"Альфа": "+++Альфа", "бета": "бета++", "гамма": "++++гамма", "Ввод": "++++Ввод"}
    trace = _trace_su("01_test", "0001", None, text, False,
                      _DeepRecordingConfig({"text_prep": {"ensure_terminal": False}}),
                      "Ввод", table, " .")
    occs, _, _ = _run([_make_unit(text)], [_make_chunk(1, text)], [trace])
    assert [(o.form_synth, o.su_token_index) for o in occs] == [("Альфа", 0), ("бета", 1), ("гамма", 2)]
    assert [apply_facts(o, trace).f1_rule for o in occs] == ["Альфа", "бета", "гамма"]


def _tsv_probe():
    from audiobook.wordprov import to_tsv_row
    occs, _, _ = _run([_make_unit("Альфа")], [_make_chunk(1, "Альфа")])
    return to_tsv_row(occs[0]).split("\t")


@pytest.mark.parametrize("column,value", [
    (0, ""), (1, "bad_section"), (2, "01"), (3, "+1"), (3, "-1"), (3, "01"),
    (3, "١"), (3, ""), (17, "00"), (18, "-1"), (20, "ALIGNED"),
    (22, "2"), (22, "true"), (23, "bad"), (24, "APPROVED"),
    (25, "+0"), (26, "2"), (27, "01"), (28, "ok"), (29, "-1"),
    (30, "BAD"), (31, "BAD"), (32, "00"), (33, "OK"), (34, "bad_reason"),
    (6, "альфа\tбета"), (6, "альфа\nбета"), (6, "альфа\rбета"),
    (6, "альфа\x00"), (6, "\ud800"), (6, "альфа\u2028бета"),
])
def test_fix_r7_invalid_cells_shared_validation(column, value):
    from audiobook.wordprov import from_tsv_row, parse_occ_row
    from audiobook.unitmap import AnnotationError
    cells = _tsv_probe()
    cells[column] = value
    for reader, argument in [(from_tsv_row, cells), (parse_occ_row, "\t".join(cells))]:
        with pytest.raises(AnnotationError, match="TSV_INVALID"):
            reader(argument)


@pytest.mark.parametrize("mode", ["header", "extra", "missing", "blank_line", "no_final_lf", "crlf"])
def test_fix_r7_invalid_document(mode):
    from audiobook.wordprov import tsv_header, parse_tsv
    from audiobook.unitmap import AnnotationError
    header, row = tsv_header(), "\t".join(_tsv_probe())
    text = header + "\n" + row + "\n"
    if mode == "header":
        text = "wrong\n" + row + "\n"
    elif mode == "extra":
        text = header + "\n" + row + "\textra\n"
    elif mode == "missing":
        text = header + "\n" + row.rsplit("\t", 1)[0] + "\n"
    elif mode == "blank_line":
        text += "\n"
    elif mode == "no_final_lf":
        text = text[:-1]
    elif mode == "crlf":
        text = text.replace("\n", "\r\n")
    with pytest.raises(AnnotationError, match="TSV_INVALID"):
        parse_tsv(text)


def test_fix_r7_byte_identical_final_lf():
    from audiobook.wordprov import tsv_header, parse_tsv, serialize_tsv
    text = tsv_header() + "\n" + "\t".join(_tsv_probe()) + "\n"
    assert serialize_tsv(parse_tsv(text)).encode("utf-8") == text.encode("utf-8")
    assert serialize_tsv(parse_tsv(tsv_header() + "\n")) == tsv_header() + "\n"


def test_fix_r7_literal_35_column_wire_oracle():
    from audiobook.wordprov import parse_tsv, serialize_tsv, tsv_header
    header = ("source_key section unit_id unit_token_index norm_start norm_end form_source "
              "chunk_n chunk_id chunk_word_index atom_index atom_char_start atom_char_end "
              "ana_start ana_end form_analysis su_chunk_id su_fragment su_token_index "
              "form_synth alignment_status f1_rule f1_phrase f1_flag f2_approval f2_vowel "
              "f3_verified f5_vowel f5_status f6_vowel f6_status expected_source "
              "expected_vowel status reason").replace(" ", "\t")
    row = ["01_test|0|0", "01_test", "0", "0", "0", "5", "Альфа",
           "1", "0001", "0", "0", "0", "5", "0", "5", "Альфа",
           "0001", "", "0", "Альфа", "aligned", "", "0", "none", "none", "",
           "0", "", "none", "", "not_run", "none", "", "unresolved", "ruaccent_not_run"]
    wire = header + "\n" + "\t".join(row) + "\n"
    assert len(row) == 35
    assert tsv_header() == header
    parsed = parse_tsv(wire)
    assert (parsed[0].source_key, parsed[0].su_fragment, parsed[0].f1_phrase) == ("01_test|0|0", None, False)
    assert serialize_tsv(parsed).encode("utf-8") == wire.encode("utf-8")


@pytest.mark.parametrize("field,value", [
    ("section", None), ("section", ""), ("form_source", "а\tб"), ("form_analysis", "а\nб"),
    ("chunk_n", True), ("chunk_n", -1), ("su_fragment", "0"), ("f1_phrase", 2),
    ("f3_verified", None), ("f6_status", "BAD"), ("f1_rule", ""), ("form_synth", ""),
    ("reason", "verified_disagreement;ruaccent_disagreement"), ("reason", "ruaccent_disagreement;ruaccent_disagreement"),
])
def test_fix_r7_writer_rejects_invalid_values(field, value):
    from audiobook.wordprov import to_tsv_row
    from audiobook.unitmap import AnnotationError
    occs, _, _ = _run([_make_unit("Альфа")], [_make_chunk(1, "Альфа")])
    setattr(occs[0], field, value)
    with pytest.raises(AnnotationError, match="TSV_INVALID"):
        to_tsv_row(occs[0])


def test_fix_r1_wrong_fragment_cannot_supply_facts():
    from audiobook.stress_facts import apply_facts
    from audiobook.unitmap import AnnotationError
    trace = _make_trace("0001", "Альфа")
    occs, _, _ = _run([_make_unit("Альфа")], [_make_chunk(1, "Альфа")], [trace])
    trace.fragment = 0
    with pytest.raises(AnnotationError, match="FACT_TRACE_ASSOCIATION"):
        apply_facts(occs[0], trace)


def test_fix_r7_out_of_order_rows_rejected():
    from audiobook.wordprov import parse_tsv, serialize_tsv, tsv_header, to_tsv_row
    from audiobook.unitmap import AnnotationError
    occs, _, _ = _run([_make_unit("Альфа бета")], [_make_chunk(1, "Альфа бета")])
    text = tsv_header() + "\n" + "\n".join(to_tsv_row(o) for o in reversed(occs)) + "\n"
    with pytest.raises(AnnotationError, match="TSV_INVALID"):
        parse_tsv(text)
    with pytest.raises(AnnotationError, match="TSV_INVALID"):
        serialize_tsv(list(reversed(occs)))


def test_fix_r5_missing_leadin_is_an_observed_dependency():
    from audiobook.synth import prepare_synth_text, row_leadin
    from audiobook.wordprov import manifest_fp
    row = _make_chunk(1, "Альфа")
    explicit_null = {**row, "leadin": None}
    cfg = {"text_prep": {"ensure_terminal": False},
           "render": {"leadin": {"phrase": "Ввод", "max_chars": 20}}}
    auto = prepare_synth_text(row["text"], cfg, {}, "", row_leadin(row))
    disabled = prepare_synth_text(row["text"], cfg, {}, "", row_leadin(explicit_null))
    assert auto == ("Ввод Альфа", "Ввод")
    assert disabled == ("Альфа", None)
    assert manifest_fp({"01_test": [row]}) != manifest_fp({"01_test": [explicit_null]})
