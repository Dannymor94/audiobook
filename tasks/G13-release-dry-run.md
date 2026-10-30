---
id: G13
title: пробный выпуск на главе 13 — loudness, export mp3/m4b, отрывок (≈10 мин, без синтеза)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
Команды выпуска ещё не запускались на настоящем звуке. Проверяем на единственной
собранной главе (13): громкость, сборка книги в mp3-набор и m4b, отрывок для магазина.
Книга неполная — поэтому `--allow-missing`.

## Правила
Те же, что в G04. Synth не запускать, ничего не удалять, не править конфиг/словари/код.

## Шаг 0
Как в G04.

## Шаг 1
```
./run.sh loudness
./run.sh export --format mp3 --allow-missing
./run.sh export --format m4b --allow-missing
./run.sh export-sample --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu --start 0 --length 60
ls -la out/export out/export/mp3
ffprobe -v quiet -show_chapters -show_entries format=duration:format_tags -of default=nw=1 out/export/*.m4b
```

## Шаг 2. На Mac
`out/export/` целиком (без `_old/`) → `~/Downloads/audiobook/G13/`.
Открыть m4b в «Книгах»/плеере на Mac — видны ли название, обложка (если задана), глава.

## Отчёт
Вывод всех команд дословно. Как открылся m4b на Mac (одной строкой). `status: review`.
