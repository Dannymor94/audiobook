---
id: G12
title: A/B «контекст из предыдущей фразы» на сплошном отрывке (≈1 ч)
status: review
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -1 → d17459d context lead-in mode (previous sentence as carrier) + passage A/B command
uv run pytest -q → 492 passed, 3 skipped
./run.sh preflight → PREFLIGHT: GREEN
```

### Шаг 1. diff config.yaml out/cfg_ctx.yaml
```
75c75
<     context: {mode: "off", max_chars: 60}
---
>     context: {mode: "previous", max_chars: 60}
```
Ровно одна строка.

### Шаг 2. queue list (после добавления)
```
01793381491203794995-666a  pending      passage --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu --start 4 --count 16 --tag base
01793381491276774362-d800  pending      passage --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu --start 4 --count 16 --tag ctx
```
У ctx — `[AUDIOBOOK_CONFIG=out/cfg_ctx.yaml]`, у base — ничего. ✓

### Шаг 2. Лог base (666a, 17:31:35 → 17:49:20 = 17 мин 45 с)
```
# config: config.yaml
20_glava_13_bazovyj_navyk_ya_tebya_chuvству: чанки 0004…0019 (16), рендер 16
→ /home/danavrata/audiobook/out/passage/base/passage.mp3  (133 с)
```

### Шаг 2. Лог ctx (d800, 17:49:20 → 18:10:06 = 20 мин 46 с)
```
# config: out/cfg_ctx.yaml
20_glava_13_bazovyj_navyk_ya_tebya_chuvству: чанки 0004…0019 (16), рендер 16
→ /home/danavrata/audiobook/out/passage/ctx/passage.mp3  (129 с)
```

### Шаг 3. Файлы на Mac
```
~/Downloads/audiobook/G12/A_base.mp3      3.1 МБ  (133.4 с = 2:13)
~/Downloads/audiobook/G12/B_context.mp3   2.9 МБ  (128.7 с = 2:09)
~/Downloads/audiobook/G12/base_index.tsv  3.2 КБ
~/Downloads/audiobook/G12/ctx_index.tsv   4.0 КБ  (больше — ctx_index содержит колонку context)
```

### Заметки агента
- Оба прохода завершены без ошибок; предупреждения `pad_token_id` и `flash-attn` — штатные.
- Время: base 17:45, ctx 20:46 → ctx на ~17% дольше (не 45%, как указано в задаче; возможно, 45% — оценка для другого размера контекста или другой секции).
- Длительность mp3: A 133 с, B 129 с — разница 4 с (~3%) укладывается в вариацию синтеза; контентный отрезок одинаковый, carrier phrase вырезается.
- ctx_index.tsv на 0.8 КБ больше base_index.tsv — видимо, хранит поле с контекстом.
- Решение (включать context mode или нет) — за пользователем по слуху.
