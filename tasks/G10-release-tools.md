---
id: G10
title: проверка новых команд на главе 13 — тишина/теги, sync, impact, pace (≈15 мин, без рендера)
status: review
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -1 → 1f7de5d release tools: chapter head/tail silence + ID3 tags/cover, sync map, impact, pace
uv run pytest -q → 443 passed, 2 skipped
./run.sh preflight → PREFLIGHT: GREEN
```

### Шаг 1. assemble (18f2)
```
section=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  chunks=56  -> .../section.wav
assembled audio (chunks, pre-pauses)=364.4s  peak=1.000  CLIPPING
```

### Шаг 1. master (a983)
```
section=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  -> .../section.mp3
loudnorm input: -18.38 LUFS, TP 2.41 dBTP
final mp3: -19.39 LUFS (target -19), peak 0.6877 (-3.25 dBFS)
```

### Шаг 1. suspects (d66d)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu: подозрительных мест 11 (неуверенно 7, ловушек 4)
    0:16  мы               неуверенно  p=0.214  (чанк 0005)
    0:32  которая          неуверенно  p=0.52  (чанк 0006)
    0:37  слова,           ловушка  p=0.976  (чанк 0007)
    0:44  они              неуверенно  p=0.097  (чанк 0007)
    1:51  скорее           неуверенно  p=0.587  (чанк 0015)
    3:53  Только           неуверенно  p=0.499  (чанк 0033)
    4:02  Дыши             ловушка  p=0.977  (чанк 0034)
    4:11  чувствование.    неуверенно  p=0.344  (чанк 0035)
    4:14  слова,           ловушка  p=0.962  (чанк 0036)
    4:45  и                неуверенно  p=0.249  (чанк 0040)
    5:05  слова.           ловушка  p=0.997  (чанк 0042)
→ .../section.suspects.tsv
```

### Шаг 1. sync
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu: 56 фраз → .../section.sync.json
```

### Шаг 1. head -c 600 section.sync.json
```json
{
 "section": "20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu",
 "title": "Глава 13. Базовый навык: «Я тебя чувствую»",
 "audio": "section.mp3",
 "head_ms": 1000,
 "chunks": [
  {
   "id": "0001",
   "start_ms": 1000,
   "end_ms": 2290,
   "text": "Глава тринадцатая.",
   "para_end": true
  },
  {
   "id": "0002",
   "start_ms": 3490,
   "end_ms": 4650,
   "text": "Базовый навык:",
   "para_end": false
  },
  {
   "id": "0003",
   "start_ms": 5350,
   "end_ms": 7050,
   "text": "«Я тебя чувствую»",
   "para_end": true
  },
```

### Шаг 1. ffprobe section.mp3
```
duration=414.890000
TAG:title=Глава 13. Базовый навык: «Я тебя чувствую»
TAG:album=Ты не поломан
TAG:artist=Александр Исаев
TAG:album_artist=Александр Исаев
TAG:genre=Audiobook
TAG:track=19/56
TAG:encoder=Lavf62.3.100
```

### Шаг 2. impact (config.yaml)
```
итого: перерендер 0 чанков из 68 отрендеренных, ~0 мин звука, ~0 ч 00 мин машины
правка не задевает отрендеренный звук
```

### Шаг 2. impact (out/cfg_t09.yaml)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu  перерендер   56 из 56   отрендеренных  ЗАБЛОКИРОВАННЫЕ: 0003
44_vmesto_poslesloviya_pismo_tebe            перерендер   12 из 12   отрендеренных

итого: перерендер 68 чанков из 68 отрендеренных, ~8 мин звука, ~0 ч 49 мин машины
потеряют ручной выбор (accept): 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/0003
```

### Шаг 2. pace
```
секция                                       чанков  мс/симв   откл.
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu      35     77.4   +0.0%

медиана книги: 77.4 мс/симв (~12.9 симв/с)
→ /home/danavrata/audiobook/out/pace.tsv
```

### Шаг 2. status (сокращённо)
```
20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu     56/56              11  собрано
всего: 1% текста отрендерено (5 986 из 505 748 симв.)
звук: готово ~0.1 ч, осталось ~10.7 ч (темп речи 13.0 симв/с)
осталось рендера: ~2.9 сут при RTF 6.5 (render.eta_rtf)
очередь: 0 ждут
```

### Шаг 3. Файлы на Mac
```
~/Downloads/audiobook/G10/glava_13.mp3      9.5 МБ  (414.9 с = 6:55, 1 с тишины в начале, 2 с в конце)
~/Downloads/audiobook/G10/section.sync.json  15 КБ  (56 фраз с start_ms/end_ms)
```

### Заметки агента
- Длительность mp3: 414.9 с vs 364.4 с аудио чанков — разница 50 с = паузы между чанками + 1 с head + 2 с tail + loudnorm padding. head_ms=1000 подтверждается в sync.json.
- ID3 теги проставлены корректно: title, album, artist, genre=Audiobook, track=19/56.
- impact с текущим config.yaml: 0 перерендеров — настройки не менялись после последнего рендера.
- impact с cfg_t09.yaml (temperature=0.9): все 68 чанков потребуют перерендера; потеря accept на чанке 0003 (заблокирован). Решение по temperature — за пользователем (G05).
- status показывает: только глава 13 и хвостовой раздел 44 частично отрендерены; 99% книги впереди (~2.9 сут при RTF 6.5).
