"""Synthetic advisory/interface tests. Real weights are explicitly opt-in."""
import dataclasses
import hashlib
import os

import pytest

from audiobook import ruaccent_adv as adv
from audiobook.unitmap import AnnotationError


def _occs(text):
    from audiobook.sutrace import SUTrace
    from audiobook.wordprov import process_section_occs
    trace = SUTrace("01_test", "0001", None, text, 0, [],
                    hashlib.sha256(text.encode()).hexdigest(), None, "ok")
    rows = [{"id": "0001", "n": 1, "text": text, "pause_after_ms": 0}]
    return process_section_occs("01_test", [{"type": "text", "text": text}], rows, [trace])[:2]


@pytest.mark.parametrize("source,output,expected", [
    ("Альфа", "Альф+а", [("resolved", 1)]),
    ("бета", "б+ета", [("resolved", 0)]),
    ("альфа", "альфа", [("no_stress", None)]),
    ("альфа", "+альф+а", [("multi_stress", None)]),
    ("альфа", "аль+фа", [("invalid_mark", None)]),
    ("альфа", "альфа+", [("invalid_mark", None)]),
    ("бета бета", "б+ета бет+а", [("resolved", 0), ("resolved", 1)]),
    ("Ребенок", "Реб+ёнок", [("resolved", 1)]),
    ("ёлка", "ёлка", [("no_stress", None)]),
    ("альфа бета", "б+ета +альфа", [("tokenization_mismatch", None)] * 2),
    ("альфа бета", "+альфа", [("tokenization_mismatch", None)] * 2),
    ("альфа", "+альфа б+ета", [("tokenization_mismatch", None)]),
    ("123!", "123!", []),
])
def test_literal_f6_outcomes(source, output, expected):
    assert adv.parse_advice(source, output) == expected


def test_original_spelling_and_provenance_survive_yo_advice():
    occs, analysis = _occs("Ребенок")
    before = dataclasses.astuple(occs[0])[:29]
    result = adv.apply_advisory(occs, analysis, lambda _: "Реб+ёнок")
    assert dataclasses.astuple(result[0])[:29] == before
    assert result[0].form_analysis == "Ребенок"
    assert (result[0].f6_status, result[0].expected_source, result[0].expected_vowel) == ("resolved", "ruaccent", 1)
    assert occs[0].f6_status == "not_run"


def test_sentence_contract_without_added_punctuation():
    occs, analysis = _occs("А. Бета. Альфа! Гамма")
    calls = []
    def process(sentence):
        calls.append(sentence)
        return sentence
    adv.apply_advisory(occs, analysis, process)
    assert calls == ["А. Бета.", "Альфа!", "Гамма"]


def test_not_run_is_explicit():
    occs, analysis = _occs("Альфа")
    result = adv.apply_advisory(occs, analysis, None)[0]
    assert (result.f6_status, result.f6_vowel, result.reason) == ("not_run", None, "ruaccent_not_run")


def test_token_free_never_invokes_model():
    assert adv.apply_advisory([], "123!", lambda _: pytest.fail("Token-free model invocation")) == []


def test_runtime_error_has_no_sensitive_message():
    occs, analysis = _occs("Альфа")
    def broken(_):
        raise RuntimeError("private synthetic diagnostic")
    with pytest.raises(AnnotationError, match="RUACCENT_RUNTIME_ERROR") as caught:
        adv.apply_advisory(occs, analysis, broken)
    assert "private" not in str(caught.value)


def test_init_error_does_not_become_not_run(monkeypatch):
    from audiobook import accent
    monkeypatch.setattr(adv, "ruaccent_content_identity", lambda: {})
    def broken():
        raise FileNotFoundError("synthetic missing model")
    monkeypatch.setattr(accent, "_get_accentizer", broken)
    with pytest.raises(AnnotationError, match="RUACCENT_INIT_ERROR"):
        adv.load_pinned_runtime()


def test_alignment_failure_and_override_keep_precedence():
    occs, analysis = _occs("Альфа бета")
    occs[0].alignment_status = "prep_token_mismatch"
    occs[1].f1_rule = "бета"
    result = adv.apply_advisory(occs, analysis, lambda _: "+Альфа бе+та")
    assert result[0].reason == "prep_token_mismatch"
    assert result[1].status == "covered_by_override"


def test_runtime_identity_hashes_same_size_contents(tmp_path):
    models, package = tmp_path / "models", tmp_path / "package"
    (models / "nn").mkdir(parents=True)
    (models / "dictionary").mkdir()
    package.mkdir()
    model = models / "nn" / "model.bin"
    model.write_bytes(b"one")
    (models / "dictionary" / "words.json").write_text("{}", encoding="utf-8")
    (package / "runtime.py").write_text("synthetic", encoding="utf-8")
    loader = tmp_path / "loader.py"
    loader.write_text("synthetic loader", encoding="utf-8")
    kwargs = dict(models=models, package=package, loader=loader, versions={"ruaccent": "synthetic"}, require_pin=False)
    original = adv.ruaccent_content_identity(**kwargs)
    from audiobook.wordprov import source_fp
    from audiobook.stress_fp import analysis_fp
    units = {"01_test": [{"type": "text", "text": "Альфа"}]}
    source = source_fp(units)
    def fingerprint(identity):
        return analysis_fp(source, "synthetic manifest", identity, {}, yo_dict_sha256=None,
                           pronounce_sha256=None, verified_sha256=None, watch_sha256=None, exclude_sha256=None)
    stamp = model.stat()
    model.write_bytes(b"two")
    os.utime(model, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    changed = adv.ruaccent_content_identity(**kwargs)
    assert changed != original
    assert fingerprint(changed) != fingerprint(original)
    assert source_fp(units) == source
    assert original["files"] == sorted(original["files"])
    with pytest.raises(AnnotationError, match="RUACCENT_RUNTIME_PIN_MISMATCH"):
        adv.ruaccent_content_identity(**{**kwargs, "require_pin": True})


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("RUN_WP3_REAL") != "1", reason="Explicit pinned offline smoke only")
def test_pinned_offline_interface():
    process, identity = adv.load_pinned_runtime()
    probes = [("На столе лежит красная книга.", "На стол+е леж+ит кр+асная кн+ига."),
              ("Старинный замок стоит у реки.", "Стар+инный з+амок сто+ит у рек+и."),
              ("Ребенок несет зеленое ведро.", "Реб+ёнок нес+ёт зел+ёное ведр+о.")]
    assert len(identity["files"]) == 77  # B1's 76 files plus its separately pinned loader.
    for source, expected in probes:
        assert process(source) == expected
        assert all(status in ("resolved", "no_stress") for status, _ in adv.parse_advice(source, expected))
