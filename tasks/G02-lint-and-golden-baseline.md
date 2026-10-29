---
id: G02
title: отчёт о тексте для автора + базовая версия golden set
status: done
owner: claude-sonnet-4-6
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

### preflight
```
GREEN  load(1м) 0.87 < 4
GREEN  RAM available 29.2 ГБ >= 16
GREEN  чужих тяжёлых процессов нет
GREEN  git ветка port-validated-settings
GREEN  git HEAD 9209dc5
GREEN  git: отслеживаемые файлы чистые
GREEN  git HEAD == origin/port-validated-settings
GREEN  doctor

PREFLIGHT: GREEN
```

### lint-text
```
секций: 58, слов: 76037
  Вероятно пропущена ё (слов): 58
  Вероятно пропущена ё (мест): 240
  Неоднозначные е/ё (пар): 6
  Подозрительные: редкое слово рядом с частым: 245
  Подозрительные: повтор слова подряд: 0
  Подозрительные: латиница в кириллическом слове: 0
  Подозрительные: «-ётся и»: 1
  Подозрительные: тройная буква: 0
  Для озвучки: аббревиатуры: 4
  Для озвучки: слова через дефис с капсом: 0
  Для озвучки: числа цифрами: 1
  Для озвучки: латиница: 8
отчёт: /home/danavrata/audiobook/out/lint/text_lint.md
```
Скопировано на Mac: `~/Downloads/audiobook/lint/text_lint.md`

### review (дополнительные шаги для разметки Антона)
```
страница прослушки: out/pron_test/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu_4chunks_тебя/review.html  (wav-файлы, 16 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>

страница прослушки: out/pron_test/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu_0031_Дыши/review.html  (wav-файлы, 4 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>

страница прослушки: out/pron_test/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu_0005_Заесть. Запить. Заснуть/review.html  (wav-файлы, 8 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>

страница прослушки: out/redo/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0001/review.html  (redo: кандидаты чанка, 3 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>
```

`fetch_results.sh gamebox` выполнен. Wav-файлы скопированы рядом с review.html:

| title | путь на Mac (review.html) |
|-------|--------------------------|
| tebya | `~/Downloads/audiobook/2026-10-29/pron_test/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu_4chunks_тебя/review.html` |
| dyshi | `~/Downloads/audiobook/2026-10-29/pron_test/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu_0031_Дыши/review.html` |
| zaest | `~/Downloads/audiobook/2026-10-29/pron_test/20_glava_13_bazovyj_navyk_ya_tebya_chuvству_0005_Заесть. Запить. Заснуть/review.html` |
| redo_0001 | `~/Downloads/audiobook/2026-10-29/redo/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0001/review.html` |

### golden render
```
golden base-ref_ch1: записей 45, найдено чанков 45, к синтезу 45
...
прослушка: /home/danavrata/audiobook/out/golden/base-ref_ch1/golden.mp3  оглавление: /home/danavrata/audiobook/out/golden/base-ref_ch1/index.tsv  (45 из 45)
```
Скопировано на Mac: `~/Downloads/audiobook/2026-10-29/golden/base-ref_ch1/golden.mp3`, `index.tsv`, 45 wav

### Приёмка (Claude)
lint и base-ref_ch1 готовы, страницы прослушки на Mac. Закрыто.
