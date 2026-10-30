---
id: G10
title: проверка новых команд на главе 13 — тишина/теги, sync, impact, pace (≈15 мин, без рендера)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
Новые команды: master добавляет 1 с тишины в начале и 2 с в конце главы и теги mp3;
`sync` — карта «текст ↔ время» для читалки; `impact` — сколько перерендерит правка
настроек; `pace` — темп по главам. Проверка на уже отрендеренной главе 13. Синтеза нет.

## Правила
Те же, что в G04. Ничего не рендерить, не удалять, не править конфиг/словари/код.

## Шаг 0
Как в G04. `export S=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu`

## Шаг 1
```
./run.sh queue add -- assemble --section $S
./run.sh queue add -- master --section $S
./run.sh queue add -- suspects --section $S
./run.sh queue run
./run.sh sync --section $S
head -c 600 out/sections/$S/section.sync.json
ffprobe -v quiet -show_entries format=duration:format_tags -of default=nw=1 out/sections/$S/section.mp3
```

## Шаг 2. Impact и темп
```
./run.sh impact
AUDIOBOOK_CONFIG=out/cfg_t09.yaml ./run.sh impact
./run.sh pace
./run.sh status
```
(`out/cfg_t09.yaml` остался от G05; если его нет — пропустить вторую строку.)

## Шаг 3. На Mac
`section.mp3` → `~/Downloads/audiobook/G10/glava_13.mp3`, `section.sync.json` туда же.

## Отчёт
Весь вывод шагов 1–2 дословно. `status: review`.
