---
id: T15
title: инвентарь ударений по тексту — омографы и список риска
status: review
owner: claude-code
agent: codex
machine: code
branch: task/T15
order: 6
depends_on: []
---
## Зачем
Ударения нельзя проверить автоматически по аудио (детектор фонем совпал с ухом 1 из 6,
G18). Значит, системно — через конечный список слов, проверяемых на слух один раз.
Замер: 75 722 слова, 10 305 словоформ; топ-300 форм = 55% текста, топ-1000 = 72%.

## Сделать
Подкоманда `stress-inventory` (новый модуль `src/audiobook/stress_inventory.py`),
только текст, без моделей синтеза. Вход — `text/*.norm.txt`.
1. **Омографы**: формы, у которых в словаре RUAccent больше одного варианта ударения
   (RUAccent уже в зависимостях, только оффлайн из `models/`). По каждому вхождению:
   секция, номер чанка, контекст ±40, вариант RUAccent по предложению.
   Если словаря омографов в RUAccent нет — стоп, `blocked`, описать.
2. **Список риска** `out/stress/risk.tsv`, детерминированно отсортирован:
   топ-N частых форм (N в `config.yaml`, `stress.top_n`, по умолчанию 300) + все омографы
   + формы с заглавной буквы не в начале предложения (имена) + формы из `pronounce.yaml`
   и `stress_watch.yaml`. Колонки: форма, частота, причина (top/homograph/name/dict),
   самое короткое предложение книги с этой формой (≤ 80 символов).
3. Исключить формы из `text/stress_verified.yaml` (если файла нет — создать пустой с
   описанием формата в шапке).
4. Вывод в консоль: сколько форм по каждой причине и сколько вхождений они покрывают.

## Правила
CLAUDE.md (через AGENTS.md). Без новых зависимостей. Тексты книги не менять.
Тесты слоя 1 на плейсхолдерах. Если Codex недоступен — задачу берёт Claude Code.

## Отчёт

Словарь омографов доступен: `models/dictionary/omographs.json.gz` — формат `{форма: [вариант1, вариант2, ...]}`, 
~700k форм. Задача не заблокирована.

**Реализовано:**
- `src/audiobook/stress_inventory.py` — модуль без моделей синтеза
- `./run.sh stress-inventory [--top-n N]` — подкоманда в `__main__.py`
- `text/stress_verified.yaml` — создаётся автоматически если отсутствует
- `out/stress/risk.tsv` — агрегированный список риска (форма / частота / причина / пример)
- `out/stress/omographs.tsv` — детали по каждому вхождению омографа (секция / чанк / контекст / варианты)
- Колонка `ruaccent` в omographs.tsv заполняется если `models/` доступны (контекстная разрешёнка)
- 9 тестов слоя 1 на `tmp_path`, все зелёные

**Прогон на реальном тексте книги (58 секций):**
```
stress-inventory: 1022 форм в списке риска → out/stress/risk.tsv
  top-300       300 форм    41918 вхождений
  омографы      430 форм     2673 вхождений
  имена         387 форм    26321 вхождений
  словарь        45 форм     1161 вхождений
  детали омографов → out/stress/omographs.tsv
```

**Тесты:** 676 passed, 5 skipped (полный suite).

---

### Ревью Codex Sol → CHANGES_REQUIRED, исправления (commit a3e9b5c)

**1. Детерминированность**
- Добавлен `form` как третий ключ сортировки: `(reason_priority, -freq, form)`.
- Тест `test_risk_tsv_deterministic_across_hashseeds`: запускает три отдельных процесса
  с `PYTHONHASHSEED=1,2,3`, сравнивает SHA-256 `risk.tsv` — все три одинаковы.

**2. Номера чанков**
- `_build_chunk_index(section)` загружает `out/sections/<section>/manifest.jsonl`
  и строит `word → [chunk_id, ...]` в текстовом порядке.
- При обходе текста ведётся `local_occ: Counter[str]` — счётчик вхождений каждой формы
  в пределах секции. `chunk_id = ids[local_occ[form]]` → точное соответствие.
- Если манифест отсутствует — `chunk_id = "?"` (явный индикатор, не индекс абзаца).
- Тесты: `test_chunk_id_from_manifest`, `test_chunk_id_question_mark_without_manifest`.

**3. Повторные омографы**
- Переход с `_WORD.findall` на `_WORD.finditer`: каждое вхождение получает `m.start()`
  (точную позицию символа в предложении).
- `_char_context(sent, char_pos, word_len)` вызывается с реальной позицией —
  контекст центрирован на конкретном вхождении, а не всегда на первом.
- Тесты: `test_duplicate_omograph_different_contexts`, `test_omograph_context_anchored_to_occurrence`.

**4. Ошибки RUAccent / отсутствие словаря**
- `_omograph_dict()`: если `omographs.json.gz` отсутствует — `SystemExit` с сообщением
  "Статус: blocked", ненулевой код. Молчаливый пустой dict был убран.
- Запись файлов — атомарная: `tempfile.NamedTemporaryFile` → `os.replace`.
  Если выполнение прерывается до rename — старый TSV остаётся нетронутым.
- Тесты: `test_missing_omograph_dict_exits_nonzero`, `test_failed_run_does_not_leave_partial_tsv`.

**5. Примеры длиннее 80 символов**
- `_char_context` возвращает `sent[start: start+80]` (всегда ≤80 символов).
- Когда для формы нет предложения ≤80 символов, example = сниппет ±40 вокруг
  первого вхождения (тоже ≤80). Форма всегда присутствует в сниппете.
- Тесты: `test_example_at_most_80_chars`, `test_example_always_contains_form`,
  `test_example_prefers_short_sentence`.

**Итого тестов:** 19 в файле, 686 passed, 5 skipped (полный suite).
