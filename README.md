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

## Тесты
- `pytest` — слои 1–2, без моделей, секунды. Гоняются в CI на обеих ОС.
- `RUN_SLOW=1 pytest -m slow` — реальные модели, локально.
# audiobook
