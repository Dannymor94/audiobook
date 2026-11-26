import json

from audiobook.rhythm_audit import analyze, audit


def test_explicit_list_offsets_and_source_unchanged():
    text = "Список: красный, синий, зелёный."
    result = analyze(text)
    commas = [i for i, c in enumerate(text) if c == ","]
    assert result["review_candidate_offsets"] == commas
    assert all(text[i] == "," for i in result["legacy_comma_offsets"])


def test_protected_and_function_word_groups():
    text = "Ответ: «один, два», 3,14, с кем-то."
    result = analyze(text)
    assert result["review_candidate_offsets"] == []
    assert text.index(",") in result["protected_comma_offsets"]
    assert text.index(",14") in result["protected_comma_offsets"]


def test_unhashed_sentence_split_risk():
    assert analyze("Первое. Второе.")["legacy_unhashed_sentence_split_risk"]
    assert not analyze("Одно предложение.")["legacy_unhashed_sentence_split_risk"]


def test_exact_repeated_text_offsets():
    text = "Список: один, два, три. Список: один, два, три."
    result = analyze(text)
    assert result["review_candidate_offsets"] == [
        i for i, c in enumerate(text) if c == ","]


def test_manifest_readonly(tmp_path):
    p = tmp_path / "manifest.jsonl"
    data = json.dumps({"id": "0001", "hash": "test",
                       "text": "Список: один, два, три."}, ensure_ascii=False)
    p.write_text(data, encoding="utf-8")
    before = set(tmp_path.iterdir())
    result = audit(p)
    assert result["candidate_chunks"] == 1
    assert result["chunk_count"] == 1
    assert p.read_text(encoding="utf-8") == data
    assert set(tmp_path.iterdir()) == before
