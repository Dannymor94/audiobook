---
id: G12
title: A/B «контекст из предыдущей фразы» на сплошном отрывке (≈1 ч)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
Проверка механики `render.leadin.context`: перед каждым чанком модель читает конец
предыдущей фразы, потом он вырезается. Цель — связная интонация на стыках вместо
«каждая фраза с нуля». Цена — около +45% времени рендера. Слушает и решает человек.
Книга не трогается: `passage` пишет только в out/passage/.

## Правила
Те же, что в G04. config.yaml не править — только копия в out/.

## Шаг 0
Как в G04.

## Шаг 1. Копия конфига
```
cp config.yaml out/cfg_ctx.yaml
```
В `out/cfg_ctx.yaml` (только в копии!) заменить строку
`    context: {mode: "off", max_chars: 60}` на `    context: {mode: "previous", max_chars: 60}`.
`diff config.yaml out/cfg_ctx.yaml` — ровно одна строка, иначе стоп.

## Шаг 2. Два отрывка (одинаковые чанки)
```
./run.sh queue add -- passage --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu --start 4 --count 16 --tag base
AUDIOBOOK_CONFIG=out/cfg_ctx.yaml ./run.sh queue add -- passage --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu --start 4 --count 16 --tag ctx
./run.sh queue list
./run.sh queue run
```
У задачи ctx в списке должно стоять `[AUDIOBOOK_CONFIG=out/cfg_ctx.yaml]`.

## Шаг 3. На Mac
`out/passage/base/passage.mp3` → `~/Downloads/audiobook/G12/A_base.mp3`,
`out/passage/ctx/passage.mp3` → `~/Downloads/audiobook/G12/B_context.mp3`, плюс оба `index.tsv`.

## Отчёт
diff, queue list, хвосты логов обеих задач (время работы каждой, строки с ошибками/повторами
обрезки, если есть), длительности mp3. `status: review`.
