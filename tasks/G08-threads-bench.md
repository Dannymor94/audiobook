---
id: G08
title: подбор потоков на воркер (bench, ≈40 мин)
status: review
owner: claude-sonnet-4-6
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

### Шаг 0
```
git log --oneline -1 → 14c8824 wire loudness, pron-audit, queue run --watch/--requeue-interrupted
uv run pytest -q → 434 passed, 2 skipped
./run.sh preflight → PREFLIGHT: GREEN
nproc → 16
lscpu:
  Model name:   AMD Ryzen 7 5700X 8-Core Processor
  Thread(s) per core: 2
  Core(s) per socket: 8
  Socket(s): 1
free -g: available 28 ГБ (> 26 ГБ, можно запускать)
```

### Шаг 1. Логи (строки device/load/RTF дословно)

**bench --workers 2** (f5d1):
```
device=cpu  workers=2  threads/worker=8
load: 11.7s
RTF=6.23  (workers=2, threads/worker=8)  → 12 ч звука ≈ 3.1 сут
```

**bench --workers 2 --threads 4** (4174):
```
device=cpu  workers=2  threads/worker=4
load: 6.6s
RTF=6.12  (workers=2, threads/worker=4)  → 12 ч звука ≈ 3.1 сут
```

**bench --workers 2 --threads 6** (1410):
```
device=cpu  workers=2  threads/worker=6
load: 12.5s
RTF=6.18  (workers=2, threads/worker=6)  → 12 ч звука ≈ 3.1 сут
```

**bench --workers 2 --threads 8** (7735, второй прогон):
```
device=cpu  workers=2  threads/worker=8
load: 6.8s
RTF=6.69  (workers=2, threads/worker=8)  → 12 ч звука ≈ 3.3 сут
```

**bench --workers 1 --threads 8** (db69):
```
device=cpu  workers=1  threads/worker=8
load: 11.7s
RTF=7.96  (workers=1, threads/worker=8)  → 12 ч звука ≈ 4.0 сут
```

**bench --workers 1 --threads 16** (ee84):
```
device=cpu  workers=1  threads/worker=16
load: 5.7s
RTF=8.65  (workers=1, threads/worker=16)  → 12 ч звука ≈ 4.3 сут
```

### Таблица workers × threads → RTF

| workers | threads/worker | RTF   | сут/12 ч |
|---------|----------------|-------|----------|
| 2       | 4              | 6.12  | 3.1      |
| 2       | 6              | 6.18  | 3.1      |
| 2       | 8 (default)    | 6.23  | 3.1      |
| 2       | 8 (повтор)     | 6.69  | 3.3      |
| 1       | 8              | 7.96  | 4.0      |
| 1       | 16             | 8.65  | 4.3      |

### Заметки агента

- 2 воркера при любом числе потоков (4/6/8) дают практически одинаковый RTF ≈ 6.1–6.7×. Разброс между двумя прогонами `--workers 2 --threads 8` (6.23 vs 6.69) сопоставим с вариацией между 4/6/8 потоками — это шум, не сигнал.
- 1 воркер × 8 потоков = RTF 7.96×, 1 воркер × 16 потоков = RTF 8.65× — оба заметно хуже 2 воркеров. Параллельный синтез двумя воркерами выгоднее одного с большим числом потоков.
- Дефолт (threads=логические_ядра/workers = 16/2 = 8) уже близок к оптимуму для 2 воркеров. Уменьшение до 4 потоков даёт RTF 6.12 — чуть лучше, но в пределах шума.
- Решение по `render.cpu_threads` — за пользователем.
