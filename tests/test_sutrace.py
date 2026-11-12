"""Tests for src/audiobook/sutrace.py — T15-7.2 (includes WP-1-FIX R1/R2/R3)"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
SUTRACE_SRC = REPO_ROOT / "src" / "audiobook" / "sutrace.py"
ENUM_ORACLE = REPO_ROOT / "tests" / "fixtures" / "t15_7" / "synthetic" / "enum_oracle.json"
BASELINE_PATH = REPO_ROOT / "out" / "t15_7" / "baseline" / "baseline.json"

# ---------------------------------------------------------------------------
# Synthetic config helpers
# ---------------------------------------------------------------------------

_SHORT_CONFIG = {
    "text_prep": {"strip_quotes": False, "ensure_terminal": False},
    "render": {"leadin": {"phrase": "Carry.", "max_chars": 20}},
    "model": {"name": "test", "sentinel": " ."},
}
_LONG_CONFIG = {
    "text_prep": {"strip_quotes": False, "ensure_terminal": False},
    "render": {},
    "model": {"name": "test", "sentinel": " ."},
}

_EMPTY_TABLE: dict = {}


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Unit tests (no real corpus)
# ---------------------------------------------------------------------------

def test_normal_su_no_phrase():
    """Long text (>20 chars in this config) → phrase=None → phrase_sha256=None."""
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook import leadin as leadin_mod

    text = "This is a sufficiently long synthetic text."
    cfg = _DeepRecordingConfig(_LONG_CONFIG)
    t = _trace_su("s", "c1", None, text, False, cfg, leadin_mod.AUTO, _EMPTY_TABLE, " .")
    assert t.phrase_sha256 is None
    assert t.status == "ok"
    assert t.pad_len == 0
    assert t.final_sha256 == _sha256(t.prep_text)


def test_normal_su_with_phrase():
    """Short text (≤20 chars) → phrase fires → phrase_sha256 is set."""
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook import leadin as leadin_mod

    text = "Hi."  # well under 20
    cfg = _DeepRecordingConfig(_SHORT_CONFIG)
    t = _trace_su("s", "c2", None, text, False, cfg, leadin_mod.AUTO, _EMPTY_TABLE, " .")
    assert t.phrase_sha256 is not None
    assert t.phrase_sha256 == _sha256("Carry.")
    assert t.status == "ok"
    assert t.pad_len == len("Carry.") + 1


def test_phrase_none_vs_empty():
    """None phrase → phrase_sha256=None; empty string → distinct non-None sha256."""
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook import leadin as leadin_mod

    cfg_none = _DeepRecordingConfig(_LONG_CONFIG)
    t_none = _trace_su("s", "c3", None, "Test text.", False, cfg_none, leadin_mod.AUTO,
                       _EMPTY_TABLE, " .")
    assert t_none.phrase_sha256 is None

    # Provide a stored phrase="" (empty string) directly
    t_empty = _trace_su("s", "c4", None, "Test text.", False, cfg_none, "",
                        _EMPTY_TABLE, " .")
    # empty string phrase: phrase is "" (not None), so sha256("") != None
    assert t_empty.phrase_sha256 == _sha256("")
    assert t_empty.phrase_sha256 != t_none.phrase_sha256


def test_enum_fragments():
    """Enum oracle: exact SU set, final/phrase sha match for all 3 fragments."""
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook import leadin as leadin_mod
    from audiobook.synth import chunk_fragments

    oracle = json.loads(ENUM_ORACLE.read_bytes())
    config = oracle["config"]
    text = oracle["text"]
    sentinel = config["model"]["sentinel"]
    table: dict = {}

    frags = chunk_fragments(text, config)
    assert len(frags) == len(oracle["fragments"])

    for fi, (frag_text, _pause, is_enum) in enumerate(frags):
        frag = frag_text.rstrip("?") if is_enum and frag_text.endswith("?") else frag_text
        cfg = _DeepRecordingConfig(config)
        t = _trace_su("syn", "row0", fi, frag, False, cfg, leadin_mod.AUTO, table, sentinel)
        exp = oracle["fragments"][fi]
        assert t.status == "ok", f"fragment {fi} not ok: {t.status}"
        assert t.final_sha256 == exp["final_sha256"], f"fi={fi} final_sha256 mismatch"
        assert t.phrase_sha256 == exp["phrase_sha256"], f"fi={fi} phrase_sha256 mismatch"


def test_deterministic_hash():
    """Same input always yields identical sha values."""
    from audiobook.sutrace import _trace_su, _DeepRecordingConfig
    from audiobook import leadin as leadin_mod

    cfg1 = _DeepRecordingConfig(_SHORT_CONFIG)
    cfg2 = _DeepRecordingConfig(_SHORT_CONFIG)
    t1 = _trace_su("s", "x", None, "Hi.", False, cfg1, leadin_mod.AUTO, _EMPTY_TABLE, " .")
    t2 = _trace_su("s", "x", None, "Hi.", False, cfg2, leadin_mod.AUTO, _EMPTY_TABLE, " .")
    assert t1.final_sha256 == t2.final_sha256
    assert t1.phrase_sha256 == t2.phrase_sha256


def test_match_reconstruction():
    """Match reconstruction must equal pronounce.respell output."""
    from audiobook.sutrace import _reconstruct
    from audiobook.pronounce import respell, build_pattern

    table = {"foo": "FOO", "bar": "BAR"}
    text = "foo and bar are here"
    pat = build_pattern(table)
    matches = [{"start": m.start(), "end": m.end(), "key": m.group(0), "value": table[m.group(0)]}
               for m in pat.finditer(text)]
    assert _reconstruct(text, matches) == respell(text, table)


def test_config_keys_guard():
    """Extra undeclared config key accessed during prep → detected by guard."""
    from audiobook.sutrace import _DeepRecordingConfig, DECLARED_CONFIG_PATHS

    cfg = _DeepRecordingConfig({"text_prep": {}, "render": {}, "model": {}, "SECRET": 42})
    _ = cfg.get("text_prep")
    _ = cfg.get("SECRET")   # undeclared access
    unexpected = cfg._accessed - DECLARED_CONFIG_PATHS
    assert "SECRET" in unexpected


def test_ast_no_import_of_sutrace():
    """synth, worker, voicecfg, pronounce, engine must NOT import sutrace (I3)."""
    guarded = ["synth", "worker", "voicecfg", "pronounce", "engine"]
    src_dir = REPO_ROOT / "src" / "audiobook"
    for name in guarded:
        path = src_dir / f"{name}.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "sutrace" not in alias.name, f"{name}.py imports sutrace"
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "sutrace" not in mod, f"{name}.py imports from sutrace"


# ---------------------------------------------------------------------------
# R1 — Singleton enum must use row["text"] not frags[0][0]
# ---------------------------------------------------------------------------

def test_r1_singleton_enum_uses_row_text(tmp_path, monkeypatch):
    """R1: len(frags)==1 with enum_pause_ms>0 must use row['text'], not frags[0][0]."""
    import audiobook.paths as paths_mod
    from audiobook.synth import prepare_synth_text, chunk_fragments
    from audiobook.sutrace import trace_section
    from audiobook import leadin as leadin_mod

    row_text = " Hi. "   # leading/trailing space preserved by production
    enum_cfg = {
        "text_prep": {"strip_quotes": False, "ensure_terminal": False},
        "render": {},
        "pauses_ms": {"enum_pause_ms": 100, "sentence": 200},
        "model": {"name": "test", "sentinel": " ."},
    }
    sentinel = " ."
    table: dict = {}

    # Confirm chunk_fragments normalises the text (singleton but different string)
    frags = chunk_fragments(row_text, enum_cfg)
    assert len(frags) == 1, "Need singleton for this test"
    assert frags[0][0] != row_text, "frags[0][0] must differ for test to be meaningful"

    # Production truth: use row_text directly
    prod_final, _ = prepare_synth_text(row_text, enum_cfg, table, sentinel,
                                       leadin_mod.AUTO, False)
    # Incorrect path: use frags[0][0]
    frag_final, _ = prepare_synth_text(frags[0][0], enum_cfg, table, sentinel,
                                       leadin_mod.AUTO, False)
    assert prod_final != frag_final, "row_text and frags[0][0] must yield different finals"

    # Build a temporary manifest
    section = "test_r1"
    sec_dir = tmp_path / "sections" / section
    sec_dir.mkdir(parents=True)
    row = {"id": "0001", "n": 1, "text": row_text, "hash": "abc123",
           "pause_after_ms": 0, "status": "pending"}
    (sec_dir / "manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(paths_mod, "OUT", tmp_path)
    traces = trace_section(section, enum_cfg, table, sentinel)

    assert len(traces) == 1
    t = traces[0]
    assert t.fragment is None, "singleton must have fragment=None"
    assert t.status == "ok"
    # Must match production path (row_text), not frags[0][0]
    assert t.final_sha256 == _sha256(prod_final)
    assert t.final_sha256 != _sha256(frag_final)


# ---------------------------------------------------------------------------
# R2 — Fake-engine oracle: multi-fragment baseline matches production
# ---------------------------------------------------------------------------

def test_r2_enum_fake_engine_oracle():
    """R2: fixture capture matches independent fake-engine oracle for 3-fragment enum."""
    import numpy as np
    from audiobook.synth import _synth_one_chunk, prepare_synth_text, chunk_fragments
    from audiobook import leadin as leadin_mod

    oracle = json.loads(ENUM_ORACLE.read_bytes())
    config = oracle["config"]
    text = oracle["text"]
    sentinel = config["model"]["sentinel"]
    table: dict = {}

    class _FakeEngine:
        def __init__(self):
            self.calls: list[dict] = []
        def synth(self, synth_text: str, seed: int, **kw):
            self.calls.append({"text": synth_text, "phrase": kw.get("leadin")})
            return np.zeros(0, dtype=np.float32)

    row = {"id": "row0", "n": 1, "text": text, "hash": "deadbeef",
           "pause_after_ms": 0, "status": "pending"}
    engine = _FakeEngine()
    _synth_one_chunk(row, config, table, sentinel, engine, retries=0)

    assert len(engine.calls) == 3, f"expected 3 fragments, got {len(engine.calls)}"

    # Compare oracle expected values against what production actually passed
    frags = chunk_fragments(text, config)
    for fi, (frag_text, _pause, is_enum) in enumerate(frags):
        frag = frag_text.rstrip("?") if is_enum and frag_text.endswith("?") else frag_text
        exp_final, exp_phrase = prepare_synth_text(frag, config, table, sentinel)
        assert engine.calls[fi]["text"] == exp_final, f"fragment {fi}: engine text mismatch"

        exp_oracle = oracle["fragments"][fi]
        assert engine.calls[fi]["text"] == exp_oracle["final"], \
            f"fragment {fi}: engine text does not match oracle"
        assert _sha256(engine.calls[fi]["text"]) == exp_oracle["final_sha256"], \
            f"fragment {fi}: final_sha256 mismatch"


def test_r2_fixture_capture_matches_oracle(tmp_path, monkeypatch):
    """R2: fixture _capture_section matches oracle for synthetic enum row."""
    import sys
    import audiobook.paths as paths_mod

    oracle = json.loads(ENUM_ORACLE.read_bytes())
    config = oracle["config"]
    row_text = oracle["text"]
    sentinel = config["model"]["sentinel"]
    table: dict = {}

    section = "test_r2"
    sec_dir = tmp_path / "sections" / section
    sec_dir.mkdir(parents=True)
    row = {"id": "row0", "n": 1, "text": row_text, "hash": "deadbeef",
           "pause_after_ms": 0, "status": "pending"}
    (sec_dir / "manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(paths_mod, "OUT", tmp_path)
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from helpers.t15_7_fixture import _capture_section

    records = _capture_section(section, config, table, sentinel)
    assert len(records) == 3, f"expected 3 SU records, got {len(records)}"

    for fi, rec in enumerate(records):
        exp = oracle["fragments"][fi]
        assert rec["fragment"] == fi
        assert rec["final_sha256"] == exp["final_sha256"], f"fi={fi} final_sha256"
        assert rec["phrase_sha256"] == exp["phrase_sha256"], f"fi={fi} phrase_sha256"


def test_r2_singleton_fixture_uses_row_text(tmp_path, monkeypatch):
    """R2: fixture singleton row uses row['text'] — mirrors R1 for _capture_section."""
    import sys
    import audiobook.paths as paths_mod
    from audiobook.synth import prepare_synth_text, chunk_fragments
    from audiobook import leadin as leadin_mod

    row_text = " Hi. "
    enum_cfg = {
        "text_prep": {"strip_quotes": False, "ensure_terminal": False},
        "render": {},
        "pauses_ms": {"enum_pause_ms": 100, "sentence": 200},
        "model": {"name": "test", "sentinel": " ."},
    }
    sentinel = " ."
    table: dict = {}

    frags = chunk_fragments(row_text, enum_cfg)
    assert len(frags) == 1

    prod_final, _ = prepare_synth_text(row_text, enum_cfg, table, sentinel,
                                       leadin_mod.AUTO, False)

    section = "test_r2s"
    sec_dir = tmp_path / "sections" / section
    sec_dir.mkdir(parents=True)
    row = {"id": "0001", "n": 1, "text": row_text, "hash": "abc",
           "pause_after_ms": 0, "status": "pending"}
    (sec_dir / "manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(paths_mod, "OUT", tmp_path)
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from helpers.t15_7_fixture import _capture_section

    records = _capture_section(section, enum_cfg, table, sentinel)
    assert len(records) == 1
    assert records[0]["fragment"] is None
    assert records[0]["final_sha256"] == _sha256(prod_final)


# ---------------------------------------------------------------------------
# R3 — Nested config path recording
# ---------------------------------------------------------------------------

def test_r3_top_level_recorded():
    """R3: top-level config keys are recorded as plain path strings."""
    from audiobook.sutrace import _DeepRecordingConfig

    cfg = _DeepRecordingConfig({"text_prep": {"a": 1}, "render": {}})
    _ = cfg.get("text_prep")
    _ = cfg.get("render")
    assert "text_prep" in cfg._accessed
    assert "render" in cfg._accessed


def test_r3_nested_path_recorded():
    """R3: nested dict access records full dotted path."""
    from audiobook.sutrace import _DeepRecordingConfig

    cfg = _DeepRecordingConfig({"text_prep": {"strip_quotes": True, "ensure_terminal": False}})
    tp = cfg.get("text_prep")
    _ = tp.get("strip_quotes")
    _ = tp.get("ensure_terminal")
    assert "text_prep.strip_quotes" in cfg._accessed
    assert "text_prep.ensure_terminal" in cfg._accessed


def test_r3_nested_unknown_fails_closed():
    """R3: a nested key not in DECLARED_CONFIG_PATHS raises when guard runs."""
    from audiobook.sutrace import _DeepRecordingConfig, DECLARED_CONFIG_PATHS

    cfg = _DeepRecordingConfig({"text_prep": {"strip_quotes": True, "UNDECLARED": "x"}})
    tp = cfg.get("text_prep")
    _ = tp.get("strip_quotes")
    _ = tp.get("UNDECLARED")   # nested undeclared access
    unexpected = cfg._accessed - DECLARED_CONFIG_PATHS
    assert "text_prep.UNDECLARED" in unexpected, \
        "nested undeclared path must be detected by guard"


def test_r3_pauses_ms_recorded():
    """R3: pauses_ms.enum_pause_ms and pauses_ms.sentence are recorded."""
    from audiobook.sutrace import _DeepRecordingConfig

    cfg = _DeepRecordingConfig({"pauses_ms": {"enum_pause_ms": 300, "sentence": 200}})
    _ = cfg.get("pauses_ms", {}).get("enum_pause_ms", 0)
    _ = cfg.get("pauses_ms", {}).get("sentence", 350)
    assert "pauses_ms" in cfg._accessed
    assert "pauses_ms.enum_pause_ms" in cfg._accessed
    assert "pauses_ms.sentence" in cfg._accessed


def test_r3_contains_records_path():
    """R3: 'key in wrapper' records the dotted path."""
    from audiobook.sutrace import _DeepRecordingConfig

    cfg = _DeepRecordingConfig({"render": {"leadin": {"max_chars": 55}}})
    render_w = cfg.get("render")
    leadin_w = render_w.get("leadin")
    _ = "max_chars" in leadin_w
    assert "render.leadin.max_chars" in cfg._accessed


def test_r3_full_trace_no_unexpected(tmp_path, monkeypatch):
    """R3: trace_section with normal config records only declared paths — guard passes."""
    import audiobook.paths as paths_mod

    section = "test_r3"
    sec_dir = tmp_path / "sections" / section
    sec_dir.mkdir(parents=True)
    row = {"id": "0001", "n": 1, "text": "Hello world.", "hash": "abc",
           "pause_after_ms": 0, "status": "pending"}
    (sec_dir / "manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    cfg = {
        "text_prep": {"strip_quotes": False, "ensure_terminal": False},
        "render": {"leadin": {"phrase": "Carry.", "max_chars": 20}},
        "pauses_ms": {"enum_pause_ms": 0, "sentence": 200},
        "model": {"name": "test", "sentinel": " ."},
    }
    monkeypatch.setattr(paths_mod, "OUT", tmp_path)
    from audiobook.sutrace import trace_section
    # Must not raise
    traces = trace_section(section, cfg, {}, " .")
    assert len(traces) == 1
    assert traces[0].status == "ok"


def test_r3_unexpected_key_raises(tmp_path, monkeypatch):
    """R3: config with extra accessed key causes trace_section to raise ValueError."""
    import audiobook.paths as paths_mod

    section = "test_r3x"
    sec_dir = tmp_path / "sections" / section
    sec_dir.mkdir(parents=True)
    row = {"id": "0001", "n": 1, "text": "Test.", "hash": "abc",
           "pause_after_ms": 0, "status": "pending"}
    (sec_dir / "manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Patch voicecfg.prepare_text to access an extra key so we can trigger the guard
    import audiobook.voicecfg as voicecfg_mod
    original_prepare = voicecfg_mod.prepare_text

    def patched_prepare(text, config, open_end=False):
        _ = config.get("SECRET_KEY")   # undeclared key access
        return original_prepare(text, config, open_end)

    monkeypatch.setattr(paths_mod, "OUT", tmp_path)
    monkeypatch.setattr(voicecfg_mod, "prepare_text", patched_prepare)

    cfg = {
        "text_prep": {"strip_quotes": False, "ensure_terminal": False},
        "render": {},
        "pauses_ms": {"enum_pause_ms": 0},
        "model": {"name": "test", "sentinel": " ."},
        "SECRET_KEY": "oops",
    }
    from audiobook.sutrace import trace_section
    with pytest.raises(ValueError, match="Unexpected config keys"):
        trace_section(section, cfg, {}, " .")


# ---------------------------------------------------------------------------
# Baseline integration (skipped when S2 baseline not present)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not BASELINE_PATH.exists(), reason="S2 baseline not present")
def test_baseline_check():
    """--check reproduces D for the stored baseline."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from helpers.t15_7_fixture import check
    match, stored_D, fresh_D = check()
    assert match, f"baseline check FAIL: stored={stored_D} fresh={fresh_D}"
    assert stored_D != ""


@pytest.mark.skipif(not BASELINE_PATH.exists(), reason="S2 baseline not present")
def test_baseline_d_matches_accepted():
    """Baseline digest must match the accepted WP-1 value (R2 guard)."""
    ACCEPTED_D = "0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6"
    import hashlib
    actual_D = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    assert actual_D == ACCEPTED_D, (
        f"Baseline digest changed unexpectedly!\n"
        f"  stored: {actual_D}\n"
        f"  expected: {ACCEPTED_D}\n"
        "Do NOT overwrite the existing baseline to make this test pass."
    )


@pytest.mark.skipif(not BASELINE_PATH.exists(), reason="S2 baseline not present")
def test_sutrace_matches_baseline_all_sections():
    """N1: SUTrace final/phrase sha256 matches baseline for ALL 56 sections / 5127 SUs."""
    import yaml
    from audiobook import paths
    from audiobook.pronounce import load_table
    from audiobook.sutrace import trace_section

    bl = json.loads(BASELINE_PATH.read_bytes())
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    table = load_table()
    sentinel: str = config["model"].get("sentinel", "")

    total_su = 0
    non_ok = 0
    for sec in bl["sections"]:
        bl_records = [r for r in bl["su_records"] if r["section"] == sec]
        traces = trace_section(sec, config, table, sentinel)
        assert len(traces) == len(bl_records), \
            f"SU count mismatch in section {sec}: {len(traces)} vs {len(bl_records)}"
        for tr, bl_r in zip(traces, bl_records):
            assert tr.final_sha256 == bl_r["final_sha256"], \
                f"final_sha256 mismatch: section={sec} chunk={tr.chunk_id}"
            assert tr.phrase_sha256 == bl_r["phrase_sha256"], \
                f"phrase_sha256 mismatch: section={sec} chunk={tr.chunk_id}"
            if tr.status != "ok":
                non_ok += 1
        total_su += len(traces)

    assert total_su == 5127, f"Expected 5127 SUs, got {total_su}"
    assert non_ok == 0, \
        f"WP-1 ACCEPTANCE FAIL: {non_ok} non-ok SU(s) in full corpus trace"


# Keep old test name as an alias for backward compatibility with reports
@pytest.mark.skipif(not BASELINE_PATH.exists(), reason="S2 baseline not present")
def test_sutrace_matches_baseline():
    """Retained for report continuity; delegates to the full-corpus test."""
    test_sutrace_matches_baseline_all_sections()
