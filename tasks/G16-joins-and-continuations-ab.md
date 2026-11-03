---
id: G16
title: стыки главы 13 + A/B продолжений фраз (без рендера книги)
status: todo
owner:
agent: claude-code
machine: gamebox
order: 3
depends_on: [T10, T11]
---
## Зачем
Откалибровать пороги `joins` и дать человеку на слух варианты из T10.

## Правила
Те же, что в G04. `AUDIOBOOK_CONFIG=` — только перед одной командой, на копии.

## Шаги
Шаг 0 как в G04. Затем:
1. `./run.sh joins --section <секция главы 13>` — вывод дословно.
2. Копии конфига: `open_end: none`, `open_end: ellipsis`, `continuations: context`.
   Для каждой — `AUDIOBOOK_CONFIG=<копия> ./run.sh impact` (дословно).
3. `passage` по отрывкам главы 13 с `cont`/`open_end`-чанками: база и каждая копия.
4. `joins` на отрывках базы и копий — сравнить флаги.
5. Привезти на Mac (`scripts/mac/fetch_results.sh`) и написать пути к mp3.

## Отчёт
