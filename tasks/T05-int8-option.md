---
id: T05
title: опция int8 (dynamic quantization) для ускорения CPU-рендера
status: review
owner: claude-subagent
machine: code
branch: task/T05
depends_on: []
---
## Зачем
Книга ≈ 3–3.5 суток на CPU (RTF 6.5, 2 воркера). Dynamic int8 Linear может дать
1.5–2×, но может испортить звук — нужен выключатель и честная проверка (G03).

## Сделать
1. `config.yaml` → `model.quantize: none` (по умолчанию none; значение int8 —
   `torch.ao.quantization.quantize_dynamic(model.model, {torch.nn.Linear}, dtype=torch.qint8)`
   после загрузки, только на cpu). Правка ТОЛЬКО ключа с none (поведение не меняется).
2. Хеш: quantize ≠ none входит в model id (voicecfg.model_id → "...-int8"), чтобы
   int8-аудио никогда не смешалось с fp32 в кеше. none — хеши не меняются (тест).
3. Прокинуть через worker_config → worker → load_model. doctor: строка с режимом.
4. Тесты слоя 1: model_id, worker_config, что load_model вызывает quantize при int8
   (мок, без весов). Слой 3 (slow): прогон одного короткого чанка int8 — маркер slow.

## Правила
CLAUDE.md проекта. Замена должна затронуть voicecfg/synth/worker, не больше.

## Отчёт

Сделано (проверено: `pytest -q` — 208 passed, 2 skipped; слой 3 не запускался, весов нет):
- `voicecfg.quantize(config)` → `none|int8`, по умолчанию `none`, прочее — `SystemExit` по-русски.
  `model_id` добавляет `-int8` только при int8; при none id идентичен прежнему (тест), хеши не меняются.
- `synth.load_model(device, variant, quantize="none")`: при int8 требует cpu, затем
  `torch.ao.quantization.quantize_dynamic(model.model, {torch.nn.Linear}, dtype=torch.qint8)`
  с присвоением обратно в `model.model`. Кеш `_model` теперь ключуется по `(device, variant, quantize)`
  (`_model_key`); смена ключа перезагружает модель. `worker_config` несёт `quantize`,
  `worker` передаёт его в `load_model` (`"none"`, если ключа нет — старые cfg работают).
- `config.yaml`: только `model.quantize: none` с комментарием. `doctor`: info-строка `quantize`.
- Тесты: `tests/test_quantize.py` (слой 1: валидация, model_id none/int8, worker_config, мок
  `quantize_dynamic`, реальная подмена Linear на игрушечной модели, cpu-only, ключ кеша);
  `tests/test_slow_models.py` — slow-тест одной короткой плейсхолдер-фразы на int8.
- Замечания: (1) `bench` не трогали (вне рамок задачи) — он вызывает `load_model` без quantize,
  поэтому замер RTF для int8 через него пока невозможен; нужна одна строка, если надо.
  (2) В установленном torch `torch.ao.quantization` помечен deprecated (удалят в 2.10, миграция на
  torchao) — при обновлении torch эта опция сломается первой. (3) Качество int8 не проверено —
  это работа G03; до неё оставлять `none`.
