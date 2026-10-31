---
id: G05b
title: проверка «лучший из 3 дублей» на главе 13 (≈40 мин)
status: review
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -3:
f88b066 qc best-of-N takes, queue section/redo shortcuts
647a22e tasks: split night validation into small steps G04-G07
9ebb7ca tasks: G04 ready (R2 merged, queue stores config)
uv run pytest -q → 368 passed, 2 skipped
./run.sh preflight → PREFLIGHT: GREEN
```

### Шаг 1. Лог qc (09:34:12 → 09:49:42 = 15 мин)
```
  take 0019: seed 4032296171 → 4032312009  cer=0.0  min_p=1.0  (short)
  take 0022: seed 42 → 7961  cer=0.0  min_p=0.991  (short)
  take 0033: seed 42 → 15880  cer=0.0  min_p=0.499  (short)
  take 0048: seed 42 → 15880  cer=0.0  min_p=0.992  (short)
section=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  chunks=56  recovered=0  manual=0  suspect=1  takes=12  replaced=4
  suspect (ms/char > 1.8× median): ['0024']
```

### Шаг 1. Вывод suspects (первая строка)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu: подозрительных мест 11 (неуверенно 7, ловушек 4)
```

### Шаг 2. review.html страницы (4 чанка, по 3 wav каждый)
```
страница прослушки: .../takes/0019__f057f4eb31e1/review.html  (wav-файлы, 3 шт.)
страница прослушки: .../takes/0022__419e3687df20/review.html  (wav-файлы, 3 шт.)
страница прослушки: .../takes/0033__029bc3287c9a/review.html  (wav-файлы, 3 шт.)
страница прослушки: .../takes/0048__08079cc5b573/review.html  (wav-файлы, 3 шт.)
```

### Шаг 3. Результаты на Mac
```
~/Downloads/audiobook/G05b/glava_13_takes.mp3  (9.4 МБ)
~/Downloads/audiobook/2026-10-30/sections/20_.../takes/  (12 папок, 4 с review.html)
```

### Заметки агента

- `takes=12  replaced=4` — qc отрендерил дубли для 12 чанков (короткие ≤25 символов + suspect), заменил 4.
- Только чанки 0019, 0022, 0033, 0048 показаны как `take …` — у них выбранный дубль лучше оригинала по min_p.
- Чанк 0001: в папке `takes/0001__8facd4c44504/` есть 2 wav (seed 7961 и 15880), но строки `take 0001:` в логе нет — оригинал оказался лучше, замены не было. Qc выбирает автоматически по min_p; в redo (G04) человек слушал 4 варианта и мог выбрать другой.
- Suspect 0024 остался — takes механика его не трогает (он suspect по ms/char, не по short/cer).
