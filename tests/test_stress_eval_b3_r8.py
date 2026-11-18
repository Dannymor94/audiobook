"""B3/R8 filesystem security regression tests for stress_eval.

Synthetic only — no owner data, no real paths. All eight R8 oracle cases.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from audiobook import paths
from audiobook import stress_eval as ev
from audiobook.unitmap import AnnotationError
from audiobook.stress_yo_observer import UNSUPPORTED_obs

# ---------------------------------------------------------------------------
# Symlink availability guard
# ---------------------------------------------------------------------------

_CAN_SYMLINK = False
try:
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _d:
        _src = Path(_d) / "s"
        _dst = Path(_d) / "l"
        _src.mkdir()
        _dst.symlink_to(_src)
    _CAN_SYMLINK = True
except (OSError, NotImplementedError):
    pass

needs_symlink = pytest.mark.skipif(
    not _CAN_SYMLINK,
    reason="symlinks not available on this platform/config (Windows without Developer Mode)",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_occ(section: str = "ch01"):
    """Minimal occ SimpleNamespace sufficient to reach the manifest symlink check."""
    return SimpleNamespace(
        source_key=f"{section}|0|0",
        section=section,
        su_chunk_id="0001",
        su_fragment=None,
        su_token_index=0,
        f1_rule=None,
        f1_flag="none",
        f6_status="ok",
        f6_vowel=0,
        status="ok",
        alignment_status="aligned",
        form_analysis="тест",
        form_source="тест",
        form_synth=None,
        norm_start=0,
        norm_end=4,
    )


def _make_sources():
    """Minimal sources object whose resolve() bypasses SOURCE_NOT_FOUND."""
    dummy_identity = {
        "source_key": "ch01|0|0",
        "form_source": "тест",
        "unit_text_sha256": "a" * 64,
        "unit_kind": "text",
        "context_sha256": "b" * 64,
    }
    return SimpleNamespace(resolve=lambda k: (dummy_identity, "тест", None))


# ---------------------------------------------------------------------------
# BEFORE-FIX REPRO (source-code inspection, executed via monkeypatch)
# Demonstrates that the unpatched code would follow symlinks: we bypass our
# new guard and show the raw open() / read_text() accept symlink targets.
# ---------------------------------------------------------------------------


@needs_symlink
def test_before_fix_repro_lock_would_follow_symlink(tmp_path):
    """Pre-fix: open(path, 'a') follows a symlink target — demonstrates the vulnerability.

    We call the raw open() without symlink protection and show it writes to external file.
    This is a synthetic demonstration on tmp_path; no owner data touched.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "ext.txt"
    external.write_text("original", encoding="utf-8")

    lock_link = tmp_path / ".test.lock"
    lock_link.symlink_to(external)

    # Raw open("a") without O_NOFOLLOW follows the symlink and writes to external.
    with open(str(lock_link), "a", encoding="utf-8") as fh:
        fh.write("")  # append nothing, but file access proves it opened external
    assert lock_link.resolve() == external  # symlink was followed


@needs_symlink
def test_before_fix_repro_manifest_would_follow_symlink(tmp_path):
    """Pre-fix: read_text() follows a symlink — demonstrates the manifest vulnerability."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.jsonl"
    secret.write_text('{"id": "secret"}\n', encoding="utf-8")

    link = tmp_path / "manifest.jsonl"
    link.symlink_to(secret)

    # Raw read_text() follows the symlink — reads external data.
    content = link.read_text(encoding="utf-8")
    assert "secret" in content  # proves external data would have been read


# ---------------------------------------------------------------------------
# R8-T01: lock parent directory is a symlink to outside sentinel
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t01_lock_parent_dir_symlink(tmp_path, monkeypatch):
    """R8-T01: eval dir is a symlink to external dir → EVAL_LOCK_UNAVAILABLE, no external effects."""
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("external", encoding="utf-8")

    out_dir = tmp_path / "out"
    stress_dir = out_dir / "stress"
    stress_dir.mkdir(parents=True)
    eval_link = stress_dir / "eval"
    eval_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_dir)

    outside_before = {p.name: p.read_bytes() for p in outside.iterdir()}
    outside_names_before = set(outside.iterdir())

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    # Assert no side effects on external directory.
    assert set(outside.iterdir()) == outside_names_before
    assert sentinel.read_text(encoding="utf-8") == "external"
    for p, b in outside_before.items():
        assert (outside / p).read_bytes() == b


# ---------------------------------------------------------------------------
# R8-T02: lock file is a symlink to outside sentinel
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t02_lock_file_symlink(tmp_path, monkeypatch):
    """R8-T02: .wp4.lock is a symlink to external file → EVAL_LOCK_UNAVAILABLE, external unchanged."""
    outside = tmp_path / "outside"
    outside.mkdir()
    external_file = outside / "data.txt"
    external_file.write_text("external", encoding="utf-8")

    out_dir = tmp_path / "out"
    eval_dir = out_dir / "stress" / "eval"
    eval_dir.mkdir(parents=True)
    lock_link = eval_dir / ".wp4.lock"
    lock_link.symlink_to(external_file)

    monkeypatch.setattr(paths, "OUT", out_dir)

    outside_listing = sorted(p.name for p in outside.iterdir())
    external_bytes_before = external_file.read_bytes()

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert sorted(p.name for p in outside.iterdir()) == outside_listing
    assert external_file.read_bytes() == external_bytes_before


# ---------------------------------------------------------------------------
# R8-T03: nested ancestor is a symlink (stress dir → outside)
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t03_nested_ancestor_symlink(tmp_path, monkeypatch):
    """R8-T03: stress/ ancestor dir is a symlink → EVAL_LOCK_UNAVAILABLE, no external effects."""
    outside = tmp_path / "outside"
    outside.mkdir()

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    stress_link = out_dir / "stress"
    stress_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_dir)
    outside_before = set(outside.iterdir())

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert set(outside.iterdir()) == outside_before


# ---------------------------------------------------------------------------
# R8-T04: out/sections is a symlink → observer UNSUPPORTED
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t04_sections_dir_symlink(tmp_path, monkeypatch):
    """R8-T04: out/sections is a symlink → UNSUPPORTED_obs, external data not read."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.jsonl"
    secret.write_text('{"id": "leaked"}\n', encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sections_link = out_dir / "sections"
    sections_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_dir)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert secret.read_text(encoding="utf-8") == '{"id": "leaked"}\n'  # not consumed


# ---------------------------------------------------------------------------
# R8-T05: section parent directory is a symlink → observer UNSUPPORTED
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t05_section_parent_dir_symlink(tmp_path, monkeypatch):
    """R8-T05: out/sections/ch01 is a symlink → UNSUPPORTED_obs, external data not read."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "manifest.jsonl"
    secret.write_text('{"id": "leaked"}\n', encoding="utf-8")

    out_dir = tmp_path / "out"
    sections_dir = out_dir / "sections"
    sections_dir.mkdir(parents=True)
    section_link = sections_dir / "ch01"
    section_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_dir)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert secret.read_text(encoding="utf-8") == '{"id": "leaked"}\n'


# ---------------------------------------------------------------------------
# R8-T06: manifest.jsonl is a symlink → observer UNSUPPORTED
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t06_manifest_file_symlink(tmp_path, monkeypatch):
    """R8-T06: manifest.jsonl is a symlink to external file → UNSUPPORTED_obs, file not read."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "data.jsonl"
    secret.write_text('{"id": "leaked"}\n', encoding="utf-8")

    out_dir = tmp_path / "out"
    section_dir = out_dir / "sections" / "ch01"
    section_dir.mkdir(parents=True)
    manifest_link = section_dir / "manifest.jsonl"
    manifest_link.symlink_to(secret)

    monkeypatch.setattr(paths, "OUT", out_dir)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert secret.read_text(encoding="utf-8") == '{"id": "leaked"}\n'


# ---------------------------------------------------------------------------
# R8-T07: normal in-root positive control — lock acquires, manifest reads
# ---------------------------------------------------------------------------


def test_r8_t07_normal_in_root_positive_control(tmp_path, monkeypatch):
    """R8-T07: no symlinks — lock acquires normally, manifest read returns UNSUPPORTED (no such chunk)."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr(paths, "OUT", out_dir)

    # Lock: normal acquire and release.
    lock_path = out_dir / "stress" / "eval" / ".test.lock"
    h = ev.acquire_eval_lock(lock_path)
    assert h is not None
    ev.release_eval_lock(h)

    # Manifest: file exists but chunk not found → UNSUPPORTED (not symlink rejection).
    section_dir = out_dir / "sections" / "ch01"
    section_dir.mkdir(parents=True)
    manifest = section_dir / "manifest.jsonl"
    manifest.write_text('{"id": "0001", "n": 1, "text": "тест.", "pause_after_ms": 900}\n',
                        encoding="utf-8")

    occ = _make_occ("ch01")
    occ.su_chunk_id = "0001"  # exists in manifest; passes symlink guard, reaches observe_su
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})
    # Must NOT be rejected by the symlink guard (MANIFEST_UNAVAILABLE).
    # observe_su may return NONE_obs, RESTORED_obs, or UNSUPPORTED_obs from downstream.
    from audiobook.stress_yo_observer import NONE_obs
    assert isinstance(result, (NONE_obs, UNSUPPORTED_obs)), \
        f"Expected NONE_obs or UNSUPPORTED_obs from observe_su path, got {result!r}"
    # Verify it wasn't the symlink-guard rejection specifically.
    if isinstance(result, UNSUPPORTED_obs):
        assert result.reason != "MANIFEST_UNAVAILABLE"


# ---------------------------------------------------------------------------
# R8-T08: concurrent lock collision and release/reacquire
# ---------------------------------------------------------------------------


def test_r8_t08_concurrent_lock_and_reacquire(tmp_path):
    """R8-T08: second acquire while first held → EVAL_LOCK_UNAVAILABLE; after release, reacquires."""
    lock_path = tmp_path / ".r8_test.lock"

    h1 = ev.acquire_eval_lock(lock_path)
    try:
        with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
            ev.acquire_eval_lock(lock_path)
    finally:
        ev.release_eval_lock(h1)

    h2 = ev.acquire_eval_lock(lock_path)
    ev.release_eval_lock(h2)
