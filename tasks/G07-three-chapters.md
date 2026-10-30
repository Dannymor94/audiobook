---
id: G07
title: ещё три главы — 14, «Письмо тебе», «Личность за 2 минуты» (≈2.5 ч)
status: todo
owner:
machine: gamebox
depends_on: [G06 прослушана человеком]
---
## Зачем
Вопросы и перечисления (гл. 14), тёплый текст (письмо), слова капсом (личность).
Не начинать, пока человек не прослушал G06 и не сказал «дальше».

## Правила
Те же, что в G04.

## Шаг 1
Для каждой S по порядку — те же 6 команд `queue add`, что в G06:
```
21_glava_14_pyat_klyuchej_kak_otkryt_zakryt
44_vmesto_poslesloviya_pismo_tebe
52_lichnost_za_2_minuty
```
Затем один `nohup ./run.sh queue run > out/G07.log 2>&1 &`.

## Шаг 2. На Mac
`~/Downloads/audiobook/G07/<S>.mp3` + `<S>.suspects.tsv`.

## Отчёт
Как в G06, по каждой главе. `status: review`.
