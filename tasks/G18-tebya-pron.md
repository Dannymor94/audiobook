---
id: G18
title: произношение «тебя» в главе 13
status: todo
owner:
agent: claude-code
machine: gamebox
order: 2
depends_on: [T10]
---
## Зачем
Слово «тебя» в главе 13 (базовый навык «я тебя чувствую») произносится с ударением
на первый слог — «тЕбя» вместо «тебЯ». Нужно: зафиксировать, подобрать правку через
pron-test, занести в pronounce.yaml.

## Шаг 1 — уже сделано (Mac, 2026-11-04)
Аудит показал: `phoneme-check` по секции 20_glava_13 выявил проблему. Результат записан
в `tasks/G18-tebya-pron.md`. Шаги 2–5 — на gamebox.

## Шаги (gamebox)

### Шаг 0 — preflight
```bash
git pull origin port-validated-settings
uv run pytest -q
```

### Шаг 2 — phoneme-check с наблюдателем
```bash
./run.sh phoneme-check \
  --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu \
  --auto \
  --stress-watch тебя
```
Вывод — дословно. Зафиксировать, в каких чанках «тебя» получает неверное ударение.

### Шаг 3 — pron-test: три варианта написания
```bash
./run.sh pron-test \
  --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu \
  --word тебя \
  --try тебЯ тибЯ тебя \
  --chunks 3 \
  --seeds 3
```
Вывод (список папок с результатами) — дословно.

### Шаг 4 — phoneme-check по каждой папке pron-test
Для каждой папки из шага 3:
```bash
./run.sh phoneme-check --folder <путь_из_pron-test> --stress-watch тебя
```
Вывод — дословно.

### Шаг 5 — привезти на Mac
```bash
scripts/mac/fetch_results.sh   # или аналог для gamebox
```
Написать пути к mp3 для прослушивания на Mac.

## Решение (после прослушивания)
- Если вариант найден → добавить в `text/pronounce.yaml` запись для «тебя»
  (только для этой секции или глобально — решить после прослушивания).
- Пересинтезировать затронутые чанки (`./run.sh synth --section ...`).
- Запустить `phoneme-check` повторно для подтверждения.

## Отчёт
