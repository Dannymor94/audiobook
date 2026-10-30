---
id: G14
title: собрать страницу решений и привезти на Mac (≈2 мин, без синтеза)
status: todo
owner:
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
Вывод `decisions build` дословно, путь к странице на Mac, сколько разделов на странице
(заголовки h2). `status: review`.
