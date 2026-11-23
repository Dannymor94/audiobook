"""B3/R8-R2 filesystem security regression tests for stress_eval.

Synthetic only — no owner data, no real paths.
Covers R8 oracle matrix (T01-T08), paths.OUT itself, O_NOFOLLOW TOCTOU,
inaccessible-path normalization, and score-ERROR propagation.
"""
import os
import sys
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from audiobook import paths
from audiobook import stress_eval as ev
from audiobook.unitmap import AnnotationError
from audiobook.stress_yo_observer import UNSUPPORTED_obs, NONE_obs

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

_HAS_O_NOFOLLOW = bool(getattr(os, "O_NOFOLLOW", 0)) and os.name != "nt"

needs_nofollow = pytest.mark.skipif(
    not _HAS_O_NOFOLLOW,
    reason="O_NOFOLLOW not available on this platform",
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


def _snapshot(directory: Path) -> dict:
    """Existence, type, directory membership, symlink destinations and file bytes."""
    result = {".": directory.exists()}
    if not directory.exists():
        return result
    for item in sorted(directory.rglob("*")):
        rel = str(item.relative_to(directory))
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode):
            result[rel] = ("symlink", os.readlink(item))
        elif stat.S_ISREG(info.st_mode):
            result[rel] = ("file", info.st_mode, info.st_mtime_ns, item.read_bytes())
        else:
            result[rel] = ("directory",)
    return result


# ---------------------------------------------------------------------------
# BEFORE-FIX REPRO
# Demonstrates the pre-patch vulnerability using raw stdlib — not the
# production function (which is now patched and would reject these paths).
# ---------------------------------------------------------------------------


@needs_symlink
def test_before_fix_repro_raw_open_follows_symlink(tmp_path):
    """Pre-fix demo (raw stdlib): open('a') follows a symlink — the closed vulnerability.

    Executed against raw os.open/open, NOT the patched production function.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "ext.txt"
    external.write_text("original", encoding="utf-8")

    lock_link = tmp_path / ".test.lock"
    lock_link.symlink_to(external)

    # Raw open("a") without O_NOFOLLOW follows the symlink (pre-fix behavior).
    with open(str(lock_link), "a", encoding="utf-8") as fh:
        fh.write("")
    assert lock_link.resolve() == external  # confirmed: symlink was followed


@needs_symlink
def test_before_fix_repro_raw_read_text_follows_symlink(tmp_path):
    """Pre-fix demo (raw stdlib): read_text() follows a symlink — the closed vulnerability."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.jsonl"
    secret.write_text('{"id": "secret"}\n', encoding="utf-8")

    link = tmp_path / "manifest.jsonl"
    link.symlink_to(secret)

    # Raw read_text() follows the symlink (pre-fix behavior).
    content = link.read_text(encoding="utf-8")
    assert "secret" in content


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

    before = _snapshot(outside)

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert _snapshot(outside) == before
    assert sentinel.read_text(encoding="utf-8") == "external"


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

    before = _snapshot(outside)

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert _snapshot(outside) == before


# ---------------------------------------------------------------------------
# R8-T03: nested ancestor (stress dir) is a symlink
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
    before = _snapshot(outside)

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert _snapshot(outside) == before


# ---------------------------------------------------------------------------
# NEW: paths.OUT itself is a symlink (P1-R8-1 fix)
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_out_itself_symlink_lock(tmp_path, monkeypatch):
    """P1-R8-1: paths.OUT itself is a symlink → EVAL_LOCK_UNAVAILABLE, no external effects."""
    outside = tmp_path / "outside"
    outside.mkdir()
    out_link = tmp_path / "out"
    out_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_link)
    before = _snapshot(outside)

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert _snapshot(outside) == before


@needs_symlink
def test_r8_out_itself_symlink_observer(tmp_path, monkeypatch):
    """P1-R8-1: paths.OUT itself is a symlink → observer UNSUPPORTED, external data not read."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.jsonl"
    secret.write_text('{"id": "leaked"}\n', encoding="utf-8")
    out_link = tmp_path / "out"
    out_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_link)
    before = _snapshot(outside)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert _snapshot(outside) == before


# ---------------------------------------------------------------------------
# O_NOFOLLOW TOCTOU protection tests (P1-R8-2 fix)
# Tests that O_NOFOLLOW guards against TOCTOU race where is_symlink() passed.
# ---------------------------------------------------------------------------


@needs_symlink
@needs_nofollow
def test_r8_lock_onofollow_toctou_protection(tmp_path, monkeypatch):
    """P1-R8-2: O_NOFOLLOW on lock open rejects symlink even when is_symlink() is spoofed.

    Simulates TOCTOU: is_symlink check passes (spoofed False), but O_NOFOLLOW
    at open time catches the symlink → EVAL_LOCK_UNAVAILABLE, external unchanged.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "data.txt"
    external.write_text("external", encoding="utf-8")

    out_dir = tmp_path / "out"
    eval_dir = out_dir / "stress" / "eval"
    eval_dir.mkdir(parents=True)
    lock_link = eval_dir / ".wp4.lock"
    lock_link.symlink_to(external)

    monkeypatch.setattr(paths, "OUT", out_dir)
    # Spoof is_symlink() to simulate TOCTOU (check sees non-symlink, symlink was placed after).
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)

    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()

    assert external.read_bytes() == b"external"


@needs_symlink
@needs_nofollow
def test_r8_manifest_onofollow_toctou_protection(tmp_path, monkeypatch):
    """P1-R8-2: O_NOFOLLOW on manifest open rejects symlink even when is_symlink() is spoofed.

    Simulates TOCTOU: is_symlink check passes (spoofed False), but O_NOFOLLOW
    catches the symlink at open → UNSUPPORTED_obs, external data not read.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.jsonl"
    secret.write_text('{"secret": true}\n', encoding="utf-8")

    out_dir = tmp_path / "out"
    section_dir = out_dir / "sections" / "ch01"
    section_dir.mkdir(parents=True)
    manifest_link = section_dir / "manifest.jsonl"
    manifest_link.symlink_to(secret)

    monkeypatch.setattr(paths, "OUT", out_dir)
    # Spoof is_symlink() to simulate TOCTOU.
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert secret.read_bytes() == b'{"secret": true}\n'


# ---------------------------------------------------------------------------
# P2-R8-3: inaccessible lock parent → EVAL_LOCK_UNAVAILABLE (not raw OSError)
# ---------------------------------------------------------------------------


def test_r8_inaccessible_lock_path_normalized(tmp_path, monkeypatch):
    """P2-R8-3: PermissionError on mkdir → EVAL_LOCK_UNAVAILABLE, not propagated raw OSError."""
    out_dir = tmp_path / "out"
    eval_dir = out_dir / "stress" / "eval"
    eval_dir.mkdir(parents=True)
    locked_subdir = eval_dir / "locked"
    locked_subdir.mkdir()
    locked_subdir.chmod(0o444)  # read-only → mkdir inside will fail

    monkeypatch.setattr(paths, "OUT", out_dir)
    lock_path = locked_subdir / "nested" / ".test.lock"
    try:
        with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
            ev.acquire_eval_lock(lock_path)
    finally:
        locked_subdir.chmod(0o755)


# ---------------------------------------------------------------------------
# R8-T04: out/sections is a symlink → observer UNSUPPORTED
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t04_sections_dir_symlink(tmp_path, monkeypatch):
    """R8-T04: out/sections is a symlink → UNSUPPORTED_obs, external data not read (snapshot parity)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.jsonl"
    secret.write_text('{"id": "leaked"}\n', encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sections_link = out_dir / "sections"
    sections_link.symlink_to(outside)

    monkeypatch.setattr(paths, "OUT", out_dir)
    before = _snapshot(outside)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert _snapshot(outside) == before  # full snapshot parity: bytes + membership + existence


# ---------------------------------------------------------------------------
# R8-T05: section parent directory is a symlink → observer UNSUPPORTED
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t05_section_parent_dir_symlink(tmp_path, monkeypatch):
    """R8-T05: out/sections/ch01 is a symlink → UNSUPPORTED_obs, external snapshot unchanged."""
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
    before = _snapshot(outside)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert _snapshot(outside) == before


# ---------------------------------------------------------------------------
# R8-T06: manifest.jsonl is a symlink → observer UNSUPPORTED
# ---------------------------------------------------------------------------


@needs_symlink
def test_r8_t06_manifest_file_symlink(tmp_path, monkeypatch):
    """R8-T06: manifest.jsonl is a symlink to external file → UNSUPPORTED_obs, external snapshot parity."""
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
    before = _snapshot(outside)

    occ = _make_occ("ch01")
    sources = _make_sources()
    result = ev._yo_observe_key(occ, sources, {})

    assert isinstance(result, UNSUPPORTED_obs)
    assert _snapshot(outside) == before


# ---------------------------------------------------------------------------
# T04-T06 extended: symlink manifest → score() raises, pre-existing score unchanged
# (P2-R8-4 requirement)
# ---------------------------------------------------------------------------


@needs_symlink
@pytest.mark.parametrize("component", ["sections", "section", "manifest"])
def test_r8_symlink_manifest_propagates_to_score_error(tmp_path, monkeypatch, component):
    """T04-T06: no external reader, score ERROR and complete snapshot parity."""
    from test_stress_eval_sample import setup_book, context_for
    units = [{"type": "text", "text": "Елка."}]
    setup_book(tmp_path, monkeypatch, units)
    ev.sample({})
    score_dir = paths.OUT / "stress" / "eval" / "score"
    score_dir.mkdir(parents=True, exist_ok=True)
    (score_dir / "pre-existing.json").write_bytes(b'{"pre":"existing"}\n')
    sections = paths.OUT / "sections"
    section = sections / "01_test"
    manifest = section / "manifest.jsonl"
    victim = {"sections": sections, "section": section, "manifest": manifest}[component]
    outside = tmp_path / "outside"
    outside.mkdir()
    external_parent = outside / "01_test" if component == "sections" else outside
    external_parent.mkdir(exist_ok=True)
    external = external_parent / "manifest.jsonl"
    external.write_bytes(manifest.read_bytes())
    victim.rename(tmp_path / "original")
    victim.symlink_to(external if component == "manifest" else outside,
                      target_is_directory=component != "manifest")
    before = _snapshot(tmp_path)
    original_fdopen = os.fdopen
    external_stat = external.stat()

    def guarded_fdopen(fd, *args, **kwargs):
        info = os.fstat(fd)
        assert (info.st_dev, info.st_ino) != (external_stat.st_dev, external_stat.st_ino)
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", guarded_fdopen)
    context = context_for(units)
    assert isinstance(ev._yo_observe_key(context.rows[0], context.sources, {}), UNSUPPORTED_obs)
    with pytest.raises(AnnotationError, match="YO_OBSERVER_UNSUPPORTED"):
        ev.score({})
    assert _snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# R8-T07: normal in-root positive control — lock acquires, manifest supported observation
# (P2-R8-5: assert NONE_obs, not just non-MANIFEST_UNAVAILABLE)
# ---------------------------------------------------------------------------


def test_r8_t07_normal_in_root_positive_control(tmp_path, monkeypatch):
    """R8-T07: no symlinks — lock acquires normally; manifest produces supported NONE_obs observation."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr(paths, "OUT", out_dir)

    # Lock: normal acquire and release.
    lock_path = out_dir / "stress" / "eval" / ".test.lock"
    h = ev.acquire_eval_lock(lock_path)
    assert h is not None
    ev.release_eval_lock(h)

    # Manifest: real file (no symlinks) → supported NONE_obs (no yo-map, no ё in text).
    section_dir = out_dir / "sections" / "01_test"
    section_dir.mkdir(parents=True)
    (section_dir / "manifest.jsonl").write_text(
        '{"id": "0001", "n": 1, "text": "тест.", "pause_after_ms": 900}\n',
        encoding="utf-8",
    )

    occ = _make_occ("01_test")
    sources = ev.SourceIndex({"01_test": [{"type": "text", "text": "тест."}]})
    result = ev._yo_observe_key(occ, sources, {})
    # Must produce a SUPPORTED observation (NONE_obs: source text has no ё, no yo-map active).
    assert isinstance(result, NONE_obs), (
        f"Expected supported NONE_obs from observe_su path (no yo-map, no ё), got {result!r}"
    )


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


# R8-R2: execute the production functions while swapping actual ancestors.
# Hooks run synchronously at the OS boundary, with no scheduling/timing guesses.
@needs_symlink
@needs_nofollow
@pytest.mark.parametrize("flow,component", [
    ("lock", "out"), ("lock", "stress"), ("lock", "eval"),
    ("manifest", "out"), ("manifest", "sections"), ("manifest", "01_test"),
])
@pytest.mark.parametrize("phase", ["directory", "leaf"])
def test_r8_r2_ancestor_swap(tmp_path, monkeypatch, flow, component, phase):
    from test_stress_eval_sample import setup_book
    setup_book(tmp_path, monkeypatch, [{"type": "text", "text": "Елка."}])
    ev.sample({})
    score = paths.OUT / "stress" / "eval" / "score" / "existing.json"
    score.parent.mkdir(parents=True, exist_ok=True)
    score.write_bytes(b'{"existing":true}\n')
    protected_before = _snapshot(paths.TEXT), _snapshot(score.parent)
    branch = paths.OUT / ("stress" if flow == "lock" else "sections")
    parent = branch / ("eval" if flow == "lock" else "01_test")
    victim = paths.OUT if component == "out" else branch if component in {"stress", "sections"} else parent
    outside = tmp_path / "outside"
    outside.mkdir()
    # Mirror the relevant tree: a vulnerable full-path open really can succeed.
    if victim == paths.OUT:
        external_parent = outside / branch.name / parent.name
    elif victim == branch:
        external_parent = outside / parent.name
    else:
        external_parent = outside
    external_parent.mkdir(parents=True, exist_ok=True)
    leaf = ".wp4.lock" if flow == "lock" else "manifest.jsonl"
    if flow == "manifest":
        (external_parent / leaf).write_bytes((parent / leaf).read_bytes())
    (outside / "sentinel").write_bytes(b"external sentinel")
    outside_before = _snapshot(outside)
    all_before = _snapshot(tmp_path)
    original_open, original_fdopen = os.open, os.fdopen
    external_inodes = {(p.stat().st_dev, p.stat().st_ino) for p in outside.rglob("*") if p.is_file()}
    swapped = False
    opened = []
    lock_ready = flow == "lock"

    def guarded_fdopen(fd, *args, **kwargs):
        nonlocal lock_ready
        if args and args[0] == "a":
            lock_ready = True
        st = os.fstat(fd)
        assert (st.st_dev, st.st_ino) not in external_inodes, "outside FD handed to reader/writer"
        return original_fdopen(fd, *args, **kwargs)

    def swap_open(name, flags, *args, **kwargs):
        nonlocal swapped
        target_name = Path(name).name
        trigger = target_name == (component if phase == "directory" else leaf)
        if trigger and lock_ready and not swapped:
            victim.rename(victim.with_name(victim.name + "_original"))
            victim.symlink_to(outside, target_is_directory=True)
            swapped = True
        fd = original_open(name, flags, *args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {swap_open})
    monkeypatch.setattr(os, "open", swap_open)
    monkeypatch.setattr(os, "fdopen", guarded_fdopen)
    if flow == "lock":
        with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
            handle = ev.acquire_eval_lock()
            ev.release_eval_lock(handle)
    else:
        with pytest.raises(AnnotationError, match="YO_OBSERVER_UNSUPPORTED"):
            ev.score({})
    assert swapped, "race hook must execute against the production function"
    assert _snapshot(outside) == outside_before
    # Restore only the attacker's substitution, then compare protected state.
    victim.unlink()
    victim.with_name(victim.name + "_original").rename(victim)
    assert (_snapshot(paths.TEXT), _snapshot(score.parent)) == protected_before
    assert _snapshot(tmp_path) == all_before
    # Raw directory/failed-leaf FDs must all be closed. Successful fdopen handles
    # close themselves; fstat verifies there are no live descriptors left here.
    for fd in set(opened):
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("api", ["O_NOFOLLOW", "O_DIRECTORY", "dir_fd"])
def test_r8_r2_atomic_api_unavailable_fails_closed(tmp_path, monkeypatch, api):
    """Runs even without symlink privileges; no unsafe portability fallback."""
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    before = _snapshot(tmp_path)
    if api == "dir_fd":
        monkeypatch.setattr(os, "supports_dir_fd", set())
    else:
        monkeypatch.setattr(os, api, 0, raising=False)
    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()
    result = ev._yo_observe_key(_make_occ(), _make_sources(), {})
    assert isinstance(result, UNSUPPORTED_obs)
    assert _snapshot(tmp_path) == before


@needs_symlink
@needs_nofollow
def test_r8_r2_directory_swap_during_mkdir(tmp_path, monkeypatch):
    """Missing lock directories are created relative to pinned FDs too."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(paths, "ROOT", root)
    monkeypatch.setattr(paths, "OUT", root / "out")
    before = _snapshot(outside)
    original_mkdir = os.mkdir
    swapped = False

    def swap_mkdir(name, *args, **kwargs):
        nonlocal swapped
        if name == "stress" and kwargs.get("dir_fd") is not None and not swapped:
            paths.OUT.rename(root / "original_out")
            paths.OUT.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_mkdir(name, *args, **kwargs)

    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {swap_mkdir})
    monkeypatch.setattr(os, "mkdir", swap_mkdir)
    with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
        ev.acquire_eval_lock()
    assert swapped
    assert _snapshot(outside) == before
    assert (root / "original_out" / "stress" / "eval" / ".wp4.lock").is_file()


@needs_symlink
@needs_nofollow
def test_r8_r2_canonical_root_allows_parent_alias(tmp_path, monkeypatch):
    """Aliases above the already canonical trusted ROOT do not affect traversal."""
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    root = (alias / "project")
    root.mkdir()
    root = root.resolve()
    monkeypatch.setattr(paths, "ROOT", root)
    monkeypatch.setattr(paths, "OUT", root / "out")
    handle = ev.acquire_eval_lock()
    ev.release_eval_lock(handle)
    assert (root / "out" / "stress" / "eval" / ".wp4.lock").is_file()


@needs_nofollow
@pytest.mark.parametrize("flow,failure", [
    ("lock", "fdopen"), ("lock", "directory"), ("lock", "fifo"),
    ("manifest", "fdopen"), ("manifest", "directory"),
    ("manifest", "fifo"), ("manifest", "decode"),
])
def test_r8_r2_failed_leaf_closes_fds(tmp_path, monkeypatch, flow, failure):
    """Regular-file validation and reader/wrapper failures leave no live FDs."""
    root = tmp_path / "root"
    parent = root / "out" / ("stress" if flow == "lock" else "sections") / ("eval" if flow == "lock" else "ch01")
    parent.mkdir(parents=True)
    leaf = parent / (".wp4.lock" if flow == "lock" else "manifest.jsonl")
    if failure == "directory":
        leaf.mkdir()
    elif failure == "fifo":
        os.mkfifo(leaf)
    else:
        leaf.write_bytes(b"\xff")
    monkeypatch.setattr(paths, "ROOT", root)
    monkeypatch.setattr(paths, "OUT", root / "out")
    original_open = os.open
    opened = []

    def record_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def failed_fdopen(*args, **kwargs):
        raise OSError("injected wrapper failure")

    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {record_open})
    monkeypatch.setattr(os, "open", record_open)
    if failure == "fdopen":
        monkeypatch.setattr(os, "fdopen", failed_fdopen)
    if flow == "lock":
        with pytest.raises(AnnotationError, match="EVAL_LOCK_UNAVAILABLE"):
            ev.acquire_eval_lock()
    else:
        assert isinstance(ev._yo_observe_key(_make_occ(), _make_sources(), {}), UNSUPPORTED_obs)
    assert opened
    for fd in set(opened):
        with pytest.raises(OSError):
            os.fstat(fd)
