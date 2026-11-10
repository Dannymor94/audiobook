"""Tests for stress_fp.stress_params() — T15-6D1."""
import json

import pytest

from audiobook.stress_fp import stress_params


def _cfg(stress=None, paragraph=900):
    cfg = {"pauses_ms": {"paragraph": paragraph}}
    if stress is not None:
        cfg["stress"] = stress
    return cfg


def test_top_n_default():
    assert stress_params({})["top_n"] == 300


def test_top_n_from_config():
    assert stress_params(_cfg(stress={"top_n": 150}))["top_n"] == 150


def test_paragraph_ms_from_pauses():
    assert stress_params(_cfg(paragraph=1200))["paragraph_ms"] == 1200


def test_paragraph_ms_default():
    assert stress_params({})["paragraph_ms"] == 900


def test_full_subtree_included():
    result = stress_params(_cfg(stress={"top_n": 300, "custom_key": 42}))
    assert result["custom_key"] == 42


def test_new_nested_key_auto_included():
    # Any key added to stress: in config is returned without code changes.
    result = stress_params(_cfg(stress={"top_n": 300, "foo": {"bar": True}}))
    assert result["foo"] == {"bar": True}


def test_none_cfg_returns_defaults():
    result = stress_params(None)
    assert result["top_n"] == 300
    assert result["paragraph_ms"] == 900


def test_no_stress_section_still_has_defaults():
    result = stress_params({"pauses_ms": {"paragraph": 800}})
    assert result["top_n"] == 300
    assert result["paragraph_ms"] == 800


def test_canonical_json_deterministic():
    cfg = _cfg(stress={"top_n": 300, "z_key": 1, "a_key": 2})
    r1 = json.dumps(stress_params(cfg), sort_keys=True, ensure_ascii=False)
    r2 = json.dumps(stress_params(cfg), sort_keys=True, ensure_ascii=False)
    assert r1 == r2


def test_changing_stress_key_changes_canonical():
    base = json.dumps(stress_params(_cfg(stress={"top_n": 300})), sort_keys=True)
    changed = json.dumps(stress_params(_cfg(stress={"top_n": 500})), sort_keys=True)
    assert base != changed


def test_changing_paragraph_ms_changes_canonical():
    base = json.dumps(stress_params(_cfg(paragraph=900)), sort_keys=True)
    changed = json.dumps(stress_params(_cfg(paragraph=1000)), sort_keys=True)
    assert base != changed


def test_does_not_mutate_input_cfg():
    cfg = _cfg(stress={"top_n": 300})
    stress_before = dict(cfg["stress"])
    stress_params(cfg)
    assert cfg["stress"] == stress_before
