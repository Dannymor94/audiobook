---
id: G05
title: golden A/B — temperature 1.0 vs 0.9 (≈1.5 ч)
status: done
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -1 → 647a22e tasks: split night validation into small steps G04-G07
uv run pytest -q → 354 passed, 2 skipped in 6.38s
./run.sh preflight → PREFLIGHT: GREEN
```

### Шаг 1. diff config.yaml out/cfg_t09.yaml
```
16c16
<   temperature: 1.0               # выбрано на слух: плавнее интонация; цена ~2x RTF из-за разгонов
---
>   temperature: 0.9               # выбрано на слух: плавнее интонация; цена ~2x RTF из-за разгонов
```
Ровно одна строка.

### Шаг 2. queue list (после добавления задач)
```
01793347224311190334-2beb  pending      golden render --tag base2
01793347224376549165-a7be  pending      golden render --tag t09
```
У base2 — нет конфига, у t09 — `[AUDIOBOOK_CONFIG=out/cfg_t09.yaml]`. ✓

### Шаг 2. Хвост логов render

**base2** (08:00:27 → 08:41:27 = 41 мин, 45 из 45):
```
golden base2: записей 45, найдено чанков 45, к синтезу 45
прослушка: .../out/golden/base2/golden.mp3  оглавление: .../base2/index.tsv  (45 из 45)
```

**t09** (08:41:27 → 09:22:18 = 41 мин, 45 из 45, config: out/cfg_t09.yaml):
```
golden t09: записей 45, найдено чанков 45, к синтезу 45
прослушка: .../out/golden/t09/golden.mp3  оглавление: .../t09/index.tsv  (45 из 45)
```

### Шаг 2. golden compare
```
сравнение base2 (A) / t09 (B): 45 пар → .../compare_base2_t09/compare.mp3  (.../index.tsv)
```

### Шаг 2. review
```
страница прослушки: out/golden/compare_base2_t09/review.html  (golden: пары A/B, 90 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>
```

### Шаг 3. Результаты на Mac
```
/Users/danny/Downloads/audiobook/2026-10-30/golden/compare_base2_t09/review.html
```
90 wav-файлов (45 пар A/B) + compare.mp3 + index.tsv.

### Заметки агента

- base2 и t09: каждый рендер по 41 мин на 45 чанков — одинаковое время, что ожидаемо (RTF не зависит от temperature на CPU).
- `[AUDIOBOOK_CONFIG=out/cfg_t09.yaml]` в queue list подтверждает: t09 рендерился с копией конфига, base2 — со штатным config.yaml. `export` не использовался.
- Оба 45 из 45 — полное покрытие golden set без пропусков.
- A = 1.0, B = 0.9 в каждой паре; `review.html` открывается двойным кликом для прослушки и разметки.
