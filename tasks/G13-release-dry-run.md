---
id: G13
title: пробный выпуск на главе 13 — loudness, export mp3/m4b, отрывок (≈10 мин, без синтеза)
status: review
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -1 → 6bb85d2 tasks: G13 release dry run on chapter 13
uv run pytest -q → 534 passed, 3 skipped
./run.sh preflight → PREFLIGHT: GREEN
```

### Шаг 1. loudness
```
цель: -19.0 LUFS ±1 LU, true peak ≤ -3.0 dBTP, разброс LRA по главам ≤ 3 LU
файл                                  LUFS  TP dBTP  LRA LU  флаги
— главы —
20_glava_13_bazovyj_navyk_ya_tebya   -19.4     -3.2     4.0  

глав: 1, с флагами: 0
таблица: /home/danavrata/audiobook/out/loudness/report.tsv
```

### Шаг 1. export --format mp3 --allow-missing
```
ВНИМАНИЕ: --allow-missing, книга НЕПОЛНАЯ, пропущено 55:
  [список из 55 секций без section.mp3 или manifest.jsonl — опущен для краткости]
export mp3: 1 файлов, 0:06:55 → /home/danavrata/audiobook/out/export/mp3
```

### Шаг 1. export --format m4b --allow-missing
```
ВНИМАНИЕ: --allow-missing, книга НЕПОЛНАЯ, пропущено 55:
  [тот же список 55 секций]
export m4b: 1 глав, 0:06:55, AAC 64k моно …
  → /home/danavrata/audiobook/out/export/Ty_ne_poloman.m4b
```

### Шаг 1. export-sample
```
отрывок: 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu с 0:00:00, 60.0 с → .../out/export/sample.mp3
```

### Шаг 1. ls -la out/export out/export/mp3
```
out/export:
total 4612
-rw-rw-r--  1 danavrata danavrata 3260459 Oct 30 21:41 Ty_ne_poloman.m4b
-rw-rw-r--  1 danavrata danavrata     129 Oct 30 21:41 contents.tsv
drwxrwxr-x  2 danavrata danavrata    4096 Oct 30 21:41 mp3
-rw-rw-r--  1 danavrata danavrata 1441588 Oct 30 21:41 sample.mp3

out/export/mp3:
total 9744
-rw-rw-r-- 1 danavrata danavrata 9964249 Oct 30 20:02 01_Glava_13_Bazovyy_navyk_Ya_tebya_chuvstvuyu.mp3
-rw-rw-r-- 1 danavrata danavrata     177 Oct 30 21:41 playlist.m3u8
```

### Шаг 1. ffprobe Ty_ne_poloman.m4b
```
id=0
time_base=1/1000
start=0
start_time=0.000000
end=415090
end_time=415.090000
TAG:title=Глава 13. Базовый навык: «Я тебя чувствую»
duration=415.114218
TAG:major_brand=isom
TAG:minor_version=512
TAG:compatible_brands=isomiso2mp41
TAG:title=Ты не поломан
TAG:artist=Александр Исаев
TAG:album_artist=Александр Исаев
TAG:album=Ты не поломан
TAG:encoder=Lavf62.3.100
TAG:genre=Audiobook
```

### Шаг 2. На Mac
```
~/Downloads/audiobook/G13/export/Ty_ne_poloman.m4b    3.1 МБ
~/Downloads/audiobook/G13/export/mp3/01_Glava_13_...  9.5 МБ
~/Downloads/audiobook/G13/export/sample.mp3           1.4 МБ
~/Downloads/audiobook/G13/export/playlist.m3u8        177 Б
~/Downloads/audiobook/G13/export/contents.tsv         129 Б
```
m4b открылся в «Книгах» (macOS) — глава «Глава 13. Базовый навык: «Я тебя чувствую»» видна в навигации, название «Ты не поломан» и исполнитель «Александр Исаев» отображаются в метаданных.

### Заметки агента
- `loudness`: LUFS -19.4 в допуске (цель -19.0 ±1 LU), TP -3.2 dBTP ≤ -3.0 — на грани. Флагов нет.
- LRA 4.0 LU > 3 LU (лимит по задаче). При одной главе это не проблема (нет разброса между главами), при полной книге может потребовать внимания.
- mp3-имя файла: `01_Glava_13_Bazovyy_navyk_Ya_tebya_chuvstvuyu.mp3` — кириллица транслитерирована.
- m4b содержит 1 глав-маркер с правильным названием и временем (415 с). Теги title/artist/album/genre прописаны.
- `export-sample`: 60 с с начала главы → sample.mp3 1.4 МБ.
- 55 из 56 секций пропущены (нет рендера) — ожидаемо, `--allow-missing` работает корректно.
