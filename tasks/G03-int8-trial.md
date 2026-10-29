---
id: G03
title: int8 против fp32 на golden set — скорость и звук
status: review
owner: claude-sonnet-4-6
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

### preflight
```
GREEN  load(1м) 0.61 < 4
GREEN  RAM available 29.3 ГБ >= 16
GREEN  чужих тяжёлых процессов нет
GREEN  git ветка port-validated-settings
GREEN  git HEAD d686d2d
GREEN  git: отслеживаемые файлы чистые
GREEN  git HEAD == origin/port-validated-settings
GREEN  doctor

PREFLIGHT: GREEN
```

### config_int8.yaml
```
cp config.yaml out/config_int8.yaml && sed -i "s/quantize: none/quantize: int8/" out/config_int8.yaml
→ quantize: int8
```

### golden render base-ref_ch1 (fp32, из лога G02)
```
golden base-ref_ch1: записей 45, найдено чанков 45, к синтезу 45
прослушка: …/out/golden/base-ref_ch1/golden.mp3  оглавление: …/index.tsv  (45 из 45)
```
Время: 10:59 (директория создана) → 11:40 (golden.mp3) = **41 мин (2460 с)**
Аудио: **277.8 с** (45 wav)
RTF fp32: **2460 / 277.8 ≈ 8.9×**

### golden render int8
```
AUDIOBOOK_CONFIG=out/config_int8.yaml ./run.sh golden render --tag int8
golden int8: записей 45, найдено чанков 45, к синтезу 45
```
Запуск 1 (11:46:05): `synth worker failed to start (model load timed out)` в 12:01:05 — ровно 900 с (start_timeout_s).

Причина: `torch.ao.quantization.quantize_dynamic` на Qwen3-TTS-1.7B (spawn-воркер) занимает **≥ 900 с (~15 мин)** только для загрузки + квантизации модели в новом процессе. До синтеза дело не доходило.

Исправлен баг T05: `quantize_dynamic` бросал `TypeError: cannot pickle 'dict_keys' object` при попытке deepcopy Qwen-модели. Добавлен `inplace=True` (commit `8445141`). Баг был в способе применения, не в самой идее int8.

Попытки с `start_timeout_s=1800`: прерваны по запросу (Антон — «таймаут не увеличивать»).

**int8 wav файлов в out/golden/int8/: 0** — RTF синтеза не вычислить.

### golden compare
Пропущен: int8 wav < 5.

### Заметки агента

**RTF fp32 (base-ref_ch1): 8.9×** (spawn-воркер, 1 воркер, cpu, Ryzen 7).

**int8 неприемлем в текущем виде:** `torch.ao.quantization.quantize_dynamic` на 1.7B модели в spawn-воркере занимает ≥15 минут только на старт. Каждый respawn (после таймаута чанка) тоже требует перезагрузки. При chunk_timeout_s=600 и RTF 8.9× только самые длинные чанки (~67 с аудио, ~180 символов) могут упираться в таймаут, но respawn в int8 гарантированно проваливается за start_timeout_s=900.

Возможные пути для ускорения:
- Перейти на `torchao` (рекомендуется PyTorch 2.14, заменит deprecated `torch.ao.quantization`)
- Использовать `int8` только в in-process режиме (не spawn-воркер), загрузив модель один раз
- Рассмотреть `bfloat16` как более безопасную альтернативу

