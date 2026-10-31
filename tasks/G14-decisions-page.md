---
id: G14
title: собрать страницу решений и привезти на Mac (≈2 мин, без синтеза)
status: review
owner: claude-sonnet-4-6
machine: gamebox
depends_on: []
---
## Зачем
Одна страница со всеми пятью сравнениями на слух (temperature, ударения, автовыбор
дублей, паузы по знаку, контекст). Человек выбирает и скачивает `decisions.json`.

## Правила
Те же, что в G04. Ничего не рендерить, не удалять, не править конфиг/словари/код.

## Шаги
```
cd ~/audiobook && git checkout port-validated-settings && git pull
uv sync --extra dev && uv run pytest -q
./run.sh decisions build
```
На Mac: `scripts/mac/fetch_results.sh gamebox --with-wav decisions`
→ открыть `~/Downloads/audiobook/<дата>/decisions/index.html`.

## Отчёт

### Шаг 0
```
git log --oneline -1 → 5dd64e5 decisions page (build) + apply decisions.json to config/pronounce
uv sync → Resolved 129 packages (no changes)
uv run pytest -q → 543 passed, 3 skipped
```

### decisions build
```
страница решений: /home/danavrata/audiobook/out/decisions/index.html
  на Mac: scripts/mac/fetch_results.sh gamebox --with-wav decisions
```

### На Mac
```
~/Downloads/audiobook/2026-10-30/decisions/index.html
  + decisions/media/ (342 файла: wav-пары temperature×45, takes, pron, mp3 паузы/контекст)
```

### Разделы страницы (h2, 6 шт.)
```
1. Temperature
2. Ударение: сознание
2. Ударение: Найди
3. Автовыбор дублей
4. Паузы по знаку в конце фразы
5. Контекст из предыдущей фразы
```

### Заметки агента
- 6 заголовков h2, нумерация 1–5 с двумя подразделами «2. Ударение» (два слова из G09).
- Страница открылась в браузере; кнопка «Скачать решения» → `decisions.json` для передачи агенту apply.
- Все 5 сравнений представлены: temperature (45 пар), два pron-test, takes (автовыбор), паузы by_end (before/after), контекст (A/B passage).
