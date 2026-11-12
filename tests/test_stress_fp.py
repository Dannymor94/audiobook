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


def _historical_files():
    return {"risk.tsv": b"synthetic risk\n", "omographs.tsv": b"synthetic occurrences\n"}


def test_historical_digest_literal_domain():
    import hashlib
    from audiobook.stress_fp import historical_tsv_digest
    data = (b"historical-tsv/1\0risk.tsv\0" + (15).to_bytes(8, "big") + b"synthetic risk\n"
            + b"omographs.tsv\0" + (22).to_bytes(8, "big") + b"synthetic occurrences\n")
    assert historical_tsv_digest(_historical_files()) == hashlib.sha256(data).hexdigest()
    assert historical_tsv_digest(dict(reversed(list(_historical_files().items())))) == historical_tsv_digest(_historical_files())


@pytest.mark.parametrize("mutation", ["risk.tsv", "omographs.tsv", "identity", "digest", "missing"])
def test_historical_baseline_read_only_refusal(tmp_path, mutation):
    from audiobook.stress_fp import historical_tsv_digest, check_historical_tsv
    from audiobook.unitmap import AnnotationError
    files = _historical_files()
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    metadata = {"input_identity": "synthetic", "D_tsv": historical_tsv_digest(files)}
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    assert check_historical_tsv(tmp_path, files, "synthetic") == metadata["D_tsv"]
    if mutation in files:
        files[mutation] += b"changed"
    elif mutation == "identity":
        metadata["input_identity"] = "changed"
    elif mutation == "digest":
        metadata["D_tsv"] = "changed"
    else:
        (tmp_path / "risk.tsv").unlink()
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(AnnotationError):
        check_historical_tsv(tmp_path, files, "synthetic")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


def _analysis(config=None, **changes):
    from audiobook.stress_fp import analysis_fp
    args = dict(source="synthetic source", manifest="synthetic manifest", ruaccent={"files": []},
                config=config or {}, yo_dict_sha256="yo", pronounce_sha256="pronounce",
                verified_sha256="verified", watch_sha256="watch", exclude_sha256="exclude")
    args.update(changes)
    return analysis_fp(**args)


@pytest.mark.parametrize("field", ["source", "manifest", "ruaccent", "yo_dict_sha256",
                                    "pronounce_sha256", "verified_sha256", "watch_sha256", "exclude_sha256"])
def test_analysis_every_input_class(field):
    assert _analysis(**{field: {"files": [["synthetic", "changed"]]} if field == "ruaccent" else "changed"}) != _analysis()


@pytest.mark.parametrize("path", ["text_prep.yo_restore", "text_prep.strip_quotes", "text_prep.open_end",
                                   "text_prep.ensure_terminal", "render.leadin.phrase", "render.leadin.max_chars",
                                   "pauses_ms.enum_pause_ms", "pauses_ms.sentence", "stress.top_n", "pauses_ms.paragraph"])
def test_analysis_each_observed_config_leaf(path):
    cfg = {}
    node = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = "synthetic change"
    assert _analysis(cfg) != _analysis()


def test_analysis_ignores_unread_audio_config():
    assert _analysis({"model": {"seed": 123}, "audio": {"rate": 24000}}) == _analysis()


@pytest.mark.parametrize("field,value", [("n", 2), ("id", "0002"), ("text", "Бета"),
                                        ("pause_after_ms", 100), ("open_end", True), ("leadin", "Ввод")])
def test_manifest_mutation_propagates_to_analysis(field, value):
    from audiobook.wordprov import manifest_fp
    row = {"n": 1, "id": "0001", "text": "Альфа", "pause_after_ms": 0, "open_end": False, "leadin": None}
    assert _analysis(manifest=manifest_fp({"01_test": [row]})) != _analysis(manifest=manifest_fp({"01_test": [{**row, field: value}]}))


def test_manifest_status_does_not_change_analysis():
    from audiobook.wordprov import manifest_fp
    row = {"n": 1, "id": "0001", "text": "Альфа"}
    assert _analysis(manifest=manifest_fp({"01_test": [row]})) == _analysis(manifest=manifest_fp({"01_test": [{**row, "status": "changed", "duration_ms": 99, "seed_override": 42}]}))


def test_analysis_literal_adr_payload():
    import hashlib
    expected = {"algo": "analysis/1", "inventory_algo_version": 5,
                "source_fp": "synthetic source", "manifest_fp": "synthetic manifest",
                "ruaccent": {"files": []}, "config_subset": {
                    "text_prep.yo_restore": None, "text_prep.strip_quotes": None,
                    "text_prep.open_end": None, "text_prep.ensure_terminal": None,
                    "render.leadin.phrase": None, "render.leadin.max_chars": None,
                    "pauses_ms.enum_pause_ms": None, "pauses_ms.sentence": None,
                    "stress.top_n": None, "pauses_ms.paragraph": None},
                "yo_dict_sha256": "yo", "pronounce_sha256": "pronounce",
                "verified_sha256": "verified", "watch_sha256": "watch", "exclude_sha256": "exclude",
                "trace_algo": "sutrace/1"}
    wire = json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert _analysis() == hashlib.sha256(wire).hexdigest()
