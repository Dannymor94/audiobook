---
id: T05
title: опция int8 (dynamic quantization) для ускорения CPU-рендера
status: doing
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
