---
id: G06
title: одна глава целиком — глава 23, «Шаг один.» ×36 (≈3 ч)
status: todo
owner:
machine: gamebox
depends_on: [G05b, решение человека по temperature]
---
## Зачем
Проверка исправленной перечанковки на 36 повторах «Шаг один.», пауз после «Шаг N.»,
стабильности 2 воркеров на ~3 ч. Рендер с config.yaml (уже с выбранной temperature).

## Правила
Те же, что в G04.

## Шаг 0
Как в G04, плюс `export S=30_glava_23_karta_istseleniya_poshagovaya_i`

## Шаг 1. Очередь — одна команда
```
./run.sh queue section $S
./run.sh queue list
nohup ./run.sh queue run > out/G06.log 2>&1 &
```
Проверять изредка: `./run.sh queue list`, `tail -3 out/G06.log`, `free -g`.
Упало — не перезапускать, отчёт.

## Шаг 2. На Mac
`section.mp3` → `~/Downloads/audiobook/G06/glava_23.mp3`, плюс `section.suspects.tsv`.

## Отчёт
queue list; из логов: chunk (queued/orphaned), synth (synthesised/timeout/wall/RTF),
qc (recovered/manual/suspect/takes/replaced + строки MANUAL и take), master (LUFS, peak), первая строка suspects;
пик памяти. `status: review`.
