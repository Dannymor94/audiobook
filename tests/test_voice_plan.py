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


def test_cli_report_stays_local_and_source_manifest_unchanged(config, monkeypatch, tmp_path):
    import json
    from audiobook import paths

    text = tmp_path / "text"
    blocks = text / "blocks"
    blocks.mkdir(parents=True)
    out = tmp_path / "out"
    section = "01_fixture"
    units = [{"type": "paragraph", "text": "Положить на полку."}]
    (text / (section + ".norm.txt")).write_text(units[0]["text"] + "\n", encoding="utf-8")
    (blocks / (section + ".blocks.json")).write_text(
        json.dumps({"blocks": units}, ensure_ascii=False), encoding="utf-8")
    manifest = out / "sections" / section / "manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    initial = json.dumps(baseline(units, config)[0], ensure_ascii=False) + "\n"
    manifest.write_text(initial, encoding="utf-8")
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    monkeypatch.setattr(pronounce, "load_table", lambda: {})
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"на полку": "на пОлку"}, ensure_ascii=False), encoding="utf-8")
    assert voice_plan.run(config, section, str(rules), tag="trial") == 0
    result = out / "voice_plan" / section / "trial.json"
    report = json.loads(result.read_text(encoding="utf-8"))
    assert report["counts"] == {"needs_synth": 1}
    assert manifest.read_text(encoding="utf-8") == initial
    rules.write_text("null", encoding="utf-8")
    with pytest.raises(SystemExit, match="BLOCKED"):
        voice_plan.run(config, section, str(rules), tag="invalid")
    assert not (result.parent / "invalid.json").exists()


def test_chapter_title_carrier_scoped_and_default_parity(config):
    config["render"] = {"leadin": {"phrase": "Нейтральный контекст.", "max_chars": 55}}
    units = [
        {"type": "heading", "level": 1, "text": "Глава первая. Пример"},
        {"type": "paragraph", "text": "Текст."},
        {"type": "heading", "level": 2, "text": "Подзаголовок"},
        {"type": "heading", "level": 1, "text": "Глава вторая. Метка: Название"},
        {"type": "paragraph", "text": "Конец."},
    ]
    original = baseline(units, config)
    off = deepcopy(config)
    off["render"]["leadin"]["chapter_title_carrier"] = False
    assert baseline(units, off) == original

    enabled = deepcopy(config)
    enabled["render"]["leadin"]["chapter_title_carrier"] = True
    updated = baseline(units, enabled)
    assert [r["text"] for r in updated] == [r["text"] for r in original]
    assert [r["pause_after_ms"] for r in updated] == [r["pause_after_ms"] for r in original]
    changed = [i for i, (a, b) in enumerate(zip(original, updated)) if a["hash"] != b["hash"]]
    assert changed == [1, 6]
    assert updated[1]["leadin"] == "Глава первая."
    assert updated[6]["leadin"] == "Глава вторая."
    assert voice_plan.prepared_input(updated[1], enabled, {}) == "Глава первая. Пример"
    plan = voice_plan.plan_section(units, original, config, {}, chapter_title_carrier=True)
    assert plan["counts"] == {"needs_synth": 2, "review_only": 6}
    assert not plan["blocked"]
    assert config["render"]["leadin"].get("chapter_title_carrier") is None


def test_chapter_title_carrier_hash_binds_padded_dictionary(config):
    config["render"] = {"leadin": {"chapter_title_carrier": True}}
    units = [{"type": "heading", "level": 1, "text": "Глава первая. Пример"}]
    old = baseline(units, config)
    rules = {"первая": "пЕрвая"}
    new = baseline(units, config, rules)
    assert old[1]["text"] == new[1]["text"]
    assert old[1]["leadin"] == new[1]["leadin"]
    assert old[1]["hash"] != new[1]["hash"]
    assert voice_plan.prepared_input(old[1], config, {}) != voice_plan.prepared_input(new[1], config, rules)
    plan = voice_plan.plan_section(units, old, config, {}, rules=rules)
    assert not plan["blocked"]


def test_chapter_title_carrier_requires_actual_split(config):
    config["render"] = {"leadin": {"chapter_title_carrier": True}}
    config["pauses_ms"].pop("heading_number")
    config["pauses_ms"].pop("heading_colon")
    units = [{"type": "heading", "level": 1, "text": "Глава первая. Пример"},
             {"type": "heading", "level": 2, "text": "Подзаголовок"}]
    old = baseline(units, config)
    assert all(r["leadin"] is None for r in old)
    config["render"]["leadin"]["chapter_title_carrier"] = "false"
    with pytest.raises(ValueError, match="boolean"):
        baseline(units, config)


def test_chapter_title_carrier_rejects_enum_mode(config):
    config["render"] = {"leadin": {"chapter_title_carrier": True}}
    config["pauses_ms"]["enum_pause_ms"] = 100
    units = [{"type": "heading", "level": 1, "text": "Глава первая. Пример"}]
    with pytest.raises(ValueError, match="enum_pause_ms"):
        baseline(units, config)


def test_exact_phrase_final_comma_candidate(config):
    units = [{"type": "paragraph", "text": "Положить на полку и уйти."},
             {"type": "paragraph", "text": "Осмотреть полку."}]
    old = baseline(units, config)
    rules = {"на полку": "на полку,"}
    plan = voice_plan.plan_section(units, old, config, {}, rules=rules)
    assert plan["counts"] == {"needs_synth": 1, "review_only": 1}
    assert not plan["blocked"]
    candidate = baseline(units, config, rules)
    assert candidate[0]["text"] == old[0]["text"]
    assert voice_plan.prepared_input(candidate[0], config, rules) == "Положить на полку, и уйти."
    for invalid in ({"полку": "полку,"}, {"на полку": "на полку,,"},
                    {"на полку": "на, полку"}, {"на полку": "на пОлку,"}):
        with pytest.raises(ValueError):
            voice_plan.validate_rules(invalid)


def test_live_generation_seed_is_not_config_seed(config):
    units = [{"type": "paragraph", "text": "Пример."}]
    old = baseline(units, config)
    old[0].update(status="done", seed=314159, seed_override=314159)
    plan = voice_plan.plan_section(units, old, config, {})
    assert plan["counts"] == {"review_only": 1}
    old[0]["hash"] = "stale"
    with pytest.raises(ValueError, match="STALE_MANIFEST"):
        voice_plan.plan_section(units, old, config, {})


def test_reviewed_stage_preserves_live_audio_and_binds_receipt(config, monkeypatch, tmp_path):
    import json
    import numpy as np
    import soundfile as sf
    from audiobook import paths, reviewed_stage

    units = [{"type": "paragraph", "text": "Положить на полку и уйти."},
             {"type": "paragraph", "text": "Далее."}]
    section = "01_fixture"
    monkeypatch.setattr(paths, "OUT", tmp_path)
    monkeypatch.setattr(chunker, "load_units", lambda *_: units)
    monkeypatch.setattr(reviewed_stage, "generation_identity", lambda _: {"model": "fixture"})
    monkeypatch.setattr(reviewed_stage, "input_identity", lambda row, cfg, table: {
        "input_sha256": voice_plan.digest(voice_plan.prepared_input(row, cfg, table)),
        "leadin": row["leadin"]})
    live = tmp_path / "sections" / section
    (live / "chunks").mkdir(parents=True)
    old = baseline(units, config)
    for i, row in enumerate(old):
        row.update(status="done", seed=123 + i, duration_ms=100)
        sf.write(live / "chunks" / (row["id"] + ".wav"),
                 np.full(2400, 0.01 * (i + 1), dtype=np.float32), 24000, subtype="FLOAT")
    chunker._write_manifest(live / "manifest.jsonl", old)
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    rules = {"на полку": "на полку,"}
    target = baseline(units, config, rules)[0]
    sample = tmp_path / "reviewed.wav"
    sf.write(sample, np.full(4800, 0.03, dtype=np.float32), 24000, subtype="FLOAT")
    receipt = {"wav": str(sample), "seed": 123, "wav_sha256": reviewed_stage.file_digest(sample),
               "input": reviewed_stage.input_identity(target, config, rules),
               "generation": {"model": "fixture"}}
    with pytest.raises(ValueError, match="TRIAL_INPUT_OR_GENERATION_MISMATCH"):
        reviewed_stage.stage_section(section, "bad", config, {}, rules,
                                     {"0001": {**receipt, "input": {}}}, chapter_title_carrier=False)
    with pytest.raises(ValueError, match="TRIAL_WAV_DIGEST_MISMATCH"):
        reviewed_stage.stage_section(section, "bad", config, {}, rules,
                                     {"0001": {**receipt, "wav_sha256": "bad"}}, chapter_title_carrier=False)
    assert not (tmp_path / "reviewed_stage" / "bad").exists()
    stage = reviewed_stage.stage_section(section, "good", config, {}, rules,
                                         {"0001": receipt}, chapter_title_carrier=False)
    rows = chunker._read_manifest(stage / "manifest.jsonl")
    assert rows[0]["hash"] == target["hash"] and rows[0]["locked"]
    assert rows[0]["seed"] == rows[0]["seed_override"] == 123
    assert rows[0]["duration_ms"] == 200 and rows[0]["status"] == "done"
    assert rows[1] == old[1]
    assert (stage / "chunks" / "0001.wav").read_bytes() == sample.read_bytes()
    assert (stage / "chunks" / "0002.wav").read_bytes() == before[live / "chunks" / "0002.wav"]
    assert json.loads((stage / "READY.json").read_text())["adopted_ids"] == ["0001"]
    assert all(p.read_bytes() == data for p, data in before.items())
    with pytest.raises(FileExistsError):
        reviewed_stage.stage_section(section, "good", config, {}, rules,
                                     {"0001": receipt}, chapter_title_carrier=False)


def test_accept_original_exact_wav_and_verified_seed(config, monkeypatch, tmp_path):
    import numpy as np
    import soundfile as sf
    from audiobook import paths, redo, reviewed_stage

    section = "01_fixture"
    units = [{"type": "paragraph", "text": "Пример."},
             {"type": "paragraph", "text": "Далее."}]
    monkeypatch.setattr(paths, "OUT", tmp_path)
    monkeypatch.setattr(chunker, "load_units", lambda *_: units)
    monkeypatch.setattr(pronounce, "load_table", lambda: {})
    live = tmp_path / "sections" / section
    (live / "chunks").mkdir(parents=True)
    old = baseline(units, config)
    old[0].update(status="manual", seed=125, cer=0.131)
    manifest = live / "manifest.jsonl"
    chunker._write_manifest(manifest, old)
    wav = live / "chunks" / "0001.wav"
    sf.write(wav, np.full(2400, 0.02, dtype=np.float32), 24000, subtype="FLOAT")
    data = wav.read_bytes()
    before = manifest.read_bytes()
    digest = reviewed_stage.file_digest(wav)
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        redo.run_accept_original(config, section, "0001", "0" * 40, digest, 123)
    with pytest.raises(ValueError, match="WAV_MISMATCH"):
        redo.run_accept_original(config, section, "0001", old[0]["hash"], "0" * 64, 123)
    assert manifest.read_bytes() == before
    assert redo.run_accept_original(config, section, "0001", old[0]["hash"], digest, 123) == 0
    rows = chunker._read_manifest(manifest)
    assert rows[0]["status"] == "done" and rows[0]["locked"]
    assert rows[0]["seed"] == rows[0]["seed_override"] == 123
    assert rows[0]["hash"] == old[0]["hash"] and rows[0]["cer"] == 0.131
    assert rows[0]["duration_ms"] == 100 and rows[1] == old[1]
    assert wav.read_bytes() == data


def test_scoped_qc_does_not_render_or_touch_other_rows(config, monkeypatch, tmp_path):
    from audiobook import paths, qc, probe, worker

    section = "01_fixture"
    units = [{"type": "paragraph", "text": "Пример."},
             {"type": "paragraph", "text": "Далее."}]
    config["qc"] = {"cer_threshold": 0.05}
    monkeypatch.setattr(paths, "OUT", tmp_path)
    monkeypatch.setattr(chunker, "load_units", lambda *_: units)
    monkeypatch.setattr(pronounce, "load_table", lambda: {})
    monkeypatch.setattr(probe, "load_watch", lambda: [])
    monkeypatch.setattr(qc, "load_whisper", lambda: object())
    monkeypatch.setattr(qc, "_release", lambda _: None)
    def forbidden(*args, **kwargs):
        raise AssertionError("scoped measurement must not synthesize")
    monkeypatch.setattr(worker, "TimeoutSynth", forbidden)
    seen = []
    def measure(_wm, wav, _text, _watch, _conf):
        seen.append(wav.name)
        return {"cer": 0.2}
    monkeypatch.setattr(qc, "_measure", measure)
    sec = tmp_path / "sections" / section
    (sec / "chunks").mkdir(parents=True)
    old = baseline(units, config)
    old[0].update(status="done", seed=123, duration_ms=100)
    old[1].update(status="done", seed=456, locked=True)
    manifest = sec / "manifest.jsonl"
    chunker._write_manifest(manifest, old)
    for row in old:
        (sec / "chunks" / (row["id"] + ".wav")).write_bytes(b"fixture")
    before = manifest.read_bytes()
    with pytest.raises(ValueError, match="UNKNOWN_CHUNK"):
        qc.check_selected(config, section, ["9999"])
    assert manifest.read_bytes() == before and not seen
    assert qc.check_selected(config, section, ["0001"]) == 2
    rows = chunker._read_manifest(manifest)
    assert seen == ["0001.wav"]
    assert rows[0]["status"] == "manual" and rows[0]["seed"] == 123
    assert rows[1] == old[1]
    assert all(p.read_bytes() == b"fixture" for p in (sec / "chunks").glob("*.wav"))
    assert qc.check_selected(config, section, ["0002"]) == 0
    assert chunker._read_manifest(manifest)[1]["locked"]


def test_failed_qc_retries_do_not_change_wav_seed(config, monkeypatch, tmp_path):
    from audiobook import paths, qc, probe, synth, worker

    section = "01_fixture"
    units = [{"type": "paragraph", "text": "Пример."}]
    config["qc"] = {"cer_threshold": 0.05, "max_retries": 2}
    monkeypatch.setattr(paths, "OUT", tmp_path)
    monkeypatch.setattr(chunker, "load_units", lambda *_: units)
    monkeypatch.setattr(pronounce, "load_table", lambda: {})
    monkeypatch.setattr(probe, "load_watch", lambda: [])
    monkeypatch.setattr(qc, "load_whisper", lambda: object())
    monkeypatch.setattr(qc, "_release", lambda _: None)
    monkeypatch.setattr(qc, "_measure", lambda *a: {"cer": 0.2, "flag_words": []})
    monkeypatch.setattr(synth, "worker_config", lambda *a: {})
    monkeypatch.setattr(synth, "ensure_manifest_current", lambda *a: None)
    attempted = []
    class FakeEngine:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def synth(self, _text, seed, **kw):
            attempted.append(seed)
            return None
    monkeypatch.setattr(worker, "TimeoutSynth", FakeEngine)
    sec = tmp_path / "sections" / section
    (sec / "chunks").mkdir(parents=True)
    rows = baseline(units, config)
    rows[0].update(status="done", seed=123, duration_ms=100)
    manifest = sec / "manifest.jsonl"
    chunker._write_manifest(manifest, rows)
    wav = sec / "chunks" / "0001.wav"
    wav.write_bytes(b"old audio")
    qc.run(config, section)
    result = chunker._read_manifest(manifest)[0]
    assert attempted == [124, 125]
    assert result["seed"] == 123 and result["status"] == "manual"
    assert wav.read_bytes() == b"old audio"
