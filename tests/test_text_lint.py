"""Слой 1: text_lint на плейсхолдерном тексте (не цитаты рукописи), всё во tmp_path."""
from __future__ import annotations

import pytest

from audiobook import paths, text_lint as tl


def _one(text: str, stem: str = "01_test") -> dict[str, str]:
    return {stem: text}


def test_fold_and_context():
    assert tl.fold("ЁЛКА") == "елка"
    text = "а" * 100 + " слово " + "б" * 100
    s = text.index("слово")
    ctx = tl.context(text, s, s + 5)
    assert "**слово**" in ctx
    assert len(ctx) <= 2 * tl.CONTEXT_RADIUS + len("**слово**") + 2
    assert "\n" not in tl.context("раз\nдва три\n\nчетыре", 4, 7)


def test_read_sections_only_norm_files(tmp_path, monkeypatch):
    (tmp_path / "02_b.norm.txt").write_text("два", encoding="utf-8")
    (tmp_path / "01_a.norm.txt").write_text("один", encoding="utf-8")
    (tmp_path / "01_a.txt").write_text("не читать", encoding="utf-8")
    monkeypatch.setattr(paths, "TEXT", tmp_path)
    assert list(tl.read_sections()) == ["01_a", "02_b"]


def test_missing_yo_lists_every_plain_occurrence():
    secs = {"01_a": "Лёд тонкий. Лед тает.", "02_b": "Снова лед и снова лёд."}
    res = tl.find_missing_yo(secs)
    assert [d["plain"] for d in res] == ["лед"]
    d = res[0]
    assert d["yo"] == {"лёд": 2}
    assert [h[0] for h in d["hits"]] == ["01_a", "02_b"]
    assert "**Лед**" in d["hits"][0][1]


def test_missing_yo_ignores_consistent_and_ambiguous_words():
    # «стол» never has ё; «все»/«всё» are handled by the ambiguous section.
    secs = _one("Стол стоит. Все пришли. Всё прошло. Стол.")
    assert tl.find_missing_yo(secs) == []


def test_ambiguous_only_when_yo_form_present():
    assert tl.find_ambiguous_yo(_one("Все пришли. Все ушли.")) == []
    res = tl.find_ambiguous_yo(_one("Все пришли. Всё ушло. Еще раз. Ещё раз."))
    by = {d["plain"]: d for d in res}
    assert set(by) == {"все", "еще"}
    assert (by["все"]["n_plain"], by["все"]["n_yo"]) == (1, 1)
    assert len(by["еще"]["hits"]) == 1


def test_edit_distance_le():
    assert tl.edit_distance_le("кот", "кот", 2) == 0
    assert tl.edit_distance_le("кот", "код", 2) == 1
    assert tl.edit_distance_le("кот", "котик", 2) == 2
    assert tl.edit_distance_le("кот", "стакан", 2) > 2


def test_rare_neighbors_flags_typo_not_inflection():
    frequent = " ".join(["прекрасно"] * 6 + ["дорога"] * 6)
    secs = _one(frequent + " Прикрасно. Здесь дорогу.")
    res = tl.find_rare_neighbors(secs)
    words = {d["word"]: d for d in res}
    assert "прикрасно" in words
    assert words["прикрасно"]["neighbors"][0][0] == "прекрасно"
    assert words["прикрасно"]["neighbors"][0][2] == 1
    assert "дорогу" not in words          # differs only in the ending
    assert "прекрасно" not in words          # frequent words are never «rare»


def test_rare_neighbors_needs_same_first_letter_and_length():
    secs = _one(" ".join(["прекрасно"] * 6) + " дрекрасно прекрас")
    assert tl.find_rare_neighbors(secs) == []


def test_repeats_mixed_script_yotsya_triple():
    secs = _one("Он пришёл и и ушёл.\nСлово слоvо тут.\n"
                "Он обжётся и решил. Он живётся. Рууука. Ааа! Да, да.\n"
                "Конец и\nи начало.")
    rep = tl.find_repeats(secs)
    assert len(rep) == 1 and "**и и**" in rep[0][1]    # comma and line break are not repeats
    assert len(tl.find_mixed_script(secs)) == 1
    yo = tl.find_yotsya_i(secs)
    assert len(yo) == 1 and "обжётся" in yo[0][1]
    triple = tl.find_triple_letters(secs)
    assert len(triple) == 1 and "Рууука" in triple[0][1]    # «Ааа» is an interjection, skipped


def test_abbreviations_exclude_emphasis_and_short():
    secs = _one("Слово ООН и АБВГД. Потом ДА! Да что ты. Я и Я. Тут АБВГД снова.")
    res = {d["word"]: d for d in tl.find_abbreviations(secs)}
    assert set(res) == {"ООН", "АБВГД"}     # ДА is emphasis (да exists), «Я» is 1 letter
    assert res["АБВГД"]["count"] == 2


def test_hyphen_caps_digits_latin():
    secs = _one("Это ООН-подобный случай, а это кто-то. В 2024 году, 5-го числа, "
                "пишите на example.org или в PDF. Глава XIV. Слово бЕз.")
    assert [d["word"] for d in tl.find_hyphen_caps(secs)] == ["ООН-подобный"]
    digits = {d["word"] for d in tl.find_digits(secs)}
    assert {"2024", "5-го"} <= digits
    latin = {d["word"] for d in tl.find_latin(secs)}
    assert {"example.org", "PDF", "XIV"} <= latin


def test_latin_inside_cyrillic_word_is_not_a_latin_token():
    secs = _one("Слоvо рядом.")
    assert tl.find_latin(secs) == []
    assert len(tl.find_mixed_script(secs)) == 1


def _write_placeholder_book(text_dir):
    text_dir.mkdir()
    (text_dir / "01_a.norm.txt").write_text(
        "Лёд тонкий. Лед тает. Все пришли. Всё ушло. ООН решила. В 2024 году.\n",
        encoding="utf-8")
    (text_dir / "02_b.norm.txt").write_text("Снова лёд. Файл PDF.\n", encoding="utf-8")


def test_run_writes_report_and_summary(tmp_path, monkeypatch, capsys):
    _write_placeholder_book(tmp_path / "text")
    monkeypatch.setattr(paths, "TEXT", tmp_path / "text")
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert tl.run({}) == 0
    report = (tmp_path / "out" / "lint" / "text_lint.md").read_text(encoding="utf-8")
    for heading in ("## Вероятно пропущена ё", "## Неоднозначные е/ё",
                    "## Подозрительные формы", "## Для озвучки"):
        assert heading in report
    assert "### лед ×1" in report and "**Лед**" in report
    assert "**ООН**" in report and "**2024**" in report and "**PDF**" in report
    assert not list((tmp_path / "out" / "lint").glob("*.part"))
    out = capsys.readouterr().out
    assert "Вероятно пропущена ё (слов): 1" in out
    assert "Для озвучки: аббревиатуры: 1" in out


def test_run_without_texts_returns_1(tmp_path, monkeypatch, capsys):
    (tmp_path / "text").mkdir()
    monkeypatch.setattr(paths, "TEXT", tmp_path / "text")
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert tl.run({}) == 1
    assert not (tmp_path / "out").exists()


def test_run_does_not_modify_texts(tmp_path, monkeypatch):
    _write_placeholder_book(tmp_path / "text")
    before = {p.name: p.read_bytes() for p in (tmp_path / "text").iterdir()}
    monkeypatch.setattr(paths, "TEXT", tmp_path / "text")
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    tl.run({})
    assert {p.name: p.read_bytes() for p in (tmp_path / "text").iterdir()} == before


def test_cli_lint_text(tmp_path, monkeypatch, capsys):
    from audiobook.__main__ import main
    for var in ("PYTHONUTF8", "COQUI_TOS_AGREED", "HF_HUB_DISABLE_SYMLINKS_WARNING"):
        monkeypatch.setenv(var, "1")
    _write_placeholder_book(tmp_path / "text")
    monkeypatch.setattr(paths, "TEXT", tmp_path / "text")
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert main(["lint-text"]) == 0
    assert (tmp_path / "out" / "lint" / "text_lint.md").exists()


@pytest.mark.parametrize("mark", [",", ".", ";", ":", "!", "?", "…"])
@pytest.mark.parametrize("space", [" ", "  ", "\t", "\u00a0", "\u202f"])
def test_space_before_punctuation(mark, space):
    hits = tl.find_space_before_punctuation(_one(f"Тест{space}{mark} конец"))
    assert len(hits) == 1
    assert hits[0][0] == "01_test"
    assert f"**{space}{mark}**" in hits[0][1]


def test_punctuation_checks_ignore_normal_spacing_and_line_breaks():
    secs = _one("Тест, пример. Да; нет: вопрос? Ответ! Пауза…\n. Конец\n")
    assert tl.find_space_before_punctuation(secs) == []
    assert tl.find_mixed_punctuation(secs) == []


def test_slashes_between_letters_only():
    secs = _one("и/или он/она a/b/c ё/е 1/2 а/2 2/б / а / б")
    hits = tl.find_letter_slashes(secs)
    assert len(hits) == 5
    assert all(stem == "01_test" and "**/**" in ctx for stem, ctx in hits)


@pytest.mark.parametrize("run", [",.", ".,", ";:", ":;", "!,", "?;", "…?", "?!,", "?..,"])
def test_mixed_punctuation_reports_entire_run(run):
    hits = tl.find_mixed_punctuation(_one(f"Тест{run} Конец"))
    assert len(hits) == 1
    assert f"**{run}**" in hits[0][1]


@pytest.mark.parametrize("run", ["?!", "!?", "?..", "!..", "...", "!!", "??", "……"])
def test_allowed_or_identical_punctuation_is_not_reported(run):
    assert tl.find_mixed_punctuation(_one(f"Тест{run} Конец")) == []


def test_new_checks_report_context_with_default_radius():
    text = "а" * 100 + " , " + "б" * 100
    assert tl.find_space_before_punctuation(_one(text)) == [
        ("01_test", "а" * 40 + "** ,** " + "б" * 39)
    ]


def test_new_checks_in_report_and_summary_without_changing_text(tmp_path, monkeypatch, capsys):
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    source = text_dir / "01_test.norm.txt"
    source.write_text("Тест , и/или пример,; конец.\n", encoding="utf-8")
    before = source.read_bytes()
    monkeypatch.setattr(paths, "TEXT", text_dir)
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert tl.run({}) == 0
    assert source.read_bytes() == before
    report = (tmp_path / "out" / "lint" / "text_lint.md").read_text(encoding="utf-8")
    tts_report = report.split("## Для озвучки", 1)[1]
    output = capsys.readouterr().out
    for title in ("Пробел перед знаком", "Слэш между буквами", "Сдвоенные разные знаки"):
        assert f"### {title} (1)" in tts_report
        assert f"Для озвучки: {title.lower()}: 1" in output
    assert "** ,**" in tts_report
    assert "**/**" in tts_report
    assert "**,;**" in tts_report
