---
id: G05b
title: проверка «лучший из 3 дублей» на главе 13 (≈40 мин)
status: todo
owner:
machine: gamebox
depends_on: [G05]
---
## Зачем
Новая механика: qc сам рендерит 3 дубля коротких чанков (≤25 символов: заголовки,
«Шаг N.») и чанков с неразборчивым словом, и оставляет лучший по whisper. Все дубли
сохраняются в `out/sections/<S>/takes/`, ничего не удаляется. Хеш не меняется.
Проверяем на уже отрендеренной главе 13: сколько чанков попало, сколько заменено, сколько времени.

## Правила
Те же, что в G04 (ничего не удалять, не править конфиг/словари/код, вывод дословно).

## Шаг 0
Как в G04. `git log --oneline -3` — должен быть коммит с «takes» в сообщении.

## Шаг 1
```
export S=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu
./run.sh queue add -- qc --section $S
./run.sh queue add -- assemble --section $S
./run.sh queue add -- master --section $S
./run.sh queue add -- suspects --section $S
./run.sh queue run
```

## Шаг 2. Страница прослушки дублей
Для каждого чанка из строк `take NNNN: seed … → …` в логе qc:
`./run.sh review --dir out/sections/$S/takes/<NNNN>__<hash12> --title takes_<NNNN>`
(папку взять из `ls out/sections/$S/takes/`).

## Шаг 3. На Mac
- `section.mp3` главы 13 → `~/Downloads/audiobook/G05b/glava_13_takes.mp3`
- `scripts/mac/fetch_results.sh gamebox --with-wav sections/$S/takes`

## Отчёт
Из лога qc: строка `section=… takes=… replaced=…`, все строки `take …`, время работы qc
(начало/конец из `./run.sh queue list` или лога). Вывод suspects (первая строка).
Заметка: чанк 0001 не заблокирован — qc выбрал дубль сам; сравнить номер с выбором человека.
`status: review`.
