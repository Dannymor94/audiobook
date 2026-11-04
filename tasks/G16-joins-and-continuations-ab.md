---
id: G16
title: стыки главы 13 + A/B продолжений фраз (без рендера книги)
status: todo
owner:
agent: claude-code
machine: gamebox
order: 3
depends_on: [T10, T11]
---
## Зачем
Откалибровать пороги `joins` и дать человеку на слух варианты из T10.

## Правила
Те же, что в G04. `AUDIOBOOK_CONFIG=` — только перед одной командой, на копии.

## Поправка к задаче (2026-11-04)
`continuations: context` **не делать**: опции нет, контекст `previous` включён для
всех чанков по решению. Сравнивать только `open_end: keep / none / ellipsis`.
Секции с open_end чанками (всего 39, text/stack): не глава 13, а главы 1, 4, 20
и другие (список ниже). Глава 13 — только для G18 (тебя).

## Секции с open_end-чанками
```
08_glava_1_zver_vnutri_nas_instinkty_eto_ne  — 5 чанков (#0210–0213, +#0070)
11_glava_4_bolevoe_telo_vulkan_kotoryj_drem  — 5 чанков (#0007,#0081,#0086,#0089,#0217)
27_glava_20_povedencheskij_eksperiment_prov  — 6 чанков (#0045–0049, +#0008)
33_glava_26_vstrecha_dvukh_vselennykh_kak_n — 3 чанка (#0082,#0083,#0088)
48_prilozhenie_1_karta_geroya_bystraya_samo  — 5 чанков (#0094–0097, +#0004)
```

## Шаги
Шаг 0 как в G04. Затем:

1. joins на двух секциях с наибольшей плотностью open_end-чанков:
   ```bash
   ./run.sh joins --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne
   ./run.sh joins --section 27_glava_20_povedencheskij_eksperiment_prov
   ```
   Вывод — дословно.

2. Три копии конфига (только `text_prep.open_end` меняется):
   ```bash
   cp config.yaml config_oe_keep.yaml    # keep = текущее поведение (база)
   cp config.yaml config_oe_none.yaml    # open_end: none
   cp config.yaml config_oe_ellipsis.yaml # open_end: ellipsis
   # В config_oe_none.yaml добавить под text_prep:   open_end: none
   # В config_oe_ellipsis.yaml:                      open_end: ellipsis
   ```
   Для каждой копии — `impact` по секции с наибольшим числом open_end:
   ```bash
   AUDIOBOOK_CONFIG=config_oe_none.yaml    ./run.sh impact --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne --verbose
   AUDIOBOOK_CONFIG=config_oe_ellipsis.yaml ./run.sh impact --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne --verbose
   ```
   Вывод дословно.

3. `passage` по отрывкам с open_end-чанками — три варианта:
   ```bash
   # Глава 1, список #0208–0215 (что тебя заводит / истощает / к чему тянешься…)
   ./run.sh passage --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne --start 208 --count 8 --tag base
   AUDIOBOOK_CONFIG=config_oe_none.yaml     ./run.sh passage --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne --start 208 --count 8 --tag none
   AUDIOBOOK_CONFIG=config_oe_ellipsis.yaml ./run.sh passage --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne --start 208 --count 8 --tag ellipsis

   # Глава 20, список #0043–0051 (замечаешь волну / не поддаёшься / выбираешь…)
   ./run.sh passage --section 27_glava_20_povedencheskij_eksperiment_prov --start 43 --count 9 --tag base
   AUDIOBOOK_CONFIG=config_oe_none.yaml     ./run.sh passage --section 27_glava_20_povedencheskij_eksperiment_prov --start 43 --count 9 --tag none
   AUDIOBOOK_CONFIG=config_oe_ellipsis.yaml ./run.sh passage --section 27_glava_20_povedencheskij_eksperiment_prov --start 43 --count 9 --tag ellipsis
   ```

4. `joins` на тех же отрывках для каждого варианта — сравнить флаги:
   ```bash
   ./run.sh joins --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne
   AUDIOBOOK_CONFIG=config_oe_none.yaml     ./run.sh joins --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne
   AUDIOBOOK_CONFIG=config_oe_ellipsis.yaml ./run.sh joins --section 08_glava_1_zver_vnutri_nas_instinkty_eto_ne
   ```

5. Привезти на Mac (`scripts/mac/fetch_results.sh`) и написать пути к mp3.

## Отчёт
