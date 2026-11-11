"""Read-only corpus audit integration tests, using synthetic data only."""
import json

import pytest

from audiobook import paths, stress_map_audit as audit


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    text, out = tmp_path / "text", tmp_path / "out"
    (text / "blocks").mkdir(parents=True)
    out.mkdir()
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)

    def write(section="01_test", lines=("а а", "123 ABC"), chunks=("а", "а", "123 ABC")):
        (text / f"{section}.norm.txt").write_text("\n".join(lines), encoding="utf-8")
        (text / "blocks" / f"{section}.blocks.json").write_text(
            json.dumps({"blocks": [{"type": "paragraph"} for _ in lines]}), encoding="utf-8",
        )
        if chunks is not None:
            directory = out / "sections" / section
            directory.mkdir(parents=True, exist_ok=True)
            rows = [{"n": i, "id": f"{i:04d}", "text": value, "pause_after_ms": 400}
                    for i, value in enumerate(chunks, 1)]
            (directory / "manifest.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows), encoding="utf-8",
            )
    return tmp_path, write


def test_audit_verifies_provenance_and_preserves_all_files(corpus):
    root, write = corpus
    write()
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    summary = audit.audit_corpus()
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert summary["status"] == "PASS" and summary["checksums"]["unchanged"]
    assert summary["totals"] == {
        "units": 2, "chunks": 3, "source_atoms": 4, "consumed_atoms": 4,
        "multi_unit_chunks": 0, "zero_cyrillic_chunks": 1, "repeated_atoms": 1,
    }
    assert summary["sections"][0]["stored_atom_identity_verified"]
    assert summary["checksums"]["before"] == summary["checksums"]["after"]
    assert len(summary["checksums"]["before"]["chunk_sources"]["01_test"]) == 64


def test_audit_maps_multiple_units_including_zero_cyrillic(corpus):
    _, write = corpus
    write(lines=("123", "ABC"), chunks=("123 ABC",))
    summary = audit.audit_corpus()
    assert summary["status"] == "PASS"
    assert summary["totals"]["multi_unit_chunks"] == summary["totals"]["zero_cyrillic_chunks"] == 1


def test_audit_reports_safe_structured_error(corpus):
    _, write = corpus
    secret = "SYNTHETIC_SECRET"
    write(chunks=(secret,))
    summary = audit.audit_corpus()
    assert summary["status"] == "BLOCKED"
    assert summary["failures"] == [{"section": "01_test", "chunk_id": "0001", "code": "ATOM_MISMATCH"}]
    assert secret not in json.dumps(summary)
    assert summary["checksums"]["unchanged"]


@pytest.mark.parametrize("case,code", [
    ("stale", "STALE_EXCLUSION"), ("wrong_count", "EXCLUSION_TOKEN_MISMATCH"),
    ("missing", "MANIFEST_READ_ERROR"),
])
def test_audit_preserves_exclusion_guards(corpus, case, code):
    _, write = corpus
    write(chunks=("а а 123 ABC",) if case == "stale" else None)
    if case != "missing":
        (paths.TEXT / "stress_inventory_exclude.yaml").write_text(
            "sections:\n  - section: 01_test\n    tokens: 0\n", encoding="utf-8",
        )
    summary = audit.audit_corpus()
    assert summary["status"] == "BLOCKED" and summary["failures"][0]["code"] == code


def test_audit_excludes_only_approved_sections(corpus):
    _, write = corpus
    write()
    write("02_skip", lines=("а",), chunks=None)
    (paths.TEXT / "stress_inventory_exclude.yaml").write_text(
        "sections:\n  - section: 02_skip\n    tokens: 1\n", encoding="utf-8",
    )
    summary = audit.audit_corpus()
    assert summary["status"] == "PASS"
    assert summary["sections_mapped"] == summary["sections_excluded"] == 1
    assert summary["excluded"] == [{"section": "02_skip", "tokens": 1}]


def test_audit_independently_detects_corrupt_returned_map(corpus, monkeypatch):
    _, write = corpus
    write()
    original = audit._load_mapped_section

    def corrupt(section):
        units, rows, sm = original(section)
        object.__setattr__(sm.spans[-1], "atom_end", len(sm.stream) - 1)
        object.__setattr__(sm.spans[-1], "spans", sm.spans[-1].spans[:1])
        return units, rows, sm

    monkeypatch.setattr(audit, "_load_mapped_section", corrupt)
    summary = audit.audit_corpus()
    assert summary["status"] == "BLOCKED" and summary["failures"][0]["code"] == "AUDIT_PROVENANCE"


def test_audit_detects_input_checksum_drift(corpus, monkeypatch):
    _, write = corpus
    write()
    original = audit._checksums
    calls = 0

    def drift():
        nonlocal calls
        result = original()
        calls += 1
        if calls == 2:
            result["norm"]["01_test.norm.txt"] = "changed"
        return result

    monkeypatch.setattr(audit, "_checksums", drift)
    summary = audit.audit_corpus()
    assert summary["status"] == "BLOCKED" and not summary["checksums"]["unchanged"]


def test_audit_empty_corpus_is_blocked(corpus):
    assert audit.audit_corpus()["status"] == "BLOCKED"


def test_audit_cli_input_failure_is_machine_readable_and_private(monkeypatch, capsys):
    secret = "SYNTHETIC_SECRET_INPUT"

    def fail(*args):
        raise ValueError(secret)

    monkeypatch.setattr(audit, "audit_corpus", fail)
    monkeypatch.setattr("sys.argv", ["stress_map_audit"])
    assert audit.main() == 1
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "BLOCKED",
        "failures": [{"section": None, "chunk_id": None, "code": "AUDIT_INPUT_ERROR"}],
    }
