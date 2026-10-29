---
id: G02
title: отчёт о тексте для автора + базовая версия golden set
status: todo
owner:
machine: gamebox
depends_on: [T03, T04]
---
## Шаги
1. `./run.sh preflight` → GREEN, иначе стоп.
2. `./run.sh lint-text` → скопировать `out/lint/text_lint.md` на Mac в
   `~/Downloads/audiobook/lint/`.
3. `./run.sh golden init` (если yaml ещё нет) → `./run.sh golden render --tag base-ref_ch1`
   (≈30–60 мин) → `fetch_results.sh` или скопировать `out/golden/base-ref_ch1/golden.mp3`
   и `index.tsv`.
4. Отчёт: вывод команд дословно.

## Отчёт
