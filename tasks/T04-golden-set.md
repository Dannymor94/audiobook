---
id: T04
title: постоянный набор трудных чанков (golden set) и сравнение версий
status: done
owner: claude-subagent
machine: code
branch: task/T04
depends_on: []
---
## Зачем
Любая правка настроек (референс, паузы, temperature, int8) сейчас проверяется
несколькими заходами. Нужен фиксированный набор и одна команда.

## Сделать
1. `text/golden_set.yaml`: список {section, match (подстрока текста чанка, т.к.
   id меняются при перечанковке), why}. Начальное наполнение — из `probe`
   (`./run.sh probe --dry-run` логика: по одному чанку на тег) + вручную:
   ch13 «Глава тринадцатая.», «Я тебя чувствую», чанк с «Заесть», «Шаг первый.»,
   чанк с «Дыши». Генерацию начального списка сделать командой
   `./run.sh golden init` (пишет yaml, не перезаписывает существующий без --force).
2. `./run.sh golden render --tag NAME [--workers 1]` — строит чанки секций в памяти
   (как probe: chunker.build_manifest текущим конфигом, без записи манифестов/кеша),
   находит чанки по match, рендерит в `out/golden/<NAME>/<hash16>.wav` (resume),
   пишет `index.tsv` и `golden.mp3`, сохраняет снимок значимых настроек
   (model, reference, temperature, chunking, text_prep, pauses) в `settings.json`.
3. `./run.sh golden compare A B` → `out/golden/compare_A_B/` с mp3 «A, пауза, B»
   по каждому элементу + index.tsv; если есть review из T02 — не зависеть от него,
   просто положить wav-пары так, чтобы `review --dir` их подхватил (имена
   `NN_A.wav`, `NN_B.wav`).
4. Тесты слоя 1 с фейковым engine (см. tests/test_port_validated.py — _FakeEngine).

## Правила
CLAUDE.md проекта. Модуль `src/audiobook/golden.py`. Переиспользуй probe.py/assemble/master.

## Отчёт

Сделано: `src/audiobook/golden.py`, команда `golden init|render|compare` в `__main__.py`,
`tests/test_golden.py` (7 тестов слоя 1, фейковый engine, `master_wav` подменён),
`text/golden_set.yaml` (сгенерирован `golden init`: 45 записей = 5 фиксированных + 40 от probe).

- `init [--force] [--max 40]`: фиксированные записи ch13 («Глава тринадцатая.», «Я тебя чувствую»,
  «Заесть», «Шаг первый.», «Дыши») + `probe.scan/select`; match для probe-записей — первые ~48
  символов текста чанка (по границе слова). Без `--force` существующий файл не трогает (код 1).
- `render --tag NAME [--workers 1]`: чанки секций строятся в памяти (`build_manifest` текущим
  конфигом), берётся первый чанк с match; wav float в `out/golden/NAME/<hash16>.wav` (атомарно,
  resume по существованию), `index.tsv`, `golden.mp3` (паузы 1 с), `settings.json`. Цикл вынесен в
  `render_items(..., engine)` — для тестов engine подставляется. Упавший чанк не кешируется, код 1.
- `compare A B`: пары `NN_A.wav`/`NN_B.wav`, `compare.mp3` (A, 0.6 с, B, 1.5 с), `index.tsv`;
  записи без wav в одном из тегов пропускаются с предупреждением.

Заметки агента:
- Пары A/B сопоставляются по (section, match), а не по hash (он разный при смене настроек).
  Для этого в `settings.json` добавлен список `entries` (n, section, match, why, hash16) — это сверх
  ТЗ; в `settings.json` также попал `leadin`, т.к. влияет на звук.
- `index.tsv` render: n — порядковый номер среди найденных чанков, не позиция в yaml.
- Проверено: `pytest -q` — 203 passed, 1 skipped; `golden init` на реальном тексте отработал, все 45
  записей находят чанк (только чанкинг, без синтеза). Реальный `render` с моделью и ffmpeg НЕ запускался.
- В yaml попал probe-чанк с e-mail автора из книги (`E-mail: ...`) — тег latin; при желании убрать вручную.
- Файл `text/golden_set.yaml` лежит в `text/`, где уже весь текст книги; в тестах только плейсхолдеры.

### Приёмка (Claude)
Слито в port-validated-settings, полный pytest зелёный. На реальном gamebox не запускалось — проверяется задачами G0x.
