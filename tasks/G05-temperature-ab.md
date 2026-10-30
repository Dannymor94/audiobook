---
id: G05
title: golden A/B — temperature 1.0 vs 0.9 (≈1.5 ч)
status: todo
owner:
machine: gamebox
depends_on: [G04]
---
## Зачем
Решить temperature ДО рендера глав: она входит в хеш чанка, смена потом = перерендер.

## Правила
Те же, что в G04. Дополнительно: `AUDIOBOOK_CONFIG=` писать только перед одной командой
`golden render --tag t09`, никогда через export.

## Шаг 0
Как в G04 (pull, pytest, preflight, `export AUDIOBOOK_DEVICE=cpu`).

## Шаг 1. Копия конфига
```
cp config.yaml out/cfg_t09.yaml
```
В `out/cfg_t09.yaml` (только в копии!) заменить в секции model `temperature: 1.0` на `temperature: 0.9`.
`diff config.yaml out/cfg_t09.yaml` — ровно одна строка temperature, иначе стоп.

## Шаг 2. Рендер обоих вариантов
```
./run.sh queue add -- golden render --tag base2
AUDIOBOOK_CONFIG=out/cfg_t09.yaml ./run.sh queue add -- golden render --tag t09
./run.sh queue list
```
В строке t09 должно стоять `[AUDIOBOOK_CONFIG=out/cfg_t09.yaml]`, у base2 — ничего. Иначе стоп.
```
./run.sh queue run
./run.sh golden compare base2 t09
./run.sh review --dir out/golden/compare_base2_t09 --title t_1.0_vs_0.9
```

## Шаг 3. На Mac
`scripts/mac/fetch_results.sh gamebox --with-wav golden/compare_base2_t09`

## Отчёт
diff, queue list, хвост логов обоих render, вывод compare, путь к review.html.
`status: review`. Дальше слушает человек и решает temperature — G06 без решения не начинать.
