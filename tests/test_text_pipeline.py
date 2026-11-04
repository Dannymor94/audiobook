"""Layer-1 tests for the text processing pipeline. No models, no network."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from audiobook.text_blocks import (
    block_sha1,
    cyrillic_slug,
    normalize_paragraphs,
)
from audiobook.apply_rules import apply_section, assert_no_arrows


def _sleep_worker(cfg, in_q, out_q):
    """Fake TimeoutSynth worker: no model. Sleeps float(task['text']) seconds
    then replies, so a task can be made to exceed the timeout. Module-level so
    the spawn child can import it."""
    import time
    out_q.put("ready")
    while True:
        task = in_q.get()
        if task is None:
            return
        time.sleep(float(task["text"]))
        out_q.put({"ok": True, "wav": [1.0, 2.0, 3.0]})


# ---------------------------------------------------------------------------
# normalize() chain tests
# ---------------------------------------------------------------------------

def test_normalize_chain_joins():
    """Ch.30-style: 6 content paragraphs joined by 5 ↓ paragraphs → ONE chain block."""
    parts = ['Шаг первый', 'Шаг второй', 'Шаг третий', 'Шаг четвёртый', 'Шаг пятый', 'Шаг шестой']
    paras = []
    for i, p in enumerate(parts):
        paras.append(('Normal', p))
        if i < len(parts) - 1:
            paras.append(('Normal', '↓'))

    blocks = normalize_paragraphs(paras)
    chain_blocks = [b for b in blocks if b['type'] == 'chain']
    assert len(chain_blocks) == 1, f"Expected 1 chain block, got {len(chain_blocks)}"
    chain = chain_blocks[0]
    assert '↓' not in chain['text'], "Chain text must not contain ↓"
    for part in parts:
        assert part in chain['text']


def test_normalize_chain_no_arrow_chars():
    """Chain text must contain no → ↓ · characters."""
    paras = [
        ('Normal', 'Первый шаг'),
        ('Normal', '↓'),
        ('Normal', 'Второй шаг'),
    ]
    blocks = normalize_paragraphs(paras)
    for blk in blocks:
        for ch in ('→', '↓', '·'):
            assert ch not in blk['text'] or blk['type'] not in ('chain',), \
                f"Forbidden char {ch!r} in chain block text"


# ---------------------------------------------------------------------------
# Slug stability
# ---------------------------------------------------------------------------

def test_slug_stability():
    """Same input → same slug always."""
    text = "Глава 1. Зверь внутри нас"
    s1 = cyrillic_slug(text)
    s2 = cyrillic_slug(text)
    assert s1 == s2
    assert s1.isascii()
    assert len(s1) <= 40


def test_slug_all_ascii():
    slugs = [cyrillic_slug(t) for t in ["Введение", "Глава 30", "Карта пути"]]
    for s in slugs:
        assert s.isascii(), f"Non-ASCII slug: {s}"


# ---------------------------------------------------------------------------
# Coverage assertion (HARD FAILURE)
# ---------------------------------------------------------------------------

def _make_section(blocks):
    return {'nn': '00', 'slug': 'test', 'heading': 'Test', 'blocks': blocks}


def test_coverage_fails_on_missing_spoken_form():
    """apply_section must SystemExit when flow block has no spoken form."""
    sec = _make_section([
        {'id': 1, 'global_id': 1, 'type': 'flow',
         'text': 'А → Б', 'sha1': block_sha1('А → Б'), 'pause_ms': None},
    ])
    defaults = {'flow': 'rewrite', 'chain': 'rewrite', 'prose_with_arrow': 'rewrite',
                'heading': 'skip', 'paragraph': 'read', 'stack': 'read'}
    with pytest.raises(SystemExit):
        apply_section(sec, defaults, rules={}, prose_fragments={})


def test_coverage_passes_with_spoken_form():
    sha = block_sha1('А → Б')
    sec = _make_section([
        {'id': 1, 'global_id': 1, 'type': 'flow',
         'text': 'А → Б', 'sha1': sha, 'pause_ms': None},
    ])
    defaults = {'flow': 'rewrite', 'chain': 'rewrite', 'prose_with_arrow': 'rewrite',
                'heading': 'skip', 'paragraph': 'read', 'stack': 'read'}
    lines, _, _ = apply_section(sec, defaults, rules={sha: {'spoken': 'А потом Б'}}, prose_fragments={})
    assert lines == ['А потом Б']


# ---------------------------------------------------------------------------
# Arrow assertion in output
# ---------------------------------------------------------------------------

def test_arrow_assertion_fires():
    """assert_no_arrows must SystemExit on any of → ↓ ·"""
    for ch in ('→', '↓', '·'):
        with pytest.raises(SystemExit):
            assert_no_arrows(f"clean prefix {ch} clean suffix")


def test_arrow_assertion_passes():
    assert_no_arrows("Совершенно чистый текст без стрелок и точек-буллетов")


# ---------------------------------------------------------------------------
# Fix 1: H1/H2 headings must appear in .txt output
# ---------------------------------------------------------------------------

def test_heading_emitted_in_output():
    """Heading blocks must be included in apply_section output."""
    sec = _make_section([
        {'id': 1, 'global_id': None, 'type': 'heading',
         'text': 'Глава 1. Зверь внутри нас',
         'sha1': block_sha1('Глава 1. Зверь внутри нас'),
         'pause_ms': None, 'heading_level': 1, 'pause_after_ms': 1500},
    ])
    defaults = {'heading': 'read', 'paragraph': 'read', 'flow': 'rewrite',
                'chain': 'rewrite', 'stack': 'read', 'prose_with_arrow': 'rewrite',
                'figure_caption': 'skip'}
    lines, h_count, _ = apply_section(sec, defaults, rules={}, prose_fragments={})
    assert 'Глава 1. Зверь внутри нас' in lines
    assert h_count == 1


# ---------------------------------------------------------------------------
# Fix 2: % expansion + codepoint assertion
# ---------------------------------------------------------------------------

def test_percent_expanded():
    """50% → 'пятьдесят процентов'"""
    from audiobook.text_norm import normalize_line
    result, changes = normalize_line("не на 50%. А на 100%.")
    assert '%' not in result
    assert 'пятьдесят процентов' in result
    assert 'сто процентов' in result


def test_percent_before_number_expansion():
    """Exact failing string from the book."""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("не краем ума, не на 50%. А на 100%.")
    assert '%' not in result
    assert 'пятьдесят процентов' in result


def test_codepoint_assertion_fires_on_percent():
    from audiobook.text_norm import assert_norm_chars
    with pytest.raises(SystemExit, match='NORM CODEPOINT ERROR'):
        assert_norm_chars("текст с процентом 50%", 'test_sec', 1)


def test_codepoint_assertion_fires_on_en_dash():
    from audiobook.text_norm import assert_norm_chars
    with pytest.raises(SystemExit, match='NORM CODEPOINT ERROR'):
        assert_norm_chars("два–три", 'test_sec', 1)


def test_codepoint_assertion_passes_on_clean():
    from audiobook.text_norm import assert_norm_chars
    assert_norm_chars("Это совершенно чистый текст, сто процентов / slashes — ok.", 'test', 1)


# ---------------------------------------------------------------------------
# Fix 3: en-dash normalization
# ---------------------------------------------------------------------------

def test_en_dash_replaced():
    """U+2013 en-dash → U+2014 em-dash in norm output."""
    from audiobook.text_norm import normalize_line
    result, changes = normalize_line("от двух–трёх лет")
    assert '–' not in result
    assert '—' in result
    assert any('dash' in c for c in changes)


def test_minus_sign_replaced():
    """U+2212 minus sign → U+2014 em-dash."""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("результат−ошибка")
    assert '−' not in result


# ---------------------------------------------------------------------------
# Fix 4: figure_caption skipped
# ---------------------------------------------------------------------------

def test_figure_caption_skipped():
    """Figure captions must be skipped and counted."""
    sec = _make_section([
        {'id': 1, 'global_id': None, 'type': 'figure_caption',
         'text': 'Рисунок 1. Марионетка.',
         'sha1': block_sha1('Рисунок 1. Марионетка.'),
         'pause_ms': None},
    ])
    defaults = {'heading': 'read', 'paragraph': 'read', 'flow': 'rewrite',
                'chain': 'rewrite', 'stack': 'read', 'prose_with_arrow': 'rewrite',
                'figure_caption': 'skip'}
    lines, _, fig_count = apply_section(sec, defaults, rules={}, prose_fragments={})
    assert lines == []
    assert fig_count == 1


def test_figure_caption_classification():
    """Paragraphs starting with 'Рисунок N' must be classified as figure_caption."""
    from audiobook.text_blocks import normalize_paragraphs
    paras = [('Normal', 'Рисунок 10. Внутренний Подросток — строитель масок.')]
    blocks = normalize_paragraphs(paras)
    assert blocks[0]['type'] == 'figure_caption'


# ---------------------------------------------------------------------------
# Fix 5: chapter cross-references
# ---------------------------------------------------------------------------

def test_chapter_prep_expanded():
    """'в Главе 12' → 'в двенадцатой главе'"""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("мы говорили в Главе 12.")
    assert 'двенадцатой главе' in result
    assert 'Главе 12' not in result


def test_chapter_gen_expanded():
    """'из Главы 2' → 'из второй главы'"""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("это продолжение Главы 2.")
    assert 'второй главы' in result


def test_chapter_prep_third():
    """'в Главе 3' → 'в третьей главе' (soft sign must be present)."""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("о масках в Главе 3.")
    assert 'третьей главе' in result, f"got: {result}"


# ---------------------------------------------------------------------------
# Fix 6: ordinals with suffix
# ---------------------------------------------------------------------------

def test_ordinal_suffix_fem_nom():
    """'51-я весна' → 'пятьдесят первая весна'"""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("Это моя 51-я весна.")
    assert '51-я' not in result
    assert 'пятьдесят первая' in result


def test_ordinal_suffix_masc_nom():
    """'1-й этаж' → 'первый этаж'"""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("Социальный (Подросток, 1-й этаж).")
    assert '1-й' not in result
    assert 'первый' in result


def test_ordinal_suffix_2nd():
    """'2-й этаж' → 'второй этаж'"""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("Эффективный (Взрослый, 2-й этаж).")
    assert '2-й' not in result
    assert 'второй' in result


# ---------------------------------------------------------------------------
# Fix 3 regression: numeric range expansion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected_substr", [
    ("0–1 год",        "от нуля до одного"),
    ("2–3 лет",        "от двух до трёх"),
    ("3–6 лет",        "от трёх до шести"),
    ("5–10 минут",     "от пяти до десяти"),
    ("6–8 счётов",     "от шести до восьми"),
    ("6–10 лет",       "от шести до десяти"),
    ("10–14 лет",      "от десяти до четырнадцати"),
    ("10–15 минут",    "от десяти до пятнадцати"),
    ("12–15",          "от двенадцати до пятнадцати"),
    ("1–3 года",       "от одного до трёх"),
    ("1–4",            "от одного до четырёх"),
    ("20–30 повторений", "от двадцати до тридцати"),
    ("3–5 вдохов",     "от трёх до пяти"),
    ("30–60 секунд",   "от тридцати до шестидесяти"),
    ("5–10 раз",       "от пяти до десяти"),
    ("2–3 практики",   "от двух до трёх"),
])
def test_range_expansion(raw, expected_substr):
    from audiobook.text_norm import normalize_line
    result, changes = normalize_line(raw)
    assert '–' not in result, f"en-dash survived in: {result!r}"
    assert expected_substr in result, f"expected {expected_substr!r} in {result!r}"
    assert any('range' in c for c in changes)


def test_range_no_dash_between_num_words():
    """Sanity: 'двух—трёх' pattern must never appear after normalization."""
    from audiobook.text_norm import normalize_line, assert_norm_chars
    result, _ = normalize_line("2–3 лет")
    # must not trigger the dash-between-numerals assertion
    assert_norm_chars(result, 'test', 1)  # should not raise


def test_dash_between_num_words_assertion():
    """assert_norm_chars must SystemExit on spelled-out 'двух—трёх'."""
    from audiobook.text_norm import assert_norm_chars
    with pytest.raises(SystemExit):
        assert_norm_chars("от двух—трёх лет", 'test_sec', 1)


def test_non_numeric_dash_becomes_emdash():
    """Word–word (no digits) en-dash → em-dash, not range expansion."""
    from audiobook.text_norm import normalize_line
    result, changes = normalize_line("Иван–дурак")
    assert '–' not in result
    assert '—' in result
    assert 'от' not in result


# ---------------------------------------------------------------------------
# Preposition-governed ranges: hyphenated pair, not "от…до"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # до → genitive
    ("до 2–3 лет",            "до двух-трёх"),
    # на → accusative ≈ nominative
    ("на 6–8 счётов",         "на шесть-восемь"),
    ("на 5–10 минут",         "на пять-десять"),
    # через → accusative ≈ nominative
    ("Через 20–30 повторений", "Через двадцать-тридцать"),
])
def test_prep_range_hyphenated(raw, expected):
    from audiobook.text_norm import normalize_line
    result, changes = normalize_line(raw)
    assert '–' not in result, f"en-dash survived in: {result!r}"
    assert expected in result, f"expected {expected!r} in {result!r}"
    assert 'от от' not in result and ' от ' not in result.split(expected)[0][-10:], \
        f"'от' collision in: {result!r}"


def test_prep_before_ot_assertion():
    """assert_norm_chars must SystemExit on 'до от двух до трёх'."""
    from audiobook.text_norm import assert_norm_chars
    with pytest.raises(SystemExit):
        assert_norm_chars("в раннем детстве, до от двух до трёх лет", 'test_sec', 1)


# ---------------------------------------------------------------------------
# Stage 3: chunker
# ---------------------------------------------------------------------------

import re as _re


def _ws(s: str) -> str:
    return _re.sub(r"\s+", " ", s).strip()


_CFG = {
    "model": {"name": "qwen3_tts", "seed": 42, "temperature": 0.9, "language": "ru"},
    "reference": {"path": "ref/isaev_ref.wav"},
}


def test_chunk_length_bounds():
    """Ordinary prose: every chunk within hard cap; multi-chunk paragraphs
    respect the target ceiling."""
    from audiobook.chunker import chunk_prose, CAP
    para = ("Первое предложение средней длины про маски и защиту. "
            "Второе предложение тоже про телесные ощущения и волну. "
            "Третье предложение о том, как важно замечать себя каждый день. "
            "Четвёртое предложение завершает мысль спокойно и ровно.")
    chunks = chunk_prose(para)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= CAP, f"chunk over cap: {len(c)}"


def test_no_stopword_endings():
    """No chunk ends on a bare preposition/conjunction/'не'."""
    from audiobook.chunker import chunk_prose, _ends_on_stopword
    # long sentence that a naive cap-split could break after 'в' or 'и'
    para = ("Он медленно шёл по длинной улице и думал о том что случилось вчера в "
            "маленьком городе где он вырос и куда больше не вернётся никогда "
            "потому что там его уже никто не ждёт и не помнит совсем.")
    for c in chunk_prose(para):
        assert not _ends_on_stopword(c), f"stopword ending: {c!r}"


def test_no_text_loss():
    """Concatenated chunk text equals source (whitespace-normalized)."""
    from audiobook.chunker import build_chunks
    units = [
        {"type": "heading", "text": "Глава первая", "level": 1},
        {"type": "paragraph", "text":
            "Предложение раз про телесный интеллект. Предложение два про боль. "
            "Предложение три про возвращение в тело и покой."},
        {"type": "paragraph", "text": "Короткий абзац."},
    ]
    chunks = build_chunks(units)
    src = " ".join(u["text"] for u in units)
    got = " ".join(c["text"] for c in chunks)
    assert _ws(src) == _ws(got)


def test_never_split_inside_quotes():
    """A quoted span with internal periods stays in one chunk (balanced « »)."""
    from audiobook.chunker import chunk_prose
    para = 'Он сказал: «Первое. Второе. Третье. Четвёртое» и спокойно ушёл домой.'
    for c in chunk_prose(para):
        assert c.count("«") == c.count("»"), f"quote split: {c!r}"


def test_over_cap_quoted_chunks():
    """Three real over-cap strings from the manifest must each split into
    chunks <= CAP. These were the only chunks that broke the hard cap because
    they are entirely inside «…» with no depth-0 split points."""
    from audiobook.chunker import chunk_prose, CAP

    # 03_otzyvy chunk 0002 (len=269)
    s1 = (
        "«Я прочитала сотни книг по психологии. Эта — первая, где я увидела себя целиком. "
        "Не отдельные травмы, не отдельные техники, а всю свою жизнь — от детства до "
        "сегодняшнего дня. Древо боли — это гениально. Я наконец поняла, почему реагирую "
        "так остро. И что с этим делать»."
    )
    # 03_otzyvy chunk 0004 (len=263)
    s2 = (
        "«Я мужчина, тридцать восемь лет. К психологии относился скептически. Но книга "
        "захватила с первых страниц. Метафора лифта, марионетки, Древа боли — это не "
        "\"женские штучки\", это работает. Я впервые за много лет почувствовал, что могу "
        "не просто терпеть, а выбирать»."
    )
    # 29_glava_22 chunk 0137 (len=394)
    s3 = (
        "«Спасибо тебе. Ты пытался меня защитить. Ты помогал мне выживать, когда у меня "
        "не было других инструментов. Я ценю это. Но теперь я вырос. У меня есть силы, "
        "которых не было тогда. Я могу заботиться о себе сам. Я могу дать себе то, что ты "
        "давал, — но по-настоящему, не через искажение. Ты больше не нужен мне в этом виде. "
        "Твоя энергия теперь нужна мне для жизни. Отпускаю тебя с благодарностью»."
    )
    for s in (s1, s2, s3):
        assert len(s) > CAP, f"string shorter than CAP — test data wrong: {len(s)}"
        chunks = chunk_prose(s)
        for c in chunks:
            assert len(c) <= CAP, f"over-cap chunk (len={len(c)}): {c!r}"
        # no text lost
        joined = " ".join(chunks)
        assert _ws(s) == _ws(joined), "text lost in split"


def test_determinism():
    """Same units + config → byte-identical manifest, hashes included."""
    from audiobook.chunker import build_manifest
    units = [
        {"type": "heading", "text": "Заголовок", "level": 2},
        {"type": "paragraph", "text": "Одно. Два. Три. Четыре. Пять предложений тут."},
    ]
    m1 = build_manifest(units, _CFG)
    m2 = build_manifest(units, _CFG)
    assert m1 == m2
    assert all(len(r["hash"]) == 40 for r in m1)


def test_heading_own_chunk_and_pause():
    """Heading is its own chunk with pause by level."""
    from audiobook.chunker import build_chunks
    for level, expected in [(1, 1500), (2, 900), (3, 600)]:
        units = [
            {"type": "heading", "text": "Название раздела", "level": level},
            {"type": "paragraph", "text": "Тело раздела идёт после заголовка."},
        ]
        chunks = build_chunks(units)
        assert chunks[0]["text"] == "Название раздела"
        assert chunks[0]["pause_after_ms"] == expected


def test_stack_pauses():
    """Stack lines get 500ms between, section-end override on the very last."""
    from audiobook.chunker import build_chunks
    units = [
        {"type": "stack", "text": "1. Первый шаг", "last_in_stack": False},
        {"type": "stack", "text": "2. Второй шаг", "last_in_stack": False},
        {"type": "stack", "text": "3. Третий шаг", "last_in_stack": True},
        {"type": "paragraph", "text": "Заключительный абзац раздела."},
    ]
    chunks = build_chunks(units)
    assert chunks[0]["pause_after_ms"] == 500
    assert chunks[1]["pause_after_ms"] == 500
    assert chunks[2]["pause_after_ms"] == 900  # end of stack block
    assert chunks[-1]["pause_after_ms"] == 2000  # section end


def test_alignment_survives_inserted_paragraph():
    """Inserting a paragraph mid-section: untouched chunks match by hash and are
    renamed; new chunks queue; nothing orphaned."""
    from audiobook.chunker import build_manifest, align
    base = [
        {"type": "paragraph", "text": "Первый абзац про маски."},
        {"type": "paragraph", "text": "Второй абзац про боль."},
        {"type": "paragraph", "text": "Третий абзац про покой."},
    ]
    inserted = [
        base[0],
        {"type": "paragraph", "text": "Вставленный абзац про дыхание."},
        base[1],
        base[2],
    ]
    old = build_manifest(base, _CFG)
    new = build_manifest(inserted, _CFG)
    aligned, queued, orphans = align(old, new)

    assert orphans == [], f"unexpected orphans: {orphans}"
    # the inserted paragraph's chunk(s) must be queued
    assert len(queued) >= 1
    # unchanged paragraphs carry their old identity forward (renamed, not resynth)
    carried = [c for c in aligned if "_from_id" in c]
    assert len(carried) == 3


def test_apply_wav_moves_collision_safe(tmp_path):
    """Renaming shifted wavs must not clobber; orphans move to _orphan/."""
    from audiobook.chunker import _apply_wav_moves
    cdir = tmp_path / "chunks"
    cdir.mkdir()
    (cdir / "0001.wav").write_text("a", encoding="utf-8")
    (cdir / "0002.wav").write_text("b", encoding="utf-8")
    (cdir / "0003.wav").write_text("c", encoding="utf-8")
    (cdir / "0009.wav").write_text("orphan", encoding="utf-8")
    aligned = [
        {"id": "0001", "_from_id": "0001"},   # unchanged
        {"id": "0002"},                        # queued (new, no wav yet)
        {"id": "0003", "_from_id": "0002"},   # b shifts down
        {"id": "0004", "_from_id": "0003"},   # c shifts down
    ]
    _apply_wav_moves(aligned, orphans=["0009"], chunks_dir=cdir)
    assert (cdir / "0001.wav").read_text(encoding="utf-8") == "a"
    assert (cdir / "0003.wav").read_text(encoding="utf-8") == "b"
    assert (cdir / "0004.wav").read_text(encoding="utf-8") == "c"
    assert not (cdir / "0002.wav").exists()  # slot freed for resynthesis
    assert (cdir / "_orphan" / "0009__nohash.wav").read_text(encoding="utf-8") == "orphan"


def test_sentinel_round_trip():
    """Sentinel is appended for the model and cleanly stripped back."""
    from audiobook.synth import apply_sentinel, strip_sentinel
    sent = " ."
    text = "Я тебя чувствую"
    assert apply_sentinel(text, sent) == text + sent
    assert strip_sentinel(apply_sentinel(text, sent), sent) == text


def test_sentinel_conditional():
    """Sentinel is skipped when text already ends in terminal punctuation."""
    from audiobook.synth import apply_sentinel
    sent = " ."
    # Terminal punctuation → no sentinel appended
    for terminal in ["Я тебя чувствую.", "Стоп!", "Правда?",
                     "Пауза…", "Итак:", "Далее;", "он сказал»", 'конец"']:
        result = apply_sentinel(terminal, sent)
        assert result == terminal, f"sentinel appended to terminal text: {terminal!r}"
    # No terminal punctuation → sentinel appended
    for bare in ["Заголовок главы", "Базовый навык", "Он шёл"]:
        result = apply_sentinel(bare, sent)
        assert result == bare + sent, f"sentinel missing from bare text: {bare!r}"


def test_manifest_text_has_no_sentinel():
    """Manifest stores clean text; the sentinel never leaks into it."""
    from audiobook.chunker import build_manifest
    units = [{"type": "paragraph", "text": "Обычный абзац без служебных слов."}]
    for row in build_manifest(units, _CFG):
        assert row["text"].endswith(".")


# ---------------------------------------------------------------------------
# synth: latents hash stability (layer-1, no model)
# ---------------------------------------------------------------------------

def _qwen_latents(fill: float = 0.0):
    """A Qwen voice-clone prompt in the shape synth.compute_latents returns."""
    import torch
    return {"items": [{
        "ref_code": None,
        "ref_spk_embedding": torch.full((1, 1024), fill),
        "x_vector_only_mode": True,
        "icl_mode": False,
        "ref_text": None,
    }]}


def test_latents_hash_stable():
    """latents_sha1 returns the same value for identical latents."""
    from audiobook.synth import latents_sha1
    latents = _qwen_latents()
    assert latents_sha1(latents) == latents_sha1(latents)


def test_latents_hash_round_trip(tmp_path):
    """save_latents → load_latents round-trip preserves SHA1."""
    from audiobook.synth import latents_sha1, load_latents, save_latents
    latents = _qwen_latents(0.5)
    h1 = latents_sha1(latents)
    pt_path = tmp_path / "test.latents.pt"
    save_latents(latents, pt_path)
    h2 = latents_sha1(load_latents(pt_path))
    assert h1 == h2, "latents SHA1 changed after save/load"


def test_latents_hash_differs_for_different_data():
    """Different speaker embeddings produce different hashes."""
    from audiobook.synth import latents_sha1
    assert latents_sha1(_qwen_latents(0.0)) != latents_sha1(_qwen_latents(1.0))


def test_seed_for_chunk_deterministic():
    """Per-chunk seed is a deterministic function of the chunk hash."""
    from audiobook.synth import seed_for_chunk
    h = "a" * 40
    assert seed_for_chunk(h) == seed_for_chunk(h)
    assert seed_for_chunk("0" * 40) != seed_for_chunk("f" * 40)
    assert 0 <= seed_for_chunk(h) < 2 ** 32


def test_render_section_resumes(tmp_path, monkeypatch):
    """render_section skips a chunk that is 'done' with its wav on disk, and
    synthesises only the pending one — the resumability invariant (no model)."""
    import json
    import numpy as np
    import soundfile as sf
    import audiobook.synth as synth

    sec = tmp_path / "03_test"
    chunks = sec / "chunks"
    chunks.mkdir(parents=True)
    sf.write(str(chunks / "0001.wav"), np.zeros(2400, dtype=np.float32), 24000, subtype="PCM_16")
    rows = [
        {"id": "0001", "n": 1, "text": "Готовый чанк.", "hash": "a" * 40, "seed": 42,
         "pause_after_ms": 350, "status": "done", "locked": False, "duration_ms": 100},
        {"id": "0002", "n": 2, "text": "Новый чанк", "hash": "b" * 40, "seed": 42,
         "pause_after_ms": 900, "status": "pending", "locked": False, "duration_ms": None},
    ]
    (sec / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    calls = []

    class FakeEngine:
        def synth(self, text, seed):
            calls.append((text, seed))
            return np.full(4800, 0.1, dtype=np.float32)

    cfg = {"model": {"temperature": 0.9, "language": "ru", "sentinel": " ."}}
    synthesised, skipped, timed_out, synth_audio_s = synth.render_section(FakeEngine(), sec, cfg)

    assert (synthesised, skipped, timed_out) == (1, 1, 0)
    assert abs(synth_audio_s - 0.2) < 1e-6  # one 4800-sample chunk @ 24 kHz
    # only the pending chunk hit the model, with sentinel applied and seed-from-hash
    assert calls == [("Новый чанк .", synth.seed_for_chunk("b" * 40))]
    assert (chunks / "0002.wav").exists()
    updated = {r["id"]: r for r in synth._read_manifest(sec / "manifest.jsonl")}
    assert updated["0002"]["status"] == "done"
    assert updated["0002"]["duration_ms"] == 200  # 4800 / 24000 s
    assert updated["0001"]["status"] == "done"  # untouched


def test_render_section_marks_timeout_and_continues(tmp_path):
    """A chunk whose engine returns None (timed out) is marked status 'timeout'
    and the run continues to the next chunk — the batch finishes, not dies."""
    import json
    import numpy as np
    import audiobook.synth as synth

    sec = tmp_path / "05_test"
    (sec / "chunks").mkdir(parents=True)
    rows = [
        {"id": "0001", "n": 1, "text": "Зависший чанк", "hash": "a" * 40,
         "pause_after_ms": 350, "status": "pending", "locked": False, "duration_ms": None},
        {"id": "0002", "n": 2, "text": "Нормальный чанк", "hash": "b" * 40,
         "pause_after_ms": 350, "status": "pending", "locked": False, "duration_ms": None},
    ]
    (sec / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    class HangByTextEngine:
        """The first chunk times out on EVERY seed; the second always works."""
        def synth(self, text, seed):
            if text.startswith("Зависший"):
                return None
            return np.full(4800, 0.1, dtype=np.float32)

    cfg = {"model": {"temperature": 0.9, "language": "ru", "sentinel": " ."}}
    synthesised, skipped, timed_out, _ = synth.render_section(HangByTextEngine(), sec, cfg)

    assert (synthesised, skipped, timed_out) == (1, 0, 1)
    updated = {r["id"]: r for r in synth._read_manifest(sec / "manifest.jsonl")}
    assert updated["0001"]["status"] == "timeout"  # not "done", after all seeds tried
    assert updated["0001"]["duration_ms"] is None
    assert not (sec / "chunks" / "0001.wav").exists()  # nothing written for it
    assert updated["0002"]["status"] == "done"  # run continued
    assert (sec / "chunks" / "0002.wav").exists()


def test_render_section_retries_alternate_seed(tmp_path):
    """A chunk that hangs on its base seed but not on an alternate is recovered:
    render_section retries base+1, marks it done, and records the seed used."""
    import json
    import numpy as np
    import audiobook.synth as synth

    sec = tmp_path / "06_test"
    (sec / "chunks").mkdir(parents=True)
    row = {"id": "0001", "n": 1, "text": "Капризный чанк", "hash": "a" * 40,
           "pause_after_ms": 350, "status": "pending", "locked": False, "duration_ms": None}
    (sec / "manifest.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    base = synth.seed_for_chunk("a" * 40)

    class HangBaseSeedEngine:
        def synth(self, text, seed):
            if seed == base:
                return None  # sampling-triggered hang on the base seed only
            return np.full(4800, 0.1, dtype=np.float32)

    cfg = {"model": {"temperature": 0.9, "language": "ru", "sentinel": " ."}}
    synthesised, skipped, timed_out, _ = synth.render_section(HangBaseSeedEngine(), sec, cfg)

    assert (synthesised, skipped, timed_out) == (1, 0, 0)  # recovered, not a timeout
    updated = {r["id"]: r for r in synth._read_manifest(sec / "manifest.jsonl")}
    assert updated["0001"]["status"] == "done"
    assert updated["0001"]["seed"] == base + 1  # the alternate seed that worked
    assert (sec / "chunks" / "0001.wav").exists()


def test_timeout_synth_kills_and_continues():
    """A generation exceeding the timeout is killed (worker process) and returns
    None; the engine respawns so the next call still works. Uses a fake worker
    that sleeps — no model, no network."""
    from audiobook.worker import TimeoutSynth

    with TimeoutSynth({}, timeout_s=1.0, target=_sleep_worker, start_timeout_s=30) as eng:
        assert eng.synth("5", 0) is None            # 5s sleep > 1s timeout -> killed
        assert list(eng.synth("0", 0)) == [1.0, 2.0, 3.0]  # respawned, works again


def test_configure_cpu_threads_pins_count():
    """The worker pins thread count via configure_cpu_threads so its FP reduction
    order (hence generation) is reproducible and matches the audition/calibration
    environment. workers=1 → all cores; more workers → an even split, min 1."""
    import os

    import torch

    from audiobook.device import configure_cpu_threads

    phys = os.cpu_count() or 4
    saved = torch.get_num_threads()
    try:
        configure_cpu_threads(workers=1)
        assert torch.get_num_threads() == phys
        configure_cpu_threads(workers=phys * 4)  # oversubscribed → clamped to 1
        assert torch.get_num_threads() == 1
    finally:
        torch.set_num_threads(saved)


def test_max_tokens_for_text_cap_values():
    """The length cap grows with chars and stays generously above real speech.
    Values here are the ones reported for a 1-word and a 250-char chunk."""
    from audiobook.synth import max_tokens_for_text

    kw = dict(base_ms=3000, ms_per_char=100, margin=1.5)
    assert max_tokens_for_text("Отзывы", **kw) == 65      # 6 chars → ~5.4s cap
    assert max_tokens_for_text("x" * 250, **kw) == 504    # 250 chars → 42s cap
    # Monotonic in length; a 1-word cap (5.4s) still clears its real ~2.2s render.
    assert max_tokens_for_text("x" * 10, **kw) > max_tokens_for_text("x", **kw)
    assert 65 / 12 > 2.2


def test_cap_params_from_config():
    from audiobook.synth import cap_params

    assert cap_params({"render": {"cap_ms_per_char": 100}}) == {
        "base_ms": 3000, "ms_per_char": 100, "margin": 1.5,
    }
    assert cap_params({"render": {}}) is None          # absent → cap disabled
    assert cap_params({}) is None


def test_synthesize_flags_cap_saturation(monkeypatch):
    """A generation that fills the token budget raises CapExceeded (runaway); one
    that stops short returns the wav. Uses a stub model — no real weights."""
    import numpy as np

    import audiobook.synth as synth_mod
    from audiobook.synth import CapExceeded, synthesize, _CODEC_HZ, _SAMPLE_RATE

    # Skip the qwen_tts import in _dict_to_items (pulls onnxruntime); the stub
    # ignores the prompt anyway. Keeps this a pure layer-1 test.
    monkeypatch.setattr(synth_mod, "_dict_to_items", lambda latents: [])

    class StubModel:
        def __init__(self, n_samples):
            self.n = n_samples
            self.last_kw = None

        def generate_voice_clone(self, **kw):
            self.last_kw = kw
            return [np.zeros(self.n, dtype=np.float32)], _SAMPLE_RATE

    latents = {"items": []}
    mnt = 65
    cap_samples = int(mnt / _CODEC_HZ * _SAMPLE_RATE)
    # Fills the budget → runaway.
    with pytest.raises(CapExceeded):
        synthesize(StubModel(cap_samples), "т", latents, 0, 0.9, "ru", max_new_tokens=mnt)
    # Stops well short → real speech; and the cap was forwarded to the model.
    stub = StubModel(int(2.0 * _SAMPLE_RATE))
    wav = synthesize(stub, "т", latents, 0, 0.9, "ru", max_new_tokens=mnt)
    assert len(wav) == int(2.0 * _SAMPLE_RATE)
    assert stub.last_kw["max_new_tokens"] == mnt


def test_qc_normalizer_folds_representation_noise():
    """The CER normalizer folds only representation noise, applied to both sides."""
    from audiobook.qc import normalize_for_cer

    # stress marks (combining acute + RUAccent '+'), ё→е, case, punctuation
    assert normalize_for_cer("О́тзывы!") == normalize_for_cer("отзывы")
    assert normalize_for_cer("подмо+га") == normalize_for_cer("подмога")
    assert normalize_for_cer("Ёлка, ель…") == "елка ель"
    assert normalize_for_cer("  двойные   пробелы  ") == "двойные пробелы"
    # й must NOT be folded to и (its breve is not a stress mark)
    assert normalize_for_cer("мой") != normalize_for_cer("мои")


def test_qc_cer_clean_pairs_zero(  ):
    """Zero false positives: clean transcript vs text is 0.0 CER even with the
    kinds of surface differences whisper produces (case, punctuation, ё, stress)."""
    from audiobook.qc import cer

    assert cer("Отзывы", "отзывы") == 0.0
    assert cer("Я наконец поняла, почему.", "я наконец поняла почему") == 0.0
    assert cer("Всё хорошо", "все хорошо") == 0.0
    # a real error registers, and is a fraction of the reference length
    e = cer("привет мир", "привет мор")
    assert 0.0 < e < 0.2


def test_qc_cer_unifies_number_forms():
    """Digit vs word representation of a number must not fail a chunk: whisper's
    '50%' / '13' align with the text's 'пятьдесят процентов' / 'тринадцать'."""
    from audiobook.qc import cer, normalize_for_cer

    assert "пятьдесят процентов" in normalize_for_cer("на 50%")
    assert cer("на пятьдесят процентов", "на 50%") == 0.0
    assert cer("сто процентов", "100%") == 0.0
    assert cer("тринадцать глава", "13 глава") == 0.0


def test_qc_cer_symmetric_on_stress():
    """Reference carrying a respelling-style acute still scores 0 vs plain hyp."""
    from audiobook.qc import cer

    assert cer("сло́во", "слово") == 0.0


def test_synth_offline_no_download(monkeypatch, tmp_path):
    """HF_HUB_OFFLINE=1 + empty models/ → load_model raises a clear
    FileNotFoundError from the local-snapshot lookup, before any network or
    qwen_tts import. Guards the offline load-by-path fix."""
    import audiobook.synth as synth_mod
    monkeypatch.setattr(synth_mod, "_model", None)
    from audiobook import paths
    monkeypatch.setattr(paths, "MODELS", tmp_path / "models")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(FileNotFoundError, match="Qwen3-TTS weights missing"):
        synth_mod.load_model("cpu")


# ---------------------------------------------------------------------------
# Pronunciation dictionary (stress fixes)
# ---------------------------------------------------------------------------

def test_pronounce_applies_whole_word():
    """respell substitutes exact source strings, whole-word only."""
    from audiobook.pronounce import respell
    table = {"Отзывы": "О́тзывы"}
    assert respell("Отзывы", table) == "О́тзывы"
    assert respell("Отзывы клиентов", table) == "О́тзывы клиентов"
    # substring inside a longer word is left alone
    assert respell("Переотзывы", table) == "Переотзывы"
    # nothing to match → identity (this is what keeps the hash stable)
    assert respell("Другой текст", table) == "Другой текст"


def test_pronounce_longest_key_first():
    """An overlapping longer key wins over its substring."""
    from audiobook.pronounce import respell
    table = {"Марс": "Ма́рс", "Марсель": "Марсе́ль"}
    assert respell("город Марсель", table) == "город Марсе́ль"


def test_pronounce_missing_file_is_empty(tmp_path):
    from audiobook.pronounce import load_table
    assert load_table(tmp_path / "nope.yaml") == {}


def test_pronounce_changes_chunk_hash():
    """A firing dictionary entry changes the chunk hash; an edit changes it
    again — the re-queue signal the whole feature rests on."""
    from audiobook.chunker import chunk_hash
    args = ("qwen3_tts", 42, 0.9, "ru", "lat")
    base = chunk_hash("Отзывы", *args)                       # no dictionary
    fix_a = chunk_hash("Отзывы", *args, synth_text="О́тзывы")  # entry A fires
    fix_b = chunk_hash("Отзывы", *args, synth_text="Оотзывы")  # entry B fires
    assert fix_a != base, "firing entry must change the hash"
    assert fix_b != fix_a, "editing the entry must change the hash again"


def test_pronounce_untouched_chunk_keeps_hash():
    """A chunk the dictionary does not touch keeps its pre-dictionary hash, so
    existing cached audio is not invalidated (surgical re-queue)."""
    from audiobook.chunker import chunk_hash
    args = ("qwen3_tts", 42, 0.9, "ru", "lat")
    base = chunk_hash("Обычный текст", *args)
    same = chunk_hash("Обычный текст", *args, synth_text="Обычный текст")
    assert same == base


def test_bare_range_still_expands():
    """Range without preceding preposition still → 'от N до M'."""
    from audiobook.text_norm import normalize_line
    result, _ = normalize_line("занимает 3–6 лет")
    assert 'от трёх до шести' in result


# ---------------------------------------------------------------------------
# Defect 2: accent hard failure when weights missing (layer-2 condition)
# ---------------------------------------------------------------------------

def test_accent_fails_without_weights(monkeypatch, tmp_path):
    """accent_lines must raise FileNotFoundError (not silently return unaccented text)
    when models/nn or models/dictionary are absent."""
    import audiobook.accent as accent_mod
    from audiobook import paths

    # Point MODELS at an empty tmp dir — weights do not exist there
    monkeypatch.setattr(paths, 'MODELS', tmp_path / 'models')
    accent_mod._accentizer = None  # reset cached instance

    with pytest.raises(FileNotFoundError, match='models/nn'):
        accent_mod.accent_lines(["тестовая строка"])


def test_accent_no_partial_file_on_failure(monkeypatch, tmp_path):
    """No .acc.txt must be written when accent_lines raises."""
    import audiobook.accent as accent_mod
    from audiobook import paths

    fake_models = tmp_path / 'models'
    monkeypatch.setattr(paths, 'MODELS', fake_models)
    monkeypatch.setattr(paths, 'TEXT', tmp_path / 'text')
    accent_mod._accentizer = None

    # Create a small norm.txt (above skip threshold) to force a write attempt
    text_dir = tmp_path / 'text'
    text_dir.mkdir()
    norm = text_dir / '03_test.norm.txt'
    norm.write_text("Тестовая строка без ударений.\n", encoding='utf-8')

    with pytest.raises(FileNotFoundError):
        accent_mod.main()

    acc = text_dir / '03_test.acc.txt'
    assert not acc.exists(), f"partial .acc.txt was written despite failure: {acc}"


# ---------------------------------------------------------------------------
# Defect N: chapter heading word order in _expand_chapter_refs
# ---------------------------------------------------------------------------

def test_chapter_heading_word_order():
    """'Глава N.' at line start → 'Глава первая.' (noun first, capital).
    In-text cross-references keep ordinal-first form."""
    from audiobook.text_norm import normalize_line

    # Heading titles: word order must be "Глава <ordinal>"
    assert normalize_line("Глава 1. Зверь внутри нас")[0].startswith("Глава первая.")
    assert normalize_line("Глава 12. Первый навык")[0].startswith("Глава двенадцатая.")
    assert normalize_line("Глава 21. Встреча с Тенью")[0].startswith("Глава двадцать первая.")
    assert normalize_line("Глава 35. Главное, что нужно помнить")[0].startswith("Глава тридцать пятая.")

    # In-text cross-references: inflected, ordinal first
    normed, _ = normalize_line("Смотри главу 5.")
    assert "пятую главу" in normed
    normed, _ = normalize_line("Подробнее в Главе 12.")
    assert "двенадцатой главе" in normed
    normed, _ = normalize_line("Из Главы 3 следует")
    assert "третьей главы" in normed


# ---------------------------------------------------------------------------
# Defect 3: empty section skip in text_norm and accent
# ---------------------------------------------------------------------------

def test_text_norm_skips_empty_section(tmp_path, monkeypatch):
    """text_norm.main() skips .txt files under 50 bytes."""
    from audiobook import paths
    import audiobook.text_norm as norm_mod

    monkeypatch.setattr(paths, 'TEXT', tmp_path)
    (tmp_path / '00_section.txt').write_text('', encoding='utf-8')
    (tmp_path / '02_soderzhanie.txt').write_text('Содержание\n', encoding='utf-8')
    (tmp_path / '03_real.txt').write_text('Реальный контент раздела, больше пятидесяти байт.\n', encoding='utf-8')

    norm_mod.main()

    assert not (tmp_path / '00_section.norm.txt').exists(), "00 must be skipped"
    assert not (tmp_path / '02_soderzhanie.norm.txt').exists(), "02 must be skipped"
    assert (tmp_path / '03_real.norm.txt').exists(), "03 must be processed"


# ---------------------------------------------------------------------------
# enum_splits and chunk_fragments
# ---------------------------------------------------------------------------

from audiobook.synth import chunk_fragments, enum_splits


def test_enum_splits_fires_on_short_items():
    parts = enum_splits("Тяжесть, ком, напряжение.")
    assert parts == ["Тяжесть", "ком", "напряжение."]


def test_enum_splits_fires_after_dash_reset():
    parts = enum_splits("Где ты находишься — в голове, в прошлом, в будущем?")
    assert parts == ["Где ты находишься — в голове", "в прошлом", "в будущем?"]


def test_enum_splits_blocks_subordinate():
    # "где" triggers _SUBORD_ANYWHERE on the right segment
    assert enum_splits("место, где он был") == ["место, где он был"]


def test_enum_splits_blocks_long_item():
    assert enum_splits("очень длинный текст слева, справа") == ["очень длинный текст слева, справа"]


def test_enum_splits_byline_guard():
    # "Анна, сорок два года, Москва" — last word of middle part = "года"
    assert enum_splits("Анна, сорок два года, Москва") == ["Анна, сорок два года, Москва"]


def test_chunk_fragments_no_enum_pause():
    cfg = {"pauses_ms": {}}
    frags = chunk_fragments("Тяжесть, ком, напряжение.", cfg)
    assert frags == [("Тяжесть, ком, напряжение.", 0, False)]


def test_chunk_fragments_with_enum_pause():
    cfg = {"pauses_ms": {"enum_pause_ms": 250, "sentence": 350}}
    frags = chunk_fragments("Тяжесть, ком, напряжение.", cfg)
    assert [f for f, _, _ in frags] == ["Тяжесть", "ком", "напряжение."]
    assert [p for _, p, _ in frags] == [250, 250, 0]
    assert all(ie for _, _, ie in frags)


# ---------------------------------------------------------------------------
# open_end option in text_prep
# ---------------------------------------------------------------------------

from audiobook.voicecfg import prepare_text as _pt


def _cfg(open_end=None, ensure_terminal=False, strip_quotes=False):
    tp = {}
    if ensure_terminal:
        tp["ensure_terminal"] = True
    if strip_quotes:
        tp["strip_quotes"] = True
    if open_end is not None:
        tp["open_end"] = open_end
    return {"text_prep": tp} if tp else {}


# prepare_text signature: (text, config, open_end=False)

def test_open_end_keep_same_as_ensure_terminal():
    """open_end=True, mode=keep → same as ensure_terminal (adds '.')."""
    text = "Он шёл,"
    assert _pt(text, _cfg(ensure_terminal=True), open_end=True) == "Он шёл,."
    # explicit keep = same
    assert _pt(text, _cfg(ensure_terminal=True, open_end="keep"), open_end=True) == "Он шёл,."


def test_open_end_none_no_dot():
    """open_end=True, mode=none → no terminal added, even with ensure_terminal."""
    assert _pt("Он шёл,", _cfg(ensure_terminal=True, open_end="none"), open_end=True) == "Он шёл,"


def test_open_end_ellipsis_comma():
    """open_end=True, mode=ellipsis, trailing comma → replaced with …"""
    assert _pt("Он шёл,", _cfg(open_end="ellipsis"), open_end=True) == "Он шёл…"


def test_open_end_ellipsis_emdash():
    """open_end=True, mode=ellipsis, trailing em-dash → replaced with …"""
    assert _pt("Он шёл—", _cfg(open_end="ellipsis"), open_end=True) == "Он шёл…"


def test_open_end_false_modes_do_not_fire():
    """open_end=False: none/ellipsis modes must NOT fire; ensure_terminal still applies."""
    text = "Введение"  # heading without terminal — not a continuation chunk
    assert _pt(text, _cfg(ensure_terminal=True, open_end="none"), open_end=False) == "Введение."
    assert _pt(text, _cfg(ensure_terminal=True, open_end="ellipsis"), open_end=False) == "Введение."


def test_open_end_default_no_change():
    """With no text_prep at all, output equals input regardless of open_end flag."""
    assert _pt("Он шёл,", {}) == "Он шёл,"
    assert _pt("Он шёл,", {}, open_end=True) == "Он шёл,"


# ---------------------------------------------------------------------------
# open_end / cont flags in manifest
# ---------------------------------------------------------------------------

from audiobook.chunker import build_manifest, build_chunks


def _minimal_config():
    """Minimal config that passes build_manifest (no models needed)."""
    return {
        "model": {"name": "test", "seed": 42, "temperature": 0.7, "language": "ru"},
        "pauses_ms": {"sentence": 350, "paragraph": 700},
        "ref": {"path": "ref/dummy.pt"},
    }


def _units_from_texts(texts):
    return [{"type": "text", "text": t} for t in texts]


def _manifest_monkeypatches(monkeypatch):
    import audiobook.chunker as _chunker
    import audiobook.voicecfg as _vc
    import audiobook.leadin as _leadin
    import audiobook.pronounce as _pron
    monkeypatch.setattr(_vc, "prepare_text", lambda text, cfg, open_end=False: text)
    monkeypatch.setattr(_leadin, "phrase_for", lambda *a, **kw: None)
    monkeypatch.setattr(_pron, "respell", lambda text, table: text)
    monkeypatch.setattr(_pron, "load_table", lambda: {})
    monkeypatch.setattr(_chunker, "latents_hash", lambda cfg: "FAKE")


def test_manifest_open_end_flag(monkeypatch):
    """Chunk ending without terminal → open_end=True; next chunk → cont=True."""
    _manifest_monkeypatches(monkeypatch)
    cfg = _minimal_config()
    rows = build_manifest(_units_from_texts(["Он шёл,", "пока не устал."]), cfg)
    assert len(rows) == 2
    assert rows[0]["open_end"] is True
    assert rows[0]["cont"] is False
    assert rows[1]["open_end"] is False
    assert rows[1]["cont"] is True


def test_manifest_open_end_not_in_hash(monkeypatch):
    """open_end and cont are metadata only — hash is independent of their values."""
    _manifest_monkeypatches(monkeypatch)
    from audiobook.chunker import chunk_hash
    cfg = _minimal_config()
    rows = build_manifest(_units_from_texts(["Привет."]), cfg)
    # text ends with '.', so open_end=False → prepare_text gets open_end=False → no change
    expected = chunk_hash(rows[0]["text"], "test", 42, 0.7, "ru", "FAKE")
    assert rows[0]["hash"] == expected


# ---------------------------------------------------------------------------
# Hash/synth_text consistency: chunker hash == prepare_synth_text output
# ---------------------------------------------------------------------------

def test_synth_text_consistent_with_hash_keep(monkeypatch):
    """Hash built by chunker matches what prepare_synth_text returns (open_end=True, keep)."""
    import audiobook.chunker as _chunker
    import audiobook.leadin as _leadin
    import audiobook.pronounce as _pron
    from audiobook.synth import prepare_synth_text
    from audiobook.chunker import chunk_hash

    monkeypatch.setattr(_leadin, "phrase_for", lambda *a, **kw: None)
    monkeypatch.setattr(_pron, "respell", lambda text, table: text)
    monkeypatch.setattr(_pron, "load_table", lambda: {})
    monkeypatch.setattr(_chunker, "latents_hash", lambda cfg: "FAKE")

    # open_end=True, mode=keep (default) + ensure_terminal: adds "."
    cfg = {**_minimal_config(), "text_prep": {"ensure_terminal": True}}
    rows = build_manifest(_units_from_texts(["Он шёл,"]), cfg)
    row = rows[0]
    assert row["open_end"] is True
    synth_text, _ = prepare_synth_text(row["text"], cfg, {}, "SENTINEL",
                                        open_end=row["open_end"])
    # hash field was built from the same synth_text (minus sentinel)
    prepared_text = synth_text.replace("\x00SENTINEL", "")
    expected = chunk_hash(row["text"], "test", 42, 0.7, "ru", "FAKE",
                          prepared_text if prepared_text != row["text"] else None)
    assert row["hash"] == expected


def test_hash_changes_for_open_end_chunk_with_none(monkeypatch):
    """open_end: none on an open_end chunk changes synth_text → different hash."""
    import audiobook.chunker as _chunker
    import audiobook.leadin as _leadin
    import audiobook.pronounce as _pron
    from audiobook.chunker import chunk_hash

    monkeypatch.setattr(_leadin, "phrase_for", lambda *a, **kw: None)
    monkeypatch.setattr(_pron, "respell", lambda text, table: text)
    monkeypatch.setattr(_pron, "load_table", lambda: {})
    monkeypatch.setattr(_chunker, "latents_hash", lambda cfg: "FAKE")

    text = "Он шёл,"
    cfg_keep = {**_minimal_config(), "text_prep": {"ensure_terminal": True}}
    cfg_none = {**_minimal_config(), "text_prep": {"ensure_terminal": True, "open_end": "none"}}
    rows_keep = build_manifest(_units_from_texts([text]), cfg_keep)
    rows_none = build_manifest(_units_from_texts([text]), cfg_none)
    # keep → "Он шёл,." in synth_text; none → "Он шёл," — hashes must differ
    assert rows_keep[0]["hash"] != rows_none[0]["hash"]


def test_hash_unchanged_for_non_open_end_chunk_with_none(monkeypatch):
    """open_end: none does NOT change hash of a chunk that is NOT open_end."""
    import audiobook.chunker as _chunker
    import audiobook.leadin as _leadin
    import audiobook.pronounce as _pron

    monkeypatch.setattr(_leadin, "phrase_for", lambda *a, **kw: None)
    monkeypatch.setattr(_pron, "respell", lambda text, table: text)
    monkeypatch.setattr(_pron, "load_table", lambda: {})
    monkeypatch.setattr(_chunker, "latents_hash", lambda cfg: "FAKE")

    text = "Он понял."  # has terminal → open_end=False
    cfg_base = {**_minimal_config(), "text_prep": {"ensure_terminal": True}}
    cfg_none = {**_minimal_config(), "text_prep": {"ensure_terminal": True, "open_end": "none"}}
    rows_base = build_manifest(_units_from_texts([text]), cfg_base)
    rows_none = build_manifest(_units_from_texts([text]), cfg_none)
    assert rows_base[0]["hash"] == rows_none[0]["hash"]


def test_heading_chunks_open_end_false(monkeypatch):
    """Heading chunks get open_end=False even without terminal punctuation.
    With open_end: none/ellipsis their hash must not change."""
    import audiobook.chunker as _chunker
    import audiobook.leadin as _leadin
    import audiobook.pronounce as _pron

    monkeypatch.setattr(_leadin, "phrase_for", lambda *a, **kw: None)
    monkeypatch.setattr(_pron, "respell", lambda text, table: text)
    monkeypatch.setattr(_pron, "load_table", lambda: {})
    monkeypatch.setattr(_chunker, "latents_hash", lambda cfg: "FAKE")

    # heading units (no terminal punctuation) — build_manifest must set open_end=False
    units = [{"type": "heading", "text": "Введение", "level": 1}]
    cfg_base = {**_minimal_config(), "text_prep": {"ensure_terminal": True}}
    rows = build_manifest(units, cfg_base)
    assert rows[0]["open_end"] is False

    # hash must be unchanged with none/ellipsis modes
    for mode in ("none", "ellipsis"):
        cfg_mode = {**_minimal_config(), "text_prep": {"ensure_terminal": True, "open_end": mode}}
        rows_mode = build_manifest(units, cfg_mode)
        assert rows[0]["hash"] == rows_mode[0]["hash"], (
            f"open_end: {mode} changed hash of a heading chunk"
        )
