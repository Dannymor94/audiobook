"""Synthetic contracts only: no models, manuscript, audio or production edits."""
from copy import deepcopy

import pytest

from audiobook import chunker, pronounce, voice_plan


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr(chunker, "latents_hash", lambda cfg: "fixture-latents")
    return {
        "model": {"name": "fixture", "seed": 42, "temperature": 1.0, "language": "ru"},
        "reference": {"path": "fixture.wav"},
        "pauses_ms": {"sentence": 350, "paragraph": 900, "chapter": 2000,
                      "heading_number": 1200, "heading_colon": 700, "heading_level": {1: 2000}},
        "chunking": {"target": 40, "cap": 40, "min_len": 1},
    }


def baseline(units, cfg, table=None):
    return chunker.build_manifest(units, cfg, pronounce_table=table or {})


def test_explicit_table_default_parity(config, monkeypatch):
    units = [{"type": "paragraph", "text": "Уложить на полку."}]
    table = {"на полку": "на пОлку"}
    monkeypatch.setattr(pronounce, "load_table", lambda: table)
    assert chunker.build_manifest(units, config) == baseline(units, config, table)
    assert baseline(units, config)[0]["hash"] != baseline(units, config, table)[0]["hash"]


def test_heading_source_order_and_pause_only(config):
    units = [{"type": "heading", "level": 1, "text": "Глава первая. Опыт: Пример"},
             {"type": "paragraph", "text": "Что случилось?"},
             {"type": "paragraph", "text": "Что случилось?"},
             {"type": "paragraph", "text": "Далее."}]
    old = baseline(units, config)
    saved = deepcopy(old)
    cfg_saved = deepcopy(config)
    plan = voice_plan.plan_section(units, old, config, {}, paragraph=1200, heading=2200)
    rows = plan["rows"]
    assert [r["source_anchor"]["role"] for r in rows[:3]] == [
        "chapter_number", "heading_label", "chapter_title"]
    assert rows[2]["pause_after_ms"] == 2200
    assert rows[3]["source_anchor"]["opening_after_heading"]
    assert rows[3]["source_anchor"]["role"] == "question"
    assert rows[3]["source_anchor"]["unit_ordinal"] == 2
    assert rows[4]["source_anchor"]["unit_ordinal"] == 3
    assert rows[3]["source_anchor"]["unit_sha256"] == rows[4]["source_anchor"]["unit_sha256"]
    assert all(r["old_hash"] == r["candidate_hash"] for r in rows)
    assert plan["counts"] == {"pause_only": 3, "review_only": 3}
    assert not plan["blocked"]
    assert old == saved and config == cfg_saved


def test_offsets_reproduce_source_with_whitespace_and_duplicates(config):
    units = [{"type": "paragraph", "text": "Пример.  Пример. Пример."}]
    plan = voice_plan.plan_section(units, baseline(units, config), config, {})
    anchor = plan["rows"][0]["source_anchor"]
    assert units[0]["text"][anchor["start"]:anchor["end"]].split() == [
        "Пример.", "Пример.", "Пример."]


def test_contextual_pronunciation_is_scoped_and_cache_impact(config):
    units = [{"type": "paragraph", "text": "Положить на полку."},
             {"type": "paragraph", "text": "Осмотреть полку."}]
    old = baseline(units, config)
    old[0].update(status="done", locked=True)
    plan = voice_plan.plan_section(units, old, config, {}, rules={"на полку": "на пОлку"})
    assert plan["counts"] == {"needs_synth": 1, "review_only": 1}
    assert plan["rendered_hash_changes"] == plan["locked_hash_changes"] == 1
    assert plan["rows"][0]["model_input_changed"]
    assert not plan["rows"][1]["model_input_changed"]
    assert plan["candidate_rule_hits"][0]["hits_including_carrier"] == 1
    assert not plan["blocked"]


def test_carrier_only_change_blocks_instead_of_claiming_cache_safety(config):
    config["render"] = {"leadin": {"context": {"mode": "previous", "max_chars": 60}}}
    units = [{"type": "paragraph", "text": "Замок закрыт."},
             {"type": "paragraph", "text": "Проверка завершена."}]
    old = baseline(units, config)
    assert old[1]["leadin"] == "Замок закрыт."
    plan = voice_plan.plan_section(units, old, config, {}, rules={"Замок": "ЗАмок"})
    assert plan["blocked"]
    assert plan["rows"][1]["action"] == "blocked_hash_gap"
    assert plan["rows"][1]["model_input_changed"]
    assert not plan["rows"][1]["hash_changed"]


def test_stale_manifest_and_mismatch_are_rejected(config):
    units = [{"type": "paragraph", "text": "Проверка."}]
    old = baseline(units, config)
    old[0]["hash"] = "stale"
    with pytest.raises(ValueError, match="STALE_MANIFEST"):
        voice_plan.plan_section(units, old, config, {})
    old = baseline(units, config)
    old[0]["text"] = "Не тот текст."
    with pytest.raises(ValueError, match="SOURCE_CHUNK_MISMATCH"):
        voice_plan.source_anchors(units, old, config)


@pytest.mark.parametrize("rules", [
    {"слово": "сл+ово"}, {"слово": "Слово"}, {"слово": "слова"},
    {"на слово": "на  слово"}, {"слово": "слово"}, ["bad"],
])
def test_invalid_candidate_rules(rules):
    with pytest.raises(ValueError):
        voice_plan.validate_rules(rules)


def test_rule_and_pause_validation(config):
    assert voice_plan.validate_rules({"берет": "берёт"}) == {"берет": "берёт"}
    assert voice_plan.validate_rules({"на полку": "на пОлку"}) == {"на полку": "на пОлку"}
    for value in (-1, 5001, True, 2.5):
        with pytest.raises(ValueError):
            voice_plan.pause_config(config, sentence=value)
    with pytest.raises(ValueError):
        voice_plan._unique_object([("x", "a"), ("x", "b")])


def test_cli_parser_requires_section_and_has_no_apply():
    from audiobook.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["voice-plan", "--section", "01_fixture", "--sentence-ms", "500"])
    assert args.section == "01_fixture" and args.sentence_ms == 500
    with pytest.raises(SystemExit):
        parser.parse_args(["voice-plan"])
    with pytest.raises(SystemExit):
        parser.parse_args(["voice-plan", "--section", "01_fixture", "--apply"])
