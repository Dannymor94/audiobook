---
id: T12
title: phoneme-check --auto — ожидаемое ударение без ручного --expect
status: review
owner: claude-code
agent: claude-code
machine: code
branch: task/T12
order: 4
depends_on: []
---
## Зачем
`phoneme_check` (EXPERIMENTAL) требует вручную передавать `--expect`. По редукции
гласной видно ударение только на о/а/е/я; ударные и/у/ы почти не редуцируются.

## Сделать
1. `phoneme-check --section S --auto`: слова-кандидаты — из `text/stress_watch.yaml`
   и `text/pronounce.yaml`. Ожидаемое ударение: из правки в pronounce.yaml (заглавная
   гласная), иначе RUAccent по всему предложению чанка (омографы по контексту).
   RUAccent — только оффлайн из `models/`; если весов нет — работать по словарям и
   сказать об этом в выводе. В путь рендера не встраивать.
2. Для и/у/ы добавить признаки: длительность и энергия гласной относительно других
   гласных слова (по кадрам CTC). Вердикт ok / bad / unknown, балл.
3. Вывод `out/sections/S/<stem>.stress.tsv` (m:ss, слово, ожидание, вердикт, балл).
   Метка EXPERIMENTAL остаётся до проверки в G17.
`suspects.py` не трогать. Тесты слоя 1 на `analyze()` с подставными токенами;
реальная модель — только `slow`.

## Правила
CLAUDE.md проекта и раздел «Правило для новых механик» в tasks/README.md: по
умолчанию поведение не меняется, хеши чанков те же. Без новых зависимостей.
Тесты слоя 1 на плейсхолдерах во tmp_path, не на цитатах книги. Трогать только
файлы этой задачи (+ свой блок в `__main__.py`, если нужна подкоманда).

## Отчёт

Реализован режим `phoneme-check --auto --section S [--first N]` в `src/audiobook/phoneme_check.py`.

**Что сделано:**

1. **`--auto` режим** (`run_auto`):
   - Кандидаты берутся из `text/stress_watch.yaml` (омографы) + `text/pronounce.yaml`
   - Ожидаемое ударение: для pronounce.yaml — из значения (заглавная гласная);
     для stress_watch — из `text/{nn}_{slug}.acc.txt` (уже посчитан RUAccent-ом),
     иначе RUAccent на лету на тексте чанка; если весов нет — пропустить + сообщить
   - Обходит все `status=done` чанки секции, находит слова-кандидаты, запускает
     фонемную проверку; не более 5 чанков на слово (капёр как в probe)
   - Вывод: `out/sections/S/<stem>.stress.tsv` + список в консоль
   - Метка EXPERIMENTAL в выводе сохранена

2. **Новые чистые функции (слой 1):**
   - `ctc_greedy_counts` — как `ctc_greedy`, но возвращает `(tokens, n_frames)`
   - `_ctc_frame_starts` — стартовые позиции каждого токена в argmax-последовательности
   - `stress_from_pron(key, value)` — извлекает форму "запИть" из пары pronounce.yaml;
     обрабатывает нормальный случай и исключение удвоенной гласной ("Оотзывы")
   - `parse_acc_word(word_with_plus)` — парсит "зап+ить" → ("запить", 1)
     ('+' стоит перед ударной гласной в формате RUAccent)
   - `stress_from_acc_line(word, acc_line)` — ищет слово в строке acc.txt,
     возвращает "запИть" или None
   - `analyze_iyU(form, tokens, n_frames, rms_per_tok)` — расширенный analyze для и/у/ы:
     сравнивает длительность (кадры CTC) и энергию (RMS сегмента wav) ударной гласной
     с остальными гласными слова; вердикт ok/bad/unknown, балл (геометрическое среднее)

3. **PhonemeModel.phonemes_scored** — возвращает `(tokens, n_frames, rms_per_token)`,
   использует stride=320 сэмплов (wav2vec2-xlsr-53 при 16 кГц)

4. **`suspects.py` не тронут.**

5. **Тесты слоя 1** (`tests/test_phoneme_check_auto.py`, 18 тестов):
   - ctc_greedy_counts: базовый случай, бланки, пайп
   - _ctc_frame_starts: консистентность с counts
   - stress_from_pron: нормальный, хвостовое ударение, удвоенная гласная, нет ударения
   - parse_acc_word: обычный, первая гласная, нет '+', '+' перед согласной
   - stress_from_acc_line: находит, не находит, первая гласная
   - analyze_iyU: ok (длиннее+громче), bad (тише+короче), fallback для не-и/у/ы

**Все тесты:** 566 passed, 0 failed (`uv run pytest -q`, ветка task/T12).
