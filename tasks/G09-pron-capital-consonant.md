---
id: G09
title: pron-test — «заглавная согласная» в словаре на 1.7B (≈30 мин)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
В text/pronounce.yaml со времён 0.6B стоят правки заглавной согласной: `соЗнание`
(было «сУснание»), `найДи`/`НайДи` (было «нАйди»). На 1.7B их не проверяли. Варианты:
без правки, текущая правка, заглавная ударная гласная. Решает человек по слуху.

## Правила
Те же, что в G04. Словарь не править — только pron-test.

## Шаг 0
Как в G04.

## Шаг 1. Манифесты (только чанкинг двух секций, без рендера)
```
./run.sh chunk --section 07_vvedenie_tvoya_zhizn_eto_lift_kuda_ty_ed
./run.sh chunk --section 21_glava_14_pyat_klyuchej_kak_otkryt_zakryt
```

## Шаг 2. Пробы
```
./run.sh queue add -- pron-test --section 07_vvedenie_tvoya_zhizn_eto_lift_kuda_ty_ed --word сознание --try - соЗнание сознАние --seeds 2
./run.sh queue add -- pron-test --section 21_glava_14_pyat_klyuchej_kak_otkryt_zakryt --word Найди --try - НайДи НайдИ --seeds 2
./run.sh queue run
```
Для каждой папки из вывода pron-test (`out/pron_test/<...>/`):
`./run.sh review --dir out/pron_test/<папка> --title <слово>_1.7B`

## Шаг 3. На Mac
`scripts/mac/fetch_results.sh gamebox --with-wav pron_test`

## Отчёт
Вывод chunk (2 строки), вывод обоих pron-test целиком (таблица вариантов с [м:сс]),
пути к review.html на Mac. `status: review`.
