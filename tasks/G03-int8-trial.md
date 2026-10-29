---
id: G03
title: int8 против fp32 на golden set — скорость и звук
status: todo
owner:
machine: gamebox
depends_on: [T05, G02]
---
## Шаги
1. `./run.sh preflight` → GREEN.
2. Временный конфиг: `cp config.yaml out/config_int8.yaml`, в копии `model.quantize: int8`.
   Запуск с ним: `AUDIOBOOK_CONFIG=out/config_int8.yaml ./run.sh golden render --tag int8`
   (если переменной AUDIOBOOK_CONFIG нет — стоп, это блокер для T05).
3. `./run.sh golden compare base-ref_ch1 int8` → `review --dir out/golden/compare_base-ref_ch1_int8`.
4. Отчёт: время рендера обоих тегов (из логов), пути файлов. Сравнение на слух делает Антон.

## Отчёт
