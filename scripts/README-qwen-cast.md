# QWEN-VOICE-CAST-01: приватный оператор

Точное поручение: issue #26, comment 7236230811. Это исследовательские
скрипты, не новый production entrypoint. Все реальные модели — только
Linux `danny-serv`, общий production heavy.lock, без облака и уведомлений.
Производственные настройки, текст, референс, латенты и WAV не меняются.

Корни `cast_production` и `cast_out` задаёт оператор: первый — существующий
production checkout; второй — новый приватный устойчивый каталог вне
production out/cache и tmpfs. Проверить их реальные пути, RAM/диск, процессы,
точный HEAD и `./run.sh preflight` до запуска. Код на gamebox доставляется
только через git. Никаких моделей на Mac.

## Отдельное скачивание

Только при отсутствии проверенных CustomVoice/VoiceDesign. Существующий Base
повторно не скачивается. Скрипт фиксирует immutable revision до загрузки,
проверяет Apache-2.0, сохраняет SHA-256 всех файлов и digest манифеста.
Скачивание не запускает inference и не обновляет зависимости.

```bash
PYTHONPATH="$PWD/src" HF_HOME="$cast_production/models/hf" \
HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 \
"$cast_production/.venv/bin/python" -u scripts/qwen_cast_provision.py \
  --assets "$cast_out/models"
```

Дождаться обоих файлов `CustomVoice.json` и `VoiceDesign.json` и завершения
процесса скачивания. Не запускать две большие модели одновременно.

## Ограниченный пакет

После зелёного `uv run pytest -q`:

```bash
nohup bash scripts/qwen_cast_batch.sh "$cast_production" "$cast_out" \
  > "$cast_out/batch.log" 2>&1 < /dev/null &
```

Порядок: freeze plan → пять CustomVoice → три VoiceDesign референса →
Base-клоны этих трёх голосов → Whisper/сборка/master/слепая страница.
Каждая стадия заново проверяет admission и держит именно canonical lock.
Модели выгружаются между стадиями. PID, время, журнал и exit-коды остаются
в приватном каталоге. Завершение подтверждают WAV и receipts с SHA-256.

Повторно весь batch с существующим планом не запускать. Завершённые чанки
не перезаписываются. Для возобновления конкретной стадии доступны
`qwen_cast_operator.py --help` и `--stage`; существующий незавершённый
`.attempt.json` означает блокировку этой попытки, а не разрешение повторять
seed. Другие голоса продолжаются. При недоступном gamebox, занятом lock или
изменении замороженных входов — STOP / GAMEBOX_REQUIRED, без fallback.

## Отчёт и доставка

После окончания batch:

```bash
PYTHONPATH="$PWD/src" HF_HOME="$cast_production/models/hf" \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$cast_production/.venv/bin/python" -u scripts/qwen_cast_report.py \
  --production "$cast_production" --out "$cast_out"
```

`blind-listening/index.html` и девять MP3 копируются только на Mac владельца.
Ключ `blind-key_PRIVATE.json`, план и технический отчёт хранятся отдельно от
страницы. Проверка Chrome: `qwen_cast_browser.mjs`; внешние npm-зависимости
не нужны. Полные аудио, текст и отчёты PRIVATE в git не попадают.

Сравнение CustomVoice и VoiceDesign→Base — end-to-end, не чистый эффект
диктора. Текст синтетических референсов совпадает с первым чанком отрывка;
перекрытие указывается в отчёте. ASR не оценивает ударения, акцент,
приятность или стабильность голоса. Все слушательские оценки остаются
пустыми до прослушивания владельцем. Производственный голос автоматически
не заменяется.
