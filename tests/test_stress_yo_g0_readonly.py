"""Source-private G0 coverage CLI: only synthetic fixtures, never actual book words."""
from __future__ import annotations

import json

import pytest

from audiobook import paths, stress_eval, synth, yo
from audiobook import __main__ as audiobook_main
from stress_yo_g0_readonly import (
    AuditFailure, audit_local, content_snapshot, prep_config_digest,
)
from test_stress_eval_sample import context_for


def prepare_synthetic(tmp_path, monkeypatch, *, raw="Елепа.", config=None):
    config = config or {"text_prep": {"yo_restore": False}}
    units = [{"type": "text", "text": raw}]
    text, out = tmp_path / "text", tmp_path / "out"
    text.mkdir()
    (out / "sections" / "01_test").mkdir(parents=True)
    (text / "synthetic.norm.txt").write_text(raw, encoding="utf-8")
    (out / "sections" / "01_test" / "manifest.jsonl").write_text(
        json.dumps({"id": "0001", "text": raw}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    context = context_for(units)
    monkeypatch.setattr(stress_eval, "_load_context", lambda _: context)
    monkeypatch.setattr(audiobook_main, "load_config", lambda: config)
    yo._book_map.cache_clear()
    return config


def test_synthetic_current_sample_coverage_is_aggregate_only(tmp_path, monkeypatch):
    config = prepare_synthetic(tmp_path, monkeypatch)
    try:
        m = audit_local(config)
        assert m["status"] == "G0_COVERAGE_MEASURED"
        assert m["counts"]["eligible"] == 1
        assert m["counts"]["selected"] == 1
        assert m["counts"]["selected_verified"] == 1
        assert m["counts"]["selected_pre_restored"] == 0
        assert m["counts"]["eligible_pre_restored"] == 0
        assert m["counts"]["selected_pre_0_post_0"] == 1
        assert m["counts"]["selected_pre_0_post_1"] == 0
        assert m["counts"]["selected_pre_1_post_0"] == 0
        assert m["counts"]["selected_pre_1_post_1"] == 0
        for prefix in ("eligible", "selected"):
            assert m["counts"][prefix + "_verified"] == 1
            for reason in ("manifest", "source_stream", "fragments", "source_key", "prep"):
                assert m["counts"][prefix + "_unsupported_" + reason] == 0
        for item in m["selected_by_stratum"].values():
            assert set(item) == {
                "verified", "unsupported_manifest", "unsupported_source_stream",
                "unsupported_fragments", "unsupported_source_key",
                "unsupported_prep",
            }
        assert m["g0_closed"] is False
        payload = json.dumps(m, ensure_ascii=False)
        assert "Елепа" not in payload and "01_test" not in payload
        assert "source_key" not in payload
        assert "labeler" not in payload
    finally:
        yo._book_map.cache_clear()


def test_refuses_stale_runtime_yo_cache(tmp_path, monkeypatch):
    config = prepare_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(yo, "book_map", lambda: {"fake": "wrong"})
    with pytest.raises(AuditFailure, match="YO_MTIME_CACHE_STALE"):
        audit_local(config)


def test_bad_fragment_is_reported_as_unsupported_not_no_restoration(tmp_path, monkeypatch):
    config = prepare_synthetic(tmp_path, monkeypatch)
    monkeypatch.setattr(synth, "chunk_fragments",
                        lambda raw, cfg: [("Елепа.", 0, False), ("Другая.", 0, False)])
    try:
        m = audit_local(config)
        assert m["status"] == "G0_UNSUPPORTED_PRESENT"
        assert m["counts"]["selected_unsupported_fragments"] == 1
        assert m["counts"]["selected_verified"] == 0
        assert m["counts"]["eligible_verified"] == 0
        assert m["counts"]["selected_pre_restored"] == 0
        assert m["counts"]["selected_pre_0_post_0"] == 0
        assert m["g0_closed"] is False
    finally:
        yo._book_map.cache_clear()


def test_missing_manifest_entry_is_unsupported(tmp_path, monkeypatch):
    config = prepare_synthetic(tmp_path, monkeypatch)
    manifest = paths.OUT / "sections" / "01_test" / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")
    try:
        m = audit_local(config)
        assert m["counts"]["selected_unsupported_manifest"] == 1
        assert m["counts"]["selected_verified"] == 0
        assert m["counts"]["selected_pre_restored"] == 0
        assert m["status"] == "G0_UNSUPPORTED_PRESENT"
    finally:
        yo._book_map.cache_clear()


def test_mapping_content_digest_changes_with_same_mtime(tmp_path, monkeypatch):
    config = prepare_synthetic(tmp_path, monkeypatch)
    source = paths.TEXT / "synthetic.norm.txt"
    before_map, content_before, _ = content_snapshot(paths.TEXT)
    assert before_map == {}
    st = source.stat()
    source.write_text("Ёлепа. Елепа.", encoding="utf-8")
    import os
    os.utime(source, ns=(st.st_atime_ns, st.st_mtime_ns))
    after_map, content_after, _ = content_snapshot(paths.TEXT)
    assert after_map != before_map
    assert content_after != content_before
    yo._book_map.cache_clear()


def test_preparation_config_digest_changes_on_relevant_keys_only():
    a = {"text_prep": {"yo_restore": True, "open_end": "keep"}}
    b = {"text_prep": {"yo_restore": False, "open_end": "keep"}}
    assert prep_config_digest(a, "sha") != prep_config_digest(b, "sha")
    assert prep_config_digest(a, "sha1") != prep_config_digest(a, "sha2")
    assert prep_config_digest(a, "sha") == prep_config_digest(
        {**a, "model": {"variant": "1.7B"}}, "sha"
    )


def test_zero_counter_schema_matches_supported_and_unsupported_states(tmp_path, monkeypatch):
    """The schema must not depend on which buckets happened to be observed."""
    config = prepare_synthetic(tmp_path, monkeypatch)
    try:
        supported = audit_local(config)
        monkeypatch.setattr(synth, "chunk_fragments",
                            lambda raw, cfg: [("Елепа.", 0, False), ("Другая.", 0, False)])
        unsupported = audit_local(config)
        assert set(supported["counts"]) == set(unsupported["counts"])
        assert set(supported["selected_by_stratum"]) == set(unsupported["selected_by_stratum"])
        for stratum in supported["selected_by_stratum"]:
            assert set(supported["selected_by_stratum"][stratum]) == set(
                unsupported["selected_by_stratum"][stratum]
            )
        assert supported["counts"]["selected_verified"] == 1
        assert unsupported["counts"]["selected_verified"] == 0
        assert supported["counts"]["selected_unsupported_fragments"] == 0
        assert unsupported["counts"]["selected_unsupported_fragments"] == 1
    finally:
        yo._book_map.cache_clear()
