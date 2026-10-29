---
id: T02
title: страница прослушки + журнал решений на слух
status: done
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

Сделано (ветка `task/T02`):
- `src/audiobook/review.py` — `./run.sh review --dir D [--title T] [--meta file.tsv]` → `D/review.html`.
  Один файл, inline CSS/JS, внешних URL нет, `<audio controls preload="none">` с относительным src,
  кнопки хорошо / плохо / ?, выбор «что не так», комментарий, разметка в localStorage (try/catch),
  «Скачать разметку» (Blob → `labels_<title>.json`) и «Копировать JSON» (textarea как запасной путь),
  светлая/тёмная тема, вёрстка под телефон. Виды папок определяются сами: pron-test (`n.wav` + `meta.tsv`),
  redo (`variant_XX__seed+N.wav`, секция/чанк/текст берутся из пути `out/redo/<sec>/<chunk>` и манифеста,
  если он есть), probe (`chunks/<hash16>.wav` + `index.tsv`), golden (`NN_A/NN_B.wav` парой в строку),
  ref-compare (подпапки-кандидаты, строка на чанк), иначе просто `*.wav`.
- `pron_test.py` — теперь пишет рядом `meta.tsv` (n, chunk, variant, take, start, synth_text); запись
  вынесена в `write_results()` (поведение и вывод прежние, проваленный вариант строки в meta не получает).
- `probe.py` — в `index.tsv` добавлена последняя колонка `hash` (hash16 = имя wav), чтобы страница
  сопоставляла wav со строками индекса. Старый `index.tsv` без колонки тоже читается: сопоставление
  идёт через `out/sections/*/manifest.jsonl`; чего не нашли — показывается просто по имени файла.
- `src/audiobook/labels.py` — `text/labels.yaml` (создаётся с русским заголовком-описанием полей).
  `labels import FILE [--section S]` дописывает {date, title, file, section, chunk, hash_prefix, item,
  label, issue, note}, дубли отсекаются по (title, file), повторный импорт ничего не меняет;
  неразмеченные пропускаются, комментарий без оценки = unsure. `--section` важнее секции из meta.
  `labels show [--section S]` — компактная таблица и итог ok/bad/unsure.
- CLI: `review`, `labels import`, `labels show` (в `__main__.py` перед `accept`).
- Тесты: `tests/test_review_labels.py` (23 теста), только плейсхолдерный текст, пишут в `tmp_path`.

Вывод `pytest -q`: `219 passed, 1 skipped in 11.33s`.

Заметки агента:
- Проверено: тесты, `node --check` на встроенном JS. Не проверено: работа страницы в реальном
  браузере (Safari/Chrome с file://), скачивание Blob на iOS — для этого есть «Копировать JSON».
- `labels.yaml` перезаписывается целиком при каждом импорте (через `.part` + rename), поэтому ручные
  комментарии внутри файла, кроме шапки, не сохранятся — правки лучше вносить в `note` записей.
- Дедуп по (title, file): повторная разметка того же файла на той же странице не заменяет старую запись.
  Хочется «последняя оценка побеждает» — это отдельное решение.
- Формат `index.tsv` у probe изменён (добавлена колонка); хеши чанков, кеш и манифесты не затронуты.

### Приёмка (Claude)
Слито в port-validated-settings, полный pytest зелёный. На реальном gamebox не запускалось — проверяется задачами G0x.
