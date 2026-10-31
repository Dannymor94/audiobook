---
id: G04
title: целостность главы 13 + redo 0001 (≈30 мин)
status: review
owner: claude-sonnet-4-6
machine: gamebox
depends_on: []
---
## Зачем
Старая перечанковка могла положить под чанк звук от другого текста. Проверить главу 13
и заново сделать кандидатов для чанка 0001 (старые были без meta.json).

## Правила (нарушение = стоп и отчёт)
- synth/chunk только с `--section` и только для секции этой задачи.
- Ничего не удалять в `out/`, `cache/`, `ref/`. Не править `config.yaml`, `text/*.yaml`, код.
- Тяжёлое — через `./run.sh queue add -- …`, потом один `./run.sh queue run`.
- Вывод команд — дословно. Свои выводы — отдельным абзацем «Заметки агента».
- Не придумывать команды: только то, что есть в `./run.sh <cmd> --help`.

## Шаг 0. Подготовка
1. `cd ~/audiobook && git checkout port-validated-settings && git pull`; `git log --oneline -1` в отчёт.
2. `uv sync --extra dev` → `uv run pytest -q` → зелёный, иначе стоп.
3. `./run.sh preflight` → GREEN, иначе стоп.
4. `export AUDIOBOOK_DEVICE=cpu`
5. `export S=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu`

## Шаг 1. Манифест
1. `./run.sh chunk --section $S` — ожидается 0 queued.
2. Сохранить в файл `out/ch13_check.py` и запустить `uv run python out/ch13_check.py`:
   ```python
   import json, collections
   p = "out/sections/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/manifest.jsonl"
   rows = [json.loads(l) for l in open(p, encoding="utf-8")]
   print("rows", len(rows), "locked", [r["id"] for r in rows if r.get("locked")])
   print("status", collections.Counter(r.get("status") for r in rows))
   dup = collections.Counter(r["hash"] for r in rows)
   print("dup hashes", sum(1 for v in dup.values() if v > 1))
   ```

## Шаг 2. QC и кандидаты для 0001
```
./run.sh queue add -- qc --section $S
./run.sh queue add -- redo $S 0001 --candidates 4
./run.sh queue run
./run.sh review --dir out/redo/$S/0001 --title redo_0001_v2
```

## Шаг 3. На Mac
`scripts/mac/fetch_results.sh gamebox --with-wav redo/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0001`

## Отчёт

### Шаг 0
```
git log --oneline -1 → 647a22e tasks: split night validation into small steps G04-G07
uv run pytest -q → 354 passed, 2 skipped in 10.33s
./run.sh preflight → PREFLIGHT: GREEN
```

### Шаг 1. chunk
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu            56 chunks   [re-chunk: 0 queued, 0 orphaned]
──────────────────────────────────────────────────────────────────
TOTAL                                                  56 chunks  (1 sections)
```

### Шаг 1. скрипт манифеста
```
rows 56 locked ['0003']
status Counter({'done': 56})
dup hashes 0
```

### Шаг 2. QC (лог 01793346514809947902-6600.log)
```
section=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  chunks=56  recovered=0  manual=0  suspect=1
  suspect (ms/char > 1.8× median): ['0024']
```
Строк MANUAL нет — CER в норме, подозрений на звук от другого текста нет.

### Шаг 2. redo (лог 01793346520595475775-4d77.log)
```
  старые кандидаты (другой текст чанка) перенесены в _old_legacy/
redo 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0001: 'Глава тринадцатая.'
base_seed=2410468548, rendering 4 candidates (lead-in: 'Вот что важно понять.')
  variant 01  seed+100  1.44s
  variant 02  seed+200  1.58s
  variant 03  seed+300  1.98s
  variant 04  seed+400  1.32s

Listen: /home/danavrata/audiobook/out/redo/20_glava_13_bazovyj_navyk_ya_tebya_chuvству/0001
Accept: audiobook accept 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu 0001 <1..4>
```

### Шаг 2. review
```
страница прослушки: out/redo/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0001/review.html  (redo: кандидаты чанка, 4 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>
```

### Шаг 3. Результаты на Mac
```
/Users/danny/Downloads/audiobook/2026-10-30/redo/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0001/review.html
```
4 wav-кандидата: variant_01..04 + _old_legacy/ (3 старых без meta.json).

### Заметки агента

Манифест чистый: 56 строк, все `done`, 0 дублей хешей. Чанк 0003 помечен `locked` (это нормально — не аномалия). QC не нашёл ни одного MANUAL-чанка, что означает: CER у всех чанков в норме, звуковых «загрязнений» от другого текста не обнаружено. Единственный suspect — чанк 0024 по критерию ms/char, он был suspect и по итогам ch13_v4 (тот же результат).

Redo 0001: старые 3 кандидата (без meta.json) перенесены в `_old_legacy/` автоматически. Новые 4 кандидата синтезированы с правильным meta.json, длительностью 1.32–1.98 с.
