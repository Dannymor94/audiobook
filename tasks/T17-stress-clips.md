---
id: T17
title: нарезка вхождений слов риска после рендера (по таймкодам Whisper)
status: review
owner: claude-code
agent: codex
machine: code
branch: task/T17
order: 7
depends_on: []
---
## Зачем
После рендера проверять ударения не прослушкой главы, а клипами только нужных слов.
Таймкоды слов Whisper надёжны (в отличие от вердиктов по фонемам) и уже сохраняются QC.

## Сделать
Подкоманда `stress-clips --section S [--words risk|failed|watch]`:
1. Слова — из `out/stress/risk.tsv`, `out/stress/failed.tsv` или `stress_watch.yaml`
   (по умолчанию `failed` + `watch`).
2. По данным QC (таймкоды слов, найди, где лежат) — все вхождения в отрендеренных
   чанках секции. Клип: слово ±0.6 с, между клипами 0.4 с тишины.
3. Один mp3 на секцию + `index.tsv`: м:сс в клипе → секция, чанк, м:сс в главе, слово.
4. Если у чанка нет таймкодов слов — в консоль список таких чанков, не падать.
Тесты слоя 1: синтетический wav + подставные таймкоды → правильные границы клипов.

## Правила
CLAUDE.md (через AGENTS.md). Без новых зависимостей. Ничего не рендерить.
Если Codex недоступен — задачу берёт Claude Code.

## Отчёт

Реализован модуль `src/audiobook/stress_clips.py` и подкоманда `stress-clips`.
Ревью Codex Sol (CHANGES_REQUIRED) выполнено полностью.

**Раунд 3 (финальные исправления по ревью):**

**R3-1 — word_times в QC реализован.** `qc._measure` теперь возвращает
`word_times: [[w, s, e, p], ...]` для каждого слова Whisper. Одна строка добавлена
в return dict. Существующая логика (flags, CER, статусы, ре-синтез) не затронута.

**R3-2 — qc-words: повторная транскрипция без ре-синтеза.** Новая подкоманда
`./run.sh qc-words --section S` запускает только фазу Whisper для чанков без
`word_times`, не меняет `status`, `flag_words`, `cer`, `seed`, `hash`. Идемпотентна.
Нужна для чанков, отрендеренных до добавления `word_times`.

**R3-3 — нет fallback на flag_words.** `collect_hits` использует только `word_times`.
Если у некоторых чанков нет `word_times` — `stress-clips` завершается с явным
сообщением и подсказкой `./run.sh qc-words --section S`.

**R3-4 — проверка привязки word_times к hash/seed.** `r.update(_measure(...))` всегда
перезаписывает `word_times`. Тест `test_word_times_replaced_on_update` проверяет
атомарную замену. Ложные вхождения из `flag_words` исключены тестом
`test_word_in_both_sources_uses_word_times_values`.

**R3-5 — интеграционные тесты:** `tests/test_stress_clips_integration.py` (12 тестов):
уверенное слово вне watch-листа, повторные вхождения (3 клипа), слово длиннее 0.6 с,
независимость word_times/flag_words.

**R3-6 — тесты QC:** `tests/test_qc_word_times.py` (6 тестов): `_measure` возвращает
все слова (не только флаги), `run_words_only` сохраняет status/cer/flag_words,
пропускает уже заполненные чанки.

`709 passed, 5 skipped`.
