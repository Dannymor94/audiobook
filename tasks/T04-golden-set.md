---
id: T04
title: постоянный набор трудных чанков (golden set) и сравнение версий
status: doing
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
