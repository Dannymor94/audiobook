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
