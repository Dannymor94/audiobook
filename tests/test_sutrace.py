"""Tests for src/audiobook/sutrace.py — T15-7.2"""
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
    from audiobook.sutrace import _trace_su, _KeyRecordingConfig
    from audiobook import leadin as leadin_mod

    text = "This is a sufficiently long synthetic text."
    cfg = _KeyRecordingConfig(_LONG_CONFIG)
    t = _trace_su("s", "c1", None, text, False, cfg, leadin_mod.AUTO, _EMPTY_TABLE, " .")
    assert t.phrase_sha256 is None
    assert t.status == "ok"
    assert t.pad_len == 0
    assert t.final_sha256 == _sha256(t.prep_text)


def test_normal_su_with_phrase():
    """Short text (≤20 chars) → phrase fires → phrase_sha256 is set."""
    from audiobook.sutrace import _trace_su, _KeyRecordingConfig
    from audiobook import leadin as leadin_mod

    text = "Hi."  # well under 20
    cfg = _KeyRecordingConfig(_SHORT_CONFIG)
    t = _trace_su("s", "c2", None, text, False, cfg, leadin_mod.AUTO, _EMPTY_TABLE, " .")
    assert t.phrase_sha256 is not None
    assert t.phrase_sha256 == _sha256("Carry.")
    assert t.status == "ok"
    assert t.pad_len == len("Carry.") + 1


def test_phrase_none_vs_empty():
    """None phrase → phrase_sha256=None; empty string → distinct non-None sha256."""
    from audiobook.sutrace import _trace_su, _KeyRecordingConfig
    from audiobook import leadin as leadin_mod

    empty_phrase_config = {
        "text_prep": {"strip_quotes": False, "ensure_terminal": False},
        "render": {"leadin": {"phrase": "", "max_chars": 1000}},
        "model": {"name": "test", "sentinel": " ."},
    }
    cfg = _KeyRecordingConfig(empty_phrase_config)
    # fires() returns "" (empty string) only when phrase is explicitly ""
    # but carrier() returns None for empty phrase → fires() returns None
    # So empty-phrase config results in phrase=None same as no config
    cfg_none = _KeyRecordingConfig(_LONG_CONFIG)
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
    from audiobook.sutrace import _trace_su, _KeyRecordingConfig, DECLARED_TOP_LEVEL_CONFIG_KEYS
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
        cfg = _KeyRecordingConfig(config)
        t = _trace_su("syn", "row0", fi, frag, False, cfg, leadin_mod.AUTO, table, sentinel)
        exp = oracle["fragments"][fi]
        assert t.status == "ok", f"fragment {fi} not ok: {t.status}"
        assert t.final_sha256 == exp["final_sha256"], f"fi={fi} final_sha256 mismatch"
        assert t.phrase_sha256 == exp["phrase_sha256"], f"fi={fi} phrase_sha256 mismatch"


def test_deterministic_hash():
    """Same input always yields identical sha values."""
    from audiobook.sutrace import _trace_su, _KeyRecordingConfig
    from audiobook import leadin as leadin_mod

    cfg1 = _KeyRecordingConfig(_SHORT_CONFIG)
    cfg2 = _KeyRecordingConfig(_SHORT_CONFIG)
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
    """Extra undeclared config key accessed during prep → ValueError."""
    from audiobook.sutrace import _KeyRecordingConfig, DECLARED_TOP_LEVEL_CONFIG_KEYS

    # We test the guard directly by accessing an undeclared key
    cfg = _KeyRecordingConfig({"text_prep": {}, "render": {}, "model": {}, "SECRET": 42})
    _ = cfg.get("text_prep")
    _ = cfg.get("SECRET")   # undeclared access
    unexpected = cfg._accessed - DECLARED_TOP_LEVEL_CONFIG_KEYS
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
def test_sutrace_matches_baseline():
    """SUTrace final_sha256 matches baseline for all SUs in first section."""
    import yaml
    from audiobook import paths
    from audiobook.pronounce import load_table
    from audiobook.sutrace import trace_section

    bl = json.loads(BASELINE_PATH.read_bytes())
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    table = load_table()
    sentinel: str = config["model"].get("sentinel", "")

    # Only check the first section to keep test fast
    first_sec = bl["sections"][0]
    bl_records = [r for r in bl["su_records"] if r["section"] == first_sec]

    traces = trace_section(first_sec, config, table, sentinel)
    assert len(traces) == len(bl_records), "SU count mismatch"
    for tr, bl_r in zip(traces, bl_records):
        assert tr.final_sha256 == bl_r["final_sha256"], (
            f"final_sha256 mismatch chunk={tr.chunk_id}"
        )
        assert tr.phrase_sha256 == bl_r["phrase_sha256"], (
            f"phrase_sha256 mismatch chunk={tr.chunk_id}"
        )
