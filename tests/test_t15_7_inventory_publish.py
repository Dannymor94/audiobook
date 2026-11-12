"""v5 publication, whole-generation integrity/freshness and seven crash points.

All mutations are synthetic and confined to tmp_path. Real v4 baseline replay
is an explicit local S2 check, never an implicit model dependency of this suite.
"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import types
from pathlib import Path

import pytest

from audiobook import paths, ruaccent_adv as adv, stress_fp as fp, stress_inventory as inventory
# pronounce binds its default dictionary path at import. Initialize it before
# fixtures switch paths.TEXT, so later WP-1 baseline tests keep their real input.
from audiobook import pronounce as _pronounce
from audiobook.unitmap import AnnotationError


def _process(text):
    return text.replace("Альфа", "Альф+а").replace("бета", "б+ета")


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from test_stress_inventory import _make_env
    root, cfg = _make_env(tmp_path, {"01_test.norm.txt": "Альфа бета."},
                          omographs={"альфа": ["+альфа", "альф+а"]}, verified="verified: []")
    for name in ("ROOT", "TEXT", "MODELS", "OUT"):
        monkeypatch.setattr(paths, name, root if name == "ROOT" else root / name.lower())
    (paths.TEXT / "stress_inventory_exclude.yaml").write_text("exclude: []\n", encoding="utf-8")
    (root / "config.yaml").write_text("synthetic config", encoding="utf-8")
    identity = {"version": {"ruaccent": "synthetic"}, "init_params": {}, "files": []}
    monkeypatch.setattr(adv, "ruaccent_content_identity", lambda: identity)
    monkeypatch.setattr(adv, "load_pinned_runtime", lambda: (_process, identity))
    monkeypatch.setattr(inventory, "_try_accentizer", lambda: _process)
    monkeypatch.setattr(fp, "private_output_guard", lambda _: None)
    monkeypatch.setattr(fp, "historical_input_identity", lambda: "synthetic inputs")

    # Literal v4 oracle: independent of the new writer and of Git history.
    # The legacy writer uses native newlines; occurrences always uses LF.
    risk = ("форма\tчастота\tпричина\tпример\n"
            "альфа\t1\ttop+homograph\tАльфа бета.\n"
            "бета\t1\ttop\tАльфа бета.\n")
    omographs = ("форма\tсекция\tчанк\tконтекст\tварианты\truaccent\truaccent_status\n"
                 "альфа\t01_test\t0001\tАльфа бета.\t+альфа / альф+а\tАльф+а\tresolved\n")
    files = {"risk.tsv": risk.replace("\n", os.linesep).encode("utf-8"),
             "omographs.tsv": omographs.replace("\n", os.linesep).encode("utf-8")}
    baseline = root / "out" / "t15_7" / "baseline" / "tsv"
    baseline.mkdir(parents=True)
    reference = root / "v4_reference" / "inventory"
    reference.mkdir(parents=True)
    for name, data in files.items():
        (baseline / name).write_bytes(data)
        (reference / name).write_bytes(data)
    (baseline / "metadata.json").write_text(json.dumps({"input_identity": "synthetic inputs",
                                                        "D_tsv": fp.historical_tsv_digest(files)}), encoding="utf-8")
    inventory.run(cfg)
    return cfg, paths.OUT / "stress", identity


def _summary(stress_dir):
    return json.loads((stress_dir / "inventory" / "summary.json").read_text(encoding="utf-8"))


def _resign(stress_dir, summary):
    pointer = json.loads((stress_dir / "inventory" / "current.json").read_text(encoding="utf-8"))
    archive = stress_dir / "gen" / pointer["gen_id"]
    data = json.dumps(summary, ensure_ascii=False).encode("utf-8")
    pointer["summary_sha256"] = hashlib.sha256(data).hexdigest()
    for base in (stress_dir / "inventory", archive):
        (base / "summary.json").write_bytes(data)
        (base / "current.json").write_text(json.dumps(pointer), encoding="utf-8")


def _replace_file(stress_dir, name, data):
    summary = _summary(stress_dir)
    archive = stress_dir / "gen" / summary["gen_id"]
    for base in (stress_dir / "inventory", archive):
        (base / name).write_bytes(data)
    summary["files"][name].update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), rows=len(data.splitlines()) - 1)
    _resign(stress_dir, summary)


def test_real_adapter_and_publisher_synthetic_end_to_end(environment):
    cfg, directory, _ = environment
    result = fp.read_occurrences(cfg)
    assert [(o.form_analysis, o.f6_status, o.f6_vowel) for o in result] == [
        ("Альфа", "resolved", 1), ("бета", "resolved", 0)]
    summary = _summary(directory)
    assert summary["counts"] == {"occurrences": 2, "aligned": 2, "unresolved_by_reason": {}}
    assert summary["algo_version"] == 5
    assert fp.load_current(directory) == summary  # Existing consumer API tolerates additive keys.
    assert set(summary["files"]) == {"risk.tsv", "omographs.tsv", "occurrences.tsv"}
    for name in fp.HISTORICAL_TSV_NAMES:
        assert (directory / "inventory" / name).read_bytes() == (paths.ROOT / "v4_reference" / "inventory" / name).read_bytes()


@pytest.mark.parametrize("name", ["risk.tsv", "omographs.tsv", "occurrences.tsv"])
@pytest.mark.parametrize("location", ["inventory", "archive"])
def test_every_file_and_archive_tamper_refused(environment, name, location):
    cfg, directory, _ = environment
    base = directory / "inventory" if location == "inventory" else directory / "gen" / _summary(directory)["gen_id"]
    file = base / name
    file.write_bytes(file.read_bytes() + b"tamper")
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


@pytest.mark.parametrize("name", ["risk.tsv", "omographs.tsv", "occurrences.tsv"])
@pytest.mark.parametrize("field,value", [("sha256", "bad"), ("bytes", -1), ("rows", 999), ("schema", "wrong/1")])
def test_every_file_metadata_contract(environment, name, field, value):
    cfg, directory, _ = environment
    summary = _summary(directory)
    summary["files"][name][field] = value
    _resign(directory, summary)
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


@pytest.mark.parametrize("name", ["risk.tsv", "omographs.tsv", "occurrences.tsv"])
def test_rehashed_wrong_header_is_still_refused(environment, name):
    cfg, directory, _ = environment
    content = (directory / "inventory" / name).read_bytes().split(b"\n", 1)[1]
    _replace_file(directory, name, b"wrong header\n" + content)
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


@pytest.mark.parametrize("name,column,value", [("risk.tsv", 1, "+1"), ("omographs.tsv", 6, "bad"),
                                               ("occurrences.tsv", 22, "2"), ("occurrences.tsv", 20, "ALIGNED")])
def test_rehashed_malformed_rows_refused(environment, name, column, value):
    cfg, directory, _ = environment
    lines = (directory / "inventory" / name).read_text(encoding="utf-8").splitlines()
    cells = lines[1].split("\t")
    cells[column] = value
    lines[1] = "\t".join(cells)
    _replace_file(directory, name, ("\n".join(lines) + "\n").encode("utf-8"))
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


@pytest.mark.parametrize("mutation", ["extra_file", "missing_file", "old_algo", "bad_counts", "missing_summary", "missing_archive", "missing_pointer"])
def test_incomplete_or_unsupported_generation(environment, mutation):
    cfg, directory, _ = environment
    summary = _summary(directory)
    if mutation == "extra_file":
        summary["files"]["unknown.tsv"] = {}
    elif mutation == "missing_file":
        (directory / "inventory" / "omographs.tsv").unlink()
    elif mutation == "old_algo":
        summary["algo_version"] = 4
    elif mutation == "bad_counts":
        summary["counts"]["aligned"] = 1
    elif mutation == "missing_summary":
        (directory / "inventory" / "summary.json").unlink()
    elif mutation == "missing_archive":
        shutil.rmtree(directory / "gen" / summary["gen_id"])
    else:
        (directory / "inventory" / "current.json").unlink()
    if mutation in ("extra_file", "old_algo", "bad_counts"):
        _resign(directory, summary)
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


@pytest.mark.parametrize("field,value", [("n", 2), ("id", "0002"), ("text", "Гамма бета."),
                                        ("pause_after_ms", 100), ("open_end", True), ("leadin", "Ввод")])
def test_each_analytic_manifest_edit_is_stale(environment, field, value):
    cfg, _, _ = environment
    manifest = paths.OUT / "sections" / "01_test" / "manifest.jsonl"
    row = json.loads(manifest.read_text(encoding="utf-8"))
    row[field] = value
    manifest.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="INVENTORY_STALE"):
        fp.read_occurrences(cfg)


@pytest.mark.parametrize("mutation", ["source", "kind", "config", "pronounce", "verified", "watch", "exclude", "runtime", "yo"])
def test_each_fingerprint_input_class_is_stale(environment, mutation, monkeypatch):
    cfg, _, identity = environment
    if mutation == "source":
        (paths.TEXT / "01_test.norm.txt").write_text("Гамма бета.", encoding="utf-8")
    elif mutation == "kind":
        file = paths.TEXT / "blocks" / "01_test.blocks.json"
        blocks = json.loads(file.read_text(encoding="utf-8"))
        blocks["blocks"][0]["type"] = "heading"
        file.write_text(json.dumps(blocks), encoding="utf-8")
    elif mutation == "config":
        cfg["text_prep"] = {"strip_quotes": True}
    elif mutation == "runtime":
        identity["files"].append(["synthetic runtime", "changed"])
    elif mutation == "yo":
        from audiobook import yo
        monkeypatch.setattr(yo, "build_map", lambda _: {"synthetic": "change"})
    else:
        name = {"pronounce": "pronounce.yaml", "verified": "stress_verified.yaml",
                "watch": "stress_watch.yaml", "exclude": "stress_inventory_exclude.yaml"}[mutation]
        file = paths.TEXT / name
        file.write_text(file.read_text(encoding="utf-8") + "\n# synthetic change\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="INVENTORY_STALE"):
        fp.read_occurrences(cfg)


def test_irrelevant_audio_status_and_seed_stay_current(environment):
    cfg, _, _ = environment
    manifest = paths.OUT / "sections" / "01_test" / "manifest.jsonl"
    row = json.loads(manifest.read_text(encoding="utf-8"))
    row.update(status="pending", duration_ms=42, seed_override=123, qc="changed")
    manifest.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    cfg["model"] = {"seed": 123}
    assert len(fp.read_occurrences(cfg)) == 2


def test_historical_byte_guard_precedes_advisory(environment, monkeypatch):
    cfg, directory, _ = environment
    before = (directory / "inventory" / "current.json").read_bytes()
    file = paths.ROOT / "out" / "t15_7" / "baseline" / "tsv" / "risk.tsv"
    file.write_bytes(file.read_bytes() + b"synthetic tamper")
    monkeypatch.setattr(inventory, "_occurrence_payload", lambda _: pytest.fail("Advisory gate bypassed"))
    with pytest.raises(AnnotationError, match="HISTORICAL_TSV_MISMATCH"):
        inventory.run(cfg)
    assert (directory / "inventory" / "current.json").read_bytes() == before


def test_missing_readonly_loader_input_never_created(environment):
    cfg, directory, _ = environment
    before = (directory / "inventory" / "current.json").read_bytes()
    file = paths.TEXT / "stress_verified.yaml"
    file.unlink()
    with pytest.raises(AnnotationError, match="READ_ONLY_INPUT_MISSING"):
        inventory.run(cfg)
    assert not file.exists()
    assert (directory / "inventory" / "current.json").read_bytes() == before


@pytest.mark.parametrize("ignored,tracked,ls_rc", [(False, False, 0), (True, True, 0), (True, False, 1)])
def test_p1_rejects_unsafe_output_without_writes(tmp_path, monkeypatch, ignored, tracked, ls_rc):
    def run(command, **kwargs):
        if command[1] == "check-ignore":
            return types.SimpleNamespace(returncode=0 if ignored else 1, stdout=b"")
        return types.SimpleNamespace(returncode=ls_rc, stdout=b"synthetic tracked" if tracked else b"")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(AnnotationError, match="PRIVATE_OUTPUT_REQUIRED"):
        fp.private_output_guard(tmp_path / "unwritten")
    assert not (tmp_path / "unwritten").exists()


def test_pointer_traversal_refused_before_archive_read(environment, monkeypatch):
    cfg, directory, _ = environment
    (directory / "inventory" / "current.json").write_text(json.dumps({"gen_id": "../escape"}), encoding="utf-8")
    monkeypatch.setattr(fp, "load_current", lambda _: pytest.fail("Unsafe pointer reached archive reader"))
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


def test_advisory_failure_never_replaces_current(environment, monkeypatch):
    cfg, directory, _ = environment
    before = (directory / "inventory" / "current.json").read_bytes()
    def failure(_):
        raise AnnotationError("RUACCENT_RUNTIME_ERROR")
    monkeypatch.setattr(inventory, "_occurrence_payload", failure)
    with pytest.raises(AnnotationError, match="RUACCENT_RUNTIME_ERROR"):
        inventory.run(cfg)
    assert (directory / "inventory" / "current.json").read_bytes() == before
    assert len(fp.read_occurrences(cfg)) == 2


def test_generation_collision_cannot_overwrite_history(environment):
    cfg, directory, _ = environment
    gen_id = _summary(directory)["gen_id"]
    tmp = inventory._prepare_tmp_dir(directory)
    shutil.copyfile(directory / "inventory" / "summary.json", tmp / "summary.json")
    archive = directory / "gen" / gen_id
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in archive.iterdir()}
    with pytest.raises(AnnotationError, match="GENERATION_EXISTS"):
        inventory._atomic_publish_inventory(tmp, directory, gen_id)
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in archive.iterdir()} == before
    assert not (tmp / "current.json").exists()
    assert len(fp.read_occurrences(cfg)) == 2


def test_successive_publications_keep_prior_archive(environment):
    cfg, directory, _ = environment
    gen_id = _summary(directory)["gen_id"]
    archive = directory / "gen" / gen_id
    before = {p.name: p.read_bytes() for p in archive.iterdir()}
    inventory.run(cfg)
    assert _summary(directory)["gen_id"] != gen_id
    assert {p.name: p.read_bytes() for p in archive.iterdir()} == before
    assert len(fp.read_occurrences(cfg)) == 2


@pytest.mark.parametrize("name", ["risk.tsv", "omographs.tsv"])
def test_v4_native_crlf_bytes_remain_supported(environment, name):
    cfg, directory, _ = environment
    data = (directory / "inventory" / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    _replace_file(directory, name, data)
    assert len(fp.read_occurrences(cfg)) == 2


def test_occurrences_crlf_is_never_accepted(environment):
    cfg, directory, _ = environment
    data = (directory / "inventory" / "occurrences.tsv").read_bytes().replace(b"\n", b"\r\n")
    _replace_file(directory, "occurrences.tsv", data)
    with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
        fp.read_occurrences(cfg)


def test_occurrences_writer_requests_literal_lf(environment, monkeypatch):
    cfg, _, _ = environment
    original = inventory.os.fdopen
    settings = []
    def observe(fd, *args, **kwargs):
        settings.append(kwargs.get("newline"))
        return original(fd, *args, **kwargs)
    monkeypatch.setattr(inventory.os, "fdopen", observe)
    inventory.run(cfg)
    assert settings == [None, None, ""]  # Preserve both legacy writers, force LF only for occurrences.


class SimulatedCrash(Exception):
    pass


@pytest.mark.parametrize("step", range(1, 8))
def test_seven_existing_publisher_crash_points(environment, monkeypatch, step):
    cfg, directory, _ = environment
    old_id = _summary(directory)["gen_id"]
    summary = copy.deepcopy(_summary(directory))
    summary["gen_id"] = "synthetic_next"
    tmp = directory / "inventory.tmp"
    original_write, original_rename = Path.write_text, Path.rename
    original_copy, original_delete = shutil.copytree, shutil.rmtree

    def write(path, *args, **kwargs):
        result = original_write(path, *args, **kwargs)
        if step == 3 and path == tmp / "current.json":
            raise SimulatedCrash()
        return result
    def rename(path, target):
        result = original_rename(path, target)
        if (step == 5 and path == directory / "inventory") or (step == 6 and path == tmp):
            raise SimulatedCrash()
        return result
    def copytree(source, target, *args, **kwargs):
        result = original_copy(source, target, *args, **kwargs)
        if step == 4 and Path(source) == tmp:
            raise SimulatedCrash()
        return result
    def delete(path, *args, **kwargs):
        result = original_delete(path, *args, **kwargs)
        if step == 7 and Path(path) == directory / "inventory.old":
            raise SimulatedCrash()
        return result

    with monkeypatch.context() as injected:
        injected.setattr(Path, "write_text", write)
        injected.setattr(Path, "rename", rename)
        injected.setattr(shutil, "copytree", copytree)
        injected.setattr(shutil, "rmtree", delete)
        with pytest.raises(SimulatedCrash):
            inventory._prepare_tmp_dir(directory)
            if step == 1:
                raise SimulatedCrash()
            for name in summary["files"]:
                shutil.copyfile(directory / "inventory" / name, tmp / name)
            (tmp / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            if step == 2:
                raise SimulatedCrash()
            inventory._atomic_publish_inventory(tmp, directory, summary["gen_id"])
    before = {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    if step == 5:
        with pytest.raises(AnnotationError, match="INVENTORY_INVALID"):
            fp.read_occurrences(cfg)
        assert not (directory / "inventory").exists()  # Reader must never repair the rename gap.
    else:
        assert len(fp.read_occurrences(cfg)) == 2
        assert _summary(directory)["gen_id"] == (old_id if step < 5 else "synthetic_next")
    assert {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()} == before
    # Existing recovery must precede even a failing loader on the next run.
    def loader_failure():
        raise SystemExit("synthetic loader failure")
    monkeypatch.setattr(inventory, "_omograph_dict", loader_failure)
    with pytest.raises(SystemExit):
        inventory.run(cfg)
    assert len(fp.read_occurrences(cfg)) == 2
