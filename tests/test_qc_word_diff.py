"""Word-level reporting uses the same normalization as CER; no models."""
import json

import pytest

from audiobook import qc, suspects, takes


def test_ending_and_report_only():
    diff, = qc.word_diff("мы видим тебя", "мы видим тебе")
    assert (diff["op"], diff["ref"], diff["hyp"], diff["class"]) == (
        "sub", "тебя", "тебе", "ending")
    base = {"cer": 0.01, "flag_words": []}
    flagged = dict(base, flag_words=[["тебя→тебе", 1, 0.9, "ending"]])
    assert qc.qc_status(base, 0.05) == qc.qc_status(flagged, 0.05) == "done"
    assert takes.score(base, 0.05) == takes.score(flagged, 0.05)


@pytest.mark.parametrize("ref,hyp,ops", [
    ("мы видим тебя", "мы тебя", ["del"]),
    ("мы тебя", "мы видим тебя", ["ins"]),
    ("альфа бета", "гамма", ["sub", "del"]),
    ("", "слово", ["ins"]),
    ("слово", "", ["del"]),
])
def test_operations(ref, hyp, ops):
    assert [d["op"] for d in qc.word_diff(ref, hyp)] == ops


@pytest.mark.parametrize("ref,hyp", [
    ("Ещё 21 тест", "еще двадцать один тест"),
    ("Глава тринадцатая", "Глава 13"),
])
def test_normalized_numbers_and_yo(ref, hyp):
    rn = qc.normalize_for_cer(ref)
    hn = qc.normalize_for_cer(qc._numbers_like_ref(hyp, rn.split()))
    assert qc.word_diff(rn, hn) == []


def test_measure_and_suspects_timing(monkeypatch, tmp_path):
    words = [{"w": "мы", "s": 0, "e": 0.2, "p": 0.99},
             {"w": "видим", "s": 0.3, "e": 0.6, "p": 0.99},
             {"w": "тебе", "s": 1.2, "e": 1.5, "p": 0.99}]
    monkeypatch.setattr(qc, "transcribe_words", lambda *a: ("мы видим тебе", words))
    monkeypatch.setattr(takes, "wav_peak", lambda *a: 0.5)
    row = qc._measure(None, tmp_path / "placeholder.wav", "мы видим тебя", set(), 0.6)
    assert row["word_diff"] == "тебя→тебе:ending"
    row["id"] = "0001"
    item, = suspects.collect([row], {"0001": (2000, 100)})
    assert item["t_ms"] == 3100
    assert item["why"] == "ending"


def test_timing_after_expanded_number_and_deletion():
    words = [{"w": "21", "s": 0.1, "e": 0.5, "p": 0.9},
             {"w": "тебе", "s": 0.8, "e": 1.1, "p": 0.9}]
    ref = "двадцать один тебя"
    hyp = "двадцать один тебе"
    assert qc._diff_flags(qc.word_diff(ref, hyp), hyp, words, ref.split())[0][1] == 0.8
    diff = qc.word_diff(hyp + " слово", hyp)
    assert qc._diff_flags(diff, hyp, words, ref.split())[0][1] == 1.1
    assert qc._diff_flags(diff, hyp, [], ref.split())[0][1] == 0


def test_long_tail_is_word_and_repeated_alignment_deterministic():
    assert qc.word_diff("тест", "тестирование")[0]["class"] == "word"
    diff, = qc.word_diff("да да нет", "да нет")
    assert (diff["op"], diff["ref_index"], diff["hyp_index"]) == ("del", 0, 0)


def test_qc_run_reports_counts_without_retrying_word_errors(tmp_path, monkeypatch, capsys):
    from audiobook import paths, probe, pronounce, synth, reuse
    monkeypatch.setattr(paths, "OUT", tmp_path)
    sec = tmp_path / "sections" / "placeholder"
    chunks = sec / "chunks"
    chunks.mkdir(parents=True)
    rows = [{"id": "0001", "text": "мы видим тебя", "status": "done", "hash": "a" * 40},
            {"id": "0002", "text": "альфа", "status": "done", "hash": "b" * 40}]
    for row in rows:
        (chunks / f"{row['id']}.wav").write_bytes(b"placeholder")
    manifest = sec / "manifest.jsonl"
    synth._write_manifest(manifest, rows)
    monkeypatch.setattr(synth, "ensure_manifest_current", lambda *a: None)
    monkeypatch.setattr(synth, "worker_config", lambda *a: {})
    monkeypatch.setattr(probe, "load_watch", lambda: [])
    monkeypatch.setattr(pronounce, "load_table", lambda: {})
    monkeypatch.setattr(qc, "load_whisper", lambda: object())
    monkeypatch.setattr(takes, "wav_peak", lambda *a: 0.5)

    def transcribe(model, wav):
        text = "мы видим тебе" if wav.stem == "0001" else "гамма"
        return text, [{"w": w, "s": i, "e": i + 0.5, "p": 0.99}
                      for i, w in enumerate(text.split())]

    monkeypatch.setattr(qc, "transcribe_words", transcribe)
    # A reporting-only resync can change selected transcript flags. The compact
    # field must reflect those final flags rather than stale pre-resync metrics.
    def resync(sec, rows):
        if "word_diff" in rows[0]:
            rows[0]["word_diff"] = "stale"
        return False

    monkeypatch.setattr(reuse, "resync", resync)
    cfg = {"qc": {"cer_threshold": 1.0, "max_retries": 0}, "model": {},
           "render": {"reuse_identical": True}}
    assert qc.run(cfg, "placeholder") == 0
    result = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert result[0]["word_diff"] == "тебя→тебе:ending"
    assert result[1]["word_diff"] == "альфа→гамма:word"
    assert all(row["status"] == "done" for row in result)
    assert "ending=1  word=1" in capsys.readouterr().out
