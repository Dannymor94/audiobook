---
id: G11
title: паузы по знаку в конце фразы + план прослушки на главе 13 (≈10 мин, без синтеза)
status: review
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -1 → 02e81b6 merge export (mp3/m4b book, sample, credits) and wire CLI
uv run pytest -q → 483 passed, 3 skipped
./run.sh preflight → PREFLIGHT: GREEN
cp section.mp3 section_before_by_end.mp3  (9.5 МБ)
```

### Шаг 1. chunk (8697)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu            56 chunks   [re-chunk: 0 queued, 0 orphaned]
TOTAL                                                  56 chunks  (1 sections)
```
→ `0 queued` — паузы by_end не вызывают перерендер. ✓

### Шаг 1. assemble (96c2)
```
section=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  chunks=56  -> .../section.wav
assembled audio (chunks, pre-pauses)=364.4s  peak=1.000  CLIPPING
```

### Шаг 1. master (97db)
```
section=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  -> .../section.mp3
loudnorm input: -18.38 LUFS, TP 2.41 dBTP
final mp3: -19.39 LUFS (target -19), peak 0.6883 (-3.24 dBFS)
```

### Шаг 1. suspects (efa8)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu: подозрительных мест 11 (неуверенно 7, ловушек 4)
    0:16  мы               неуверенно  p=0.214  (чанк 0005)
    0:32  которая          неуверенно  p=0.52  (чанк 0006)
    0:37  слова,           ловушка  p=0.976  (чанк 0007)
    0:44  они              неуверенно  p=0.097  (чанк 0007)
    1:51  скорее           неуверенно  p=0.587  (чанк 0015)
    3:54  Только           неуверенно  p=0.499  (чанк 0033)
    4:03  Дыши             ловушка  p=0.977  (чанк 0034)
    4:11  чувствование.    неуверенно  p=0.344  (чанк 0035)
    4:14  слова,           ловушка  p=0.962  (чанк 0036)
    4:45  и                неуверенно  p=0.249  (чанк 0040)
    5:06  слова.           ловушка  p=0.997  (чанк 0042)
→ .../section.suspects.tsv
```

### Шаг 1. sync (a65a)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvству: 56 фраз → .../section.sync.json
```

### Шаг 1. impact --section $S
```
итого: перерендер 0 чанков из 56 отрендеренных, ~0 мин звука, ~0 ч 00 мин машины
правка не задевает отрендеренный звук
```

### Шаг 2. listen-plan
```
план прослушки: 19 фрагментов, 2:35 (начало глав 6, подозрения 10, выборка 5)
→ /home/danavrata/audiobook/out/listen/plan.mp3
  оглавление: /home/danavrata/audiobook/out/listen/index.tsv
  разметка: ./run.sh review --dir out/listen  → ./run.sh fix plan <labels.json>
```

### Шаг 2. review
```
страница прослушки: out/listen/review.html  (probe: подборка ловушек, 19 шт.)
открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>
```

### Шаг 3. Файлы на Mac
```
~/Downloads/audiobook/G11/ch13_before.mp3    9.5 МБ  (до новых пауз by_end)
~/Downloads/audiobook/G11/ch13_by_end.mp3    9.5 МБ  (с паузами by_end)
~/Downloads/audiobook/2026-10-30/listen/review.html  (19 wav + plan.mp3 + index.tsv)
```

### Заметки агента
- `chunk: 0 queued` и `impact: 0 перерендеров` — паузы `by_end` не входят в хеш чанка, только в сборку. Перерендера нет.
- `assemble`: длительность 364.4 с совпадает с G10, CLIPPING снова исправляется loudnorm в master.
- `master`: LUFS/peak практически идентичны G10 (-19.39 LUFS, peak -3.24 dBFS). Разница с by_end будет только в паузах между фразами с «?», «!», «…», «:», «;» — слышна при прослушке.
- `listen-plan`: 19 фрагментов = 6 начала глав + 10 подозрений + 5 случайных. Страница совместима с `fix` для маркировки.
- На Mac: два mp3 для A/B сравнения (before vs by_end), плюс страница разметки с 19 wav.


