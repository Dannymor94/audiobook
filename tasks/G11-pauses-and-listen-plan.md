---
id: G11
title: паузы по знаку в конце фразы + план прослушки на главе 13 (≈10 мин, без синтеза)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
1) В config.yaml включены паузы по знаку (`pauses_ms.by_end`: «?» 550, «!» 500, «…» 700,
«:» и «;» 450 мс вместо 350). Паузы не входят в хеш — перерендера нет, только пересборка.
2) Новая команда `listen-plan` — короткий файл «что послушать»: подозрительные места,
начало главы, случайная выборка; плюс страница разметки, совместимая с `fix`.

## Правила
Те же, что в G04. Ничего не рендерить (synth не запускать), не удалять, не править конфиг/словари/код.

## Шаг 0
Как в G04. `export S=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu`
Сохранить текущий mp3 для сравнения (копия, не перенос):
`cp out/sections/$S/section.mp3 out/sections/$S/section_before_by_end.mp3`

## Шаг 1. Пересборка с новыми паузами
```
./run.sh queue add -- chunk --section $S
./run.sh queue add -- assemble --section $S
./run.sh queue add -- master --section $S
./run.sh queue add -- suspects --section $S
./run.sh queue add -- sync --section $S
./run.sh queue run
./run.sh impact --section $S
```
В выводе chunk должно быть `0 queued` (паузы не вызывают перерендер). Если queued > 0 — стоп, отчёт.

## Шаг 2. План прослушки
```
./run.sh listen-plan --section $S --random 5
./run.sh review --dir out/listen --title listen_ch13
```

## Шаг 3. На Mac
- `section_before_by_end.mp3` и новый `section.mp3` → `~/Downloads/audiobook/G11/` (переименовать в `ch13_before.mp3`, `ch13_by_end.mp3`)
- `scripts/mac/fetch_results.sh gamebox --with-wav listen`

## Отчёт
Вывод всех команд дословно (chunk, master: LUFS/peak, suspects, sync, impact, listen-plan),
пути файлов на Mac. `status: review`.
