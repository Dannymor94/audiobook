# audiobook — локальный TTS-пайплайн

## Переезд Mac → Windows
1. Mac: `uv sync --extra dev`, `./run.sh doctor`, `RUN_SLOW=1 uv run pytest -m slow`, одна глава на `AUDIOBOOK_DEVICE=cpu`.
2. `git push` (код, text/, config.yaml). CI должен быть зелёным на windows-latest.
3. На флешку: `models/`, `bin/ffmpeg.exe`, `ref/`, при желании `cache/`.
4. Windows: `git clone`, скопировать папки, `cp .env.example .env`, `uv sync --extra dev`, `run.bat doctor`, `run.bat bench`.

## Веса (один раз, на Mac с сетью)
- XTTS-v2: снять `HF_HUB_OFFLINE`, запустить `./run.sh bench` — скачает в `models/tts`.
- Фонемная модель для `phoneme-check` (эксперимент, ~1.3 ГБ, Apache-2.0): `uv run python scripts/fetch_phoneme_model.py` — скачает в `models/hf/hub`. Рантайм остаётся оффлайн.
- RUAccent: `RUAccent(workdir="models/ruaccent")` при первом вызове.
- whisper: `faster-whisper` модель `small` → `models/whisper/small` (ct2-конвертированная).

## Gamebox: preflight и очередь
- `./run.sh preflight [--min-free-gb N] [--max-load X]` — перед любой работой на gamebox. Построчно GREEN/RED/WARN: load(1м) < X (деф. 4), available RAM >= N ГБ (деф. 16), нет чужих тяжёлых процессов (whisper, transcri, llama-server, `audiobook synth/qc/probe/…`), git (ветка, HEAD, чистые отслеживаемые файлы, HEAD == origin/ветка после fetch), `doctor`. WARN — значение не измерить (не Linux, нет сети); он не красит итог. Итог `PREFLIGHT: GREEN|RED`, код выхода 0/1. `--no-models` — doctor без проверки весов.
- Очередь тяжёлых задач, чтобы они не накладывались: `./run.sh queue add -- <аргументы run.sh>`, `./run.sh queue list`, `./run.sh queue run`. Всё лежит в `out/queue/` (`pending/`, `done/`, `logs/`). `queue run` держит замок `out/queue/heavy.lock`, берёт задачи по одной в порядке добавления, пишет лог, переносит в `done/` со статусом и кодом выхода; второй `queue run` ждёт замок. `synth` и `chunk` без `--section` при `add` отклоняются.
- Забрать результаты на Mac: `scripts/mac/fetch_results.sh [хост] [--dry-run]` (хост по умолчанию `gamebox`). rsync из `~/audiobook/out/` только `*.mp3 *.tsv *.txt *.html *.json *.log` (wav не берёт) в `~/Downloads/audiobook/<YYYY-MM-DD>/`; на источнике ничего не удаляется.

## Тесты
- `pytest` — слои 1–2, без моделей, секунды. Гоняются в CI на обеих ОС.
- `RUN_SLOW=1 pytest -m slow` — реальные модели, локально.
# audiobook
