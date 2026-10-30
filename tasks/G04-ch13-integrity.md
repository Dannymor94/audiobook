---
id: G04
title: целостность главы 13 + redo 0001 (≈30 мин)
status: todo
owner:
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
Вывод chunk, вывод скрипта, из лога qc строка `section=… recovered=… manual=… suspect=…`
и все строки MANUAL (большой CER = подозрение на звук от другого текста), вывод redo,
путь к review.html на Mac. `status: review`.
