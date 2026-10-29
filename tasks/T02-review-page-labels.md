---
id: T02
title: страница прослушки + журнал решений на слух
status: doing
owner: claude-subagent
machine: code
branch: task/T02
depends_on: []
---
## Зачем
Сейчас Антон перематывает mp3 и диктует секунды. Нужна страница с кнопками на
каждый дубль/чанк и разметкой, а решения — сохраняться в git (только текст).

## Сделать
1. `./run.sh review --dir <папка с wav> [--title T] [--meta file.tsv]` → `<папка>/review.html`
   — один самодостаточный HTML (без CDN): список элементов (имя wav, подпись из meta,
   текст чанка если есть), плеер `<audio>` на каждый (src — относительный путь к wav),
   кнопки «хорошо / плохо / ?», поле комментария, кнопка «Скачать разметку» →
   `labels_<title>.json` ({"title","items":[{"file","label","comment","meta":{...}}]}).
   Работает с file:// на macOS Safari/Chrome. Разметка в localStorage (try/catch).
   Поддержать папки pron-test (n.wav + вывод с вариантами), redo (variant_XX__seed+N.wav),
   probe (chunks/*.wav + index.tsv), ref_compare.
   pron-test должен писать рядом `meta.tsv` (n, chunk, variant, take, synth_text) —
   добавь это в pron_test.py.
2. `text/labels.yaml` — журнал: записи {date, section, chunk, hash_prefix, item,
   label: ok|bad|unsure, issue (ударение|акцент|каша|темп|артефакт|другое), note}.
   `./run.sh labels import <labels_*.json> [--section S]` — дописывает в журнал
   (без дублей по file+hash). `./run.sh labels show [--section S]`.
3. Тесты слоя 1: генерация HTML (есть все элементы, относительные пути, нет внешних
   URL), импорт JSON → yaml, идемпотентность.

## Правила
CLAUDE.md проекта. Модули: `src/audiobook/review.py`, `src/audiobook/labels.py`.
В тестах — только плейсхолдерный текст, не цитаты книги.

## Отчёт
