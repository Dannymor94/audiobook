---
id: T01
title: preflight, очередь задач с замком, забор результатов на Mac
status: review
owner: claude-subagent
machine: code
branch: task/T01
depends_on: []
---
## Зачем
Каждая задача агенту начинается с 5–6 одинаковых строк (ресурсы, pull, тесты,
doctor) — агенты их пропускают. Задачи на gamebox не должны накладываться.
Файлы на Mac копируются вручную по одному.

## Сделать
1. `./run.sh preflight [--min-free-gb N] [--max-load X]` — построчно GREEN/RED:
   load(1м) < X (деф. 4), available RAM ≥ N (деф. 16), нет чужих тяжёлых
   процессов (whisper|transcri|llama-server|python -m audiobook synth/qc/probe…,
   кроме самого себя), git: ветка, HEAD, нет незакоммиченных отслеживаемых
   изменений, HEAD == origin/<ветка> после fetch (если сеть есть; без сети — WARN),
   `doctor` (импортом, не subprocess). Итог `PREFLIGHT: GREEN|RED`, exit 0/1.
2. Очередь: `./run.sh queue add -- <аргументы run.sh>`, `queue list`, `queue run`.
   Хранение: `out/queue/` (pending/*.json, done/*.json, logs/*.log). `queue run` —
   воркер: берёт по одному в порядке добавления, держит `fcntl.flock` на
   `out/queue/heavy.lock` (на Windows — msvcrt.locking; код переносимый), пишет лог,
   переносит в done со статусом/exit code. Второй `queue run` ждёт замок.
   Запрещённые команды в очереди (отклонять при add): `synth`/`chunk` без
   `--section`.
3. `scripts/mac/fetch_results.sh` — rsync с хоста `gamebox` (имя хоста — аргумент,
   деф. gamebox) из `~/audiobook/out/` только *.mp3, *.tsv, *.txt, *.html, *.json, *.log
   (НЕ wav), в `~/Downloads/audiobook/<YYYY-MM-DD>/`. Без удаления на источнике.
4. Тесты слоя 1: preflight-логика на подменённых значениях (load/ram/процессы как
   входные данные функции), очередь: add/list, отказ без --section, порядок,
   flock (два воркера не берут одну задачу — через multiprocessing spawn).
5. README: раздел «Gamebox: preflight и очередь».

## Правила
CLAUDE.md проекта (pathlib, encoding="utf-8", spawn, без сети в тестах, без новых
зависимостей). Модули отдельные: `src/audiobook/preflight.py`, `src/audiobook/jobqueue.py`.

## Отчёт

Сделано (ветка `task/T01`, не запушена):
- `src/audiobook/preflight.py`: чистая `evaluate(load1, available_gb, procs, git, ...)` -> список `(name, ok, hint)` (ok: True/False/None=WARN), тонкий слой чтения (`/proc/loadavg`, `/proc/meminfo`, `ps -eo pid,args`, git через subprocess). Свой PID и PID родителя из проверки чужих процессов исключаются. `doctor` вызывается импортом, его вывод показывается только при RED. Команда `preflight [--min-free-gb] [--max-load] [--no-models]`.
- `src/audiobook/jobqueue.py`: `out/queue/{pending,done,logs}`, задача `{id, created, args, status, exit_code}`; `queue add|list|run`; `add` отклоняет `synth`/`chunk` без `--section` и вложенный `queue`; `run` под эксклюзивным замком `heavy.lock` (`fcntl.flock` на POSIX, `msvcrt.locking` на Windows, импорт внутри функции), задачи запускаются как `sys.executable -m audiobook <args>` с выводом в лог; задача, оставшаяся `running` от упавшего воркера, помечается `interrupted`.
- `scripts/mac/fetch_results.sh`: rsync только mp3/tsv/txt/html/json/log, без удаления на источнике, в `~/Downloads/audiobook/<дата>/`, хост — аргумент, `--dry-run`.
- `__main__.py`: два парсера перед `accept` и диспетчеризация перед `if a.cmd == "accept":`.
- README: раздел «Gamebox: preflight и очередь».
- Тесты слоя 1: `tests/test_preflight.py`, `tests/test_jobqueue.py` (40 новых тестов; замок проверен двумя spawn-процессами с подставным runner). Итог `pytest -q`: 236 passed, 1 skipped (slow).

Заметки агента: ветка Windows (`msvcrt`) написана, но не запускалась. `preflight` на этой машине показал RED из-за RAM 7.2 ГБ и того, что ветка `task/T01` не запушена; это штатное поведение проверок. Настоящий rsync здесь не установлен, скрипт проверен с подставным rsync в PATH (аргументы и фильтры), реальную передачу с gamebox не проверял.
