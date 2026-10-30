---
id: G08
title: подбор потоков на воркер (bench, ≈40 мин)
status: todo
owner:
machine: gamebox
depends_on: []
---
## Зачем
Сейчас каждый из 2 воркеров берёт «логические ядра / 2» потоков. Возможно, меньше
потоков (без гиперпоточности) или 1 воркер × все ядра быстрее. Замер — для настройки
`render.cpu_threads` в config.yaml (решает человек по результатам).

## Правила
Те же, что в G04. Ничего не рендерить, кроме bench. Конфиг не править.

## Шаг 0
Как в G04. Дополнительно в отчёт: `nproc`, `lscpu | grep -E "Model name|Thread|Core|Socket"`.

## Шаг 1. Замеры (каждый через очередь, по одному)
```
./run.sh queue add -- bench --workers 2
./run.sh queue add -- bench --workers 2 --threads 4
./run.sh queue add -- bench --workers 2 --threads 6
./run.sh queue add -- bench --workers 2 --threads 8
./run.sh queue add -- bench --workers 1 --threads 8
./run.sh queue add -- bench --workers 1 --threads 16
./run.sh queue run
```
Если `free -g` показывает available < 26 ГБ перед стартом — стоп (2 воркера × ~12 ГБ).

## Отчёт
Из логов каждой задачи (`out/queue/logs/<id>.log`) строки `device=…`, `load: …`, `RTF=…` — дословно.
Таблица: workers × threads → RTF. `status: review`.
