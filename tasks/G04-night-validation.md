---
id: G04
title: ночная проверка перед рендером книги (4 главы + temperature A/B + целостность ch13)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
Перед рендером всей книги проверить на реальном звуке всё, что поменяли за неделю:
паузы «Шаг N.», восстановление «ё», правки ударений, исправления ревью
(повторяющиеся чанки, redo/accept, зависания воркеров), очередь и замок.
Плюс решить, оставлять ли temperature 1.0 или ставить 0.9.

## Жёсткие правила (нарушение = стоп и отчёт)
- Рендер ТОЛЬКО секций из этой задачи. `synth`/`chunk` без `--section` — никогда.
- Ничего не удалять в `out/`, `cache/`, `ref/`. Не редактировать `config.yaml`,
  `text/*.yaml`, код. Пробные конфиги — только копии в `out/`.
- Всё тяжёлое — через очередь (`./run.sh queue add -- …`), не руками параллельно.
- Вывод команд в отчёт — ДОСЛОВНО. Свои выводы — отдельным абзацем «Заметки агента».
- Не придумывать команды; если команда падает — хвост ошибки в отчёт и следующий шаг.

## Секции
```
CH13=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu
A=30_glava_23_karta_istseleniya_poshagovaya_i      # 26 мин: «Шаг один.» ×36, повторы
B=21_glava_14_pyat_klyuchej_kak_otkryt_zakryt      # 13 мин: вопросы, перечисления
C=44_vmesto_poslesloviya_pismo_tebe                # 5 мин: тёплый текст
D=52_lichnost_za_2_minuty                          # 6 мин: слова капсом (ТЕЛО, ПАУЗА…)
```

## Шаг 0. Подготовка (≈5 мин)
1. `cd ~/audiobook && git checkout port-validated-settings && git pull`
   `git log --oneline -15 | grep "Review fixes (3/3)"` — если пусто: стоп,
   «нет финальных исправлений ревью», ничего не запускать.
2. `uv sync --extra dev` → `uv run pytest -q` → зелёный, иначе стоп.
3. `./run.sh preflight` → GREEN, иначе стоп (llama-server и чужие процессы недопустимы).
4. `export AUDIOBOOK_DEVICE=cpu` (во всех шагах).

## Шаг 1. Целостность главы 13 после старой перечанковки (≈10 мин)
1. `./run.sh chunk --section $CH13` — вывод дословно.
2. Посчитать в манифесте:
   ```
   uv run python - <<'PY'
   import json, collections
   rows=[json.loads(l) for l in open("out/sections/20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu/manifest.jsonl",encoding="utf-8")]
   print("rows",len(rows),"locked",[r["id"] for r in rows if r.get("locked")])
   print("status",collections.Counter(r.get("status") for r in rows))
   dup=collections.Counter(r["hash"] for r in rows); print("dup hashes",sum(1 for v in dup.values() if v>1))
   PY
   ```
3. `./run.sh queue add -- qc --section $CH13` и `./run.sh queue run` (дождаться).
   Из лога: строка `section=… recovered=… manual=… suspect=…` и все строки MANUAL.
   MANUAL с большим CER = подозрение, что под чанком лежит звук другого текста.
4. `./run.sh redo $CH13 0001 --candidates 4` (старые кандидаты сами уйдут в `_old_*`).
   `./run.sh review --dir out/redo/$CH13/0001 --title redo_0001_v2`

## Шаг 2. Temperature A/B на наборе трудных чанков (≈1.5 ч)
1. `cp config.yaml out/cfg_t09.yaml` и в КОПИИ заменить `temperature: 1.0` на `temperature: 0.9`
   (sed по копии; `diff config.yaml out/cfg_t09.yaml` → ровно одна строка — в отчёт).
2. `./run.sh queue add -- golden render --tag base2`
   `AUDIOBOOK_CONFIG=out/cfg_t09.yaml ./run.sh queue add -- golden render --tag t09`
   `./run.sh queue list` — у задачи t09 должен быть записан путь cfg_t09.yaml
   (если очередь не хранит конфиг задачи — стоп этого шага, отметить в отчёте).

## Шаг 3. Четыре главы целиком (≈5.5 ч) — в ту же очередь, после шага 2
Для каждой S из A, B, C, D по порядку:
```
./run.sh queue add -- chunk --section $S
./run.sh queue add -- synth --section $S --workers 2
./run.sh queue add -- qc --section $S
./run.sh queue add -- assemble --section $S
./run.sh queue add -- master --section $S
./run.sh queue add -- suspects --section $S
```
Затем `nohup ./run.sh queue run > out/night_G04.log 2>&1 &` и не трогать до утра.
Проверять изредка: `./run.sh queue list`, `tail -3 out/night_G04.log`, `free -g`.
Если задача упала — следующие идут дальше; не перезапускать вручную, только отчёт.

## Шаг 4. Утром, когда очередь пуста (≈10 мин)
1. `./run.sh golden compare base2 t09`
   `./run.sh review --dir out/golden/compare_base2_t09 --title t_1.0_vs_0.9`
2. На Mac: `scripts/mac/fetch_results.sh gamebox`, а для страниц прослушки
   с wav: `--with-wav redo/$CH13/0001` и `--with-wav golden/compare_base2_t09`
   (если опции `--with-wav` нет — скопировать wav этих двух папок scp-ом).
3. Скопировать на Mac в `~/Downloads/audiobook/G04/` четыре `section.mp3`
   (переименовать в `<S>.mp3`) и четыре `section.suspects.tsv`.

## Отчёт (дословно, по шагам)
- Шаг 0: хеш HEAD, итог pytest, preflight.
- Шаг 1: вывод chunk, вывод python-скрипта, строка qc и MANUAL, вывод redo.
- Шаг 2: diff конфигов, queue list.
- Шаг 3: `./run.sh queue list` целиком; по каждой главе из логов: chunk (queued/orphaned),
  synth (synthesised/timeout/wall/RTF), qc (recovered/manual/suspect + MANUAL), master (LUFS, peak),
  suspects (первая строка с количеством); пиковое потребление памяти, если видели.
- Шаг 4: пути всех файлов на Mac.
- «Заметки агента» — отдельно, коротко.
- `status: review`.
