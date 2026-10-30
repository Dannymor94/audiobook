# Доска задач

Одна задача = один файл `Txx-*.md` (код), `Gxx-*.md` (gamebox), `Hxx-*.md` (человек).
Задачи пишутся так, чтобы их выполнил агент уровня Sonnet 4.6 без контекста чата.

## Протокол (для агентов)

1. **Взять задачу:** найди файл со `status: todo`, у которого все `depends_on` в `done`.
   Поменяй `status: doing`, `owner: <кто ты>`, закоммить `claim Txx` и запушь
   в ветку из поля `branch` (по умолчанию `port-validated-settings`).
   Если пуш отклонён (кто-то взял раньше) — `git pull --rebase`, выбери другую.
2. **Делай только то, что в задаче.** Не трогай файлы чужих задач. Не меняй
   `config.yaml` и `text/pronounce.yaml`, если задача прямо этого не говорит.
3. **Код** — в отдельной ветке `task/Txx`, от актуальной `port-validated-settings`.
   Перед сдачей: `uv run pytest -q` зелёный. Сдача = push ветки `task/Txx`,
   в файле задачи `status: review` и раздел «Отчёт».
4. **Gamebox** — выполняй шаги как написано, вывод команд копируй в «Отчёт»
   **дословно**, без своих выводов и интерпретаций. Свои наблюдения — отдельным
   абзацем «Заметки агента».
5. **Стоп-условия** из задачи — это стоп: допиши «Отчёт» с выводом и `status: blocked`.
6. `done` ставит только Антон или Claude-разработчик после проверки.

## Запрещено всегда
- пушить в `main`;
- рендер книги целиком (`synth` без `--section`, или по всем секциям) без явного
  «настройки зафиксированы, запускай» от Антона;
- удалять аудио руками (`rm` по `out/`, `cache/`) — только механизм orphan;
- придумывать команды, которых нет в `./run.sh --help`;
- коммитить `models/ ref/ cache/ out/ .env`, аудио, веса.

## Статусы
`todo` → `doing` → `review` → `done` · `blocked` (нужен человек)

## Короткие команды (вместо цепочек queue add)
- `./run.sh queue section <S> [--first N]` — вся секция: chunk → synth → qc (с дублями) → assemble → master → suspects → sync.
- `./run.sh queue redo <S> <id> [<id> …] [--candidates 3]` — кандидаты для нескольких чанков.
- `./run.sh queue run` — выполнить очередь. `./run.sh queue list` — что в ней.
- `./run.sh status` — вся книга: сделано / ждёт человека / подозрительные / звук свежий, остаток времени.
- Исправления по слуху: `./run.sh fix plan labels_*.json` → `./run.sh fix queue` → `./run.sh queue run` →
  `./run.sh fix review` (одна страница кандидатов) → `./run.sh accept <S> <id> <N>`.
- `./run.sh loudness [--section S …] [--ref-dir DIR]` — громкость глав против цели master и эталона.
- `./run.sh pron-audit` — словарь ударений: срабатывания по книге, мёртвые записи, подозрительные правки.
- Очередь как служба (переживает перезагрузку): `scripts/gamebox/README.md`.
- `./run.sh listen-plan` — что послушать: подозрения + начала глав + выборка → `out/listen/` (+ `review --dir out/listen`).
- `./run.sh impact` — сколько перерендерит правка настроек (с `AUDIOBOOK_CONFIG=копия` — без правки основного).
- `./run.sh pace`, `./run.sh sync --section S|--all`.
- Выпуск: `./run.sh credits` (модель; тексты в config `credits`), `./run.sh export --format mp3|m4b`,
  `./run.sh export-sample --section S`.
- `./run.sh passage --section S --start N --count K --tag X` — A/B сплошного отрывка (стыки, паузы, контекст);
  с `AUDIOBOOK_CONFIG=копия` — пробные настройки, книга не трогается.
- Уведомления в Telegram (опционально): `.env` с `AUDIOBOOK_TG_TOKEN`/`AUDIOBOOK_TG_CHAT`, проверка `./run.sh notify-test`
  (см. `scripts/gamebox/README.md`). Резервная копия на Mac: `scripts/mac/README.md`.
- Повторы: одинаковые чанки рендерятся один раз (`render.reuse_identical`), копии помечены `reused_from`.
- После каждой главы в очереди: `listen-plan --tag <S> --notify` → план прослушки главы в Telegram.
