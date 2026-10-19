# RYZEN.md — развёртывание на Ubuntu / Ryzen 7

Пошаговый чеклист. Проверять сверху вниз; каждый пункт — команда или утверждение с измеримым результатом.

---

## 1. Системные зависимости

```bash
sudo apt update
sudo apt install -y git python3.11 python3.11-venv ffmpeg
# Проверка:
ffmpeg -version | head -1    # ожидаем 4.x или 5.x
python3.11 --version         # ожидаем 3.11.x
```

Установить `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# или: pip install uv
uv --version
```

---

## 2. Клонировать репозиторий

```bash
git clone https://github.com/Dannymor94/audiobook.git
cd audiobook
```

Если репозиторий приватный — нужен SSH-ключ или токен в URL.

---

## 3. Установить зависимости

```bash
uv sync --extra dev
```

**Предупреждение — размер torch:**  
На Linux `torch` берётся с PyPI по умолчанию. Это CUDA-включённый wheel (~2.5 ГБ), даже если GPU не нужен. Он работает на CPU, но скачивается долго. Если нужен CPU-only wheel (~200 МБ), обсудите добавление Linux в секцию `[tool.uv.sources]` в `pyproject.toml` — это меняет `uv.lock` и требует проверки.

---

## 4. Скопировать данные вручную (флешка или scp)

Эти пути в `.gitignore`; в репозиторий не попадают.

| Что копировать | Куда на Ryzen | Примечания |
|---|---|---|
| `models/hf/hub/models--Qwen--Qwen3-TTS-12Hz-0.6B-Base/` | `models/hf/hub/` | 2.3 ГБ, продакшн-модель |
| `models/hf/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base/` | `models/hf/hub/` | 4.2 ГБ, нужна для этапа E (тест) |
| `models/whisper/small/` | `models/whisper/` | 464 МБ, QC |
| `ref/ref1.wav` | `ref/` | голос автора |
| `ref/ref1.txt` | `ref/` | дословная расшифровка ref1 |
| `ref/ref1.latents.pt` | `ref/` | предсчитанные латенты; без них вычислятся заново при первом запуске |
| `text/*.docx` | `text/` | рукопись (если нужно перегенерировать .txt) |

Все `.txt` и `.norm.txt` в `text/` уже в git — копировать не нужно.

---

## 5. Проверить окружение

```bash
AUDIOBOOK_DEVICE=cpu ./run.sh doctor
```

Ожидаемый вывод: GREEN по всем пунктам. Особенно:
- `ffmpeg` найден в `bin/` или PATH
- `ref/ref1.wav` существует
- `ref/ref1.latents.pt` существует
- `models/.../config.json` существует для обеих моделей
- `models/whisper/small/` существует

---

## 6. Быстрый smoke-тест

```bash
uv run pytest -q
```

Все тесты слоёв 1–2 должны пройти без моделей.

---

## 7. Замер производительности (этап E)

```bash
uv run python bench_ryzen.py --all
```

Тест прогоняет 10 чанков из главы 13 на раскладках `1x8`, `2x4`, `3x2`, `4x2`.  
Вывод для каждой раскладки:

```
layout=2x4  workers=2  threads_each=4  audio=Xs  wall=Ys  throughput=Z audio-s/wall-s
```

**Пороги для ночного рендера (12.4 ч аудио за 8 ч стены):**

Нужный throughput: 12.4 / 8 = **1.55 audio-s/wall-s**. Ниже — расчёт по идеальной параллельности (верхняя оценка); реальные числа — только из bench.

| Раскладка | При RTF 5× (оптим.) | При RTF 8× (консерв.) | При RTF 10× |
|---|---|---|---|
| 1×8 | 62 ч | 99 ч | 124 ч |
| 2×4 | 31 ч | 50 ч | 62 ч |
| 3×2 | 21 ч | 33 ч | 41 ч |
| 4×2 | **15.5 ч** | 25 ч | 31 ч |
| 8×1 | **7.75 ч ✅** | 12.4 ч | 15.5 ч |

Mac RTF 6.4 измерен на **CPU** (Qwen не работает на MPS; везде используется `AUDIOBOOK_DEVICE=cpu`). Ryzen сопоставим CPU-к-CPU; ожидаемый диапазон **5–10×**. При 8 воркерах и RTF 8× — около одной ночи; при RTF 5× — укладывается. Bench покажет реальный RTF и насколько параллельность близка к идеальной.

> **Примечание о параллельности.** `NxT` — N воркеров, каждый держит T потоков ATen. Реальный прирост от N воркеров меньше N×, потому что модели конкурируют за RAM-bandwidth. Ожидаемая деградация: 2× хуже идеала для 2×4, сильнее при 4×2. Bench измеряет это напрямую.

Прислать вывод `bench_ryzen.py --all` для планирования этапа F (массовый рендер).

---

## 8. Запуск рендера

После получения результатов bench и согласования раскладки:

```bash
# Один раздел (пробный):
AUDIOBOOK_DEVICE=cpu uv run audiobook synth --section 20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu

# Полный рендер — только по итогам bench и решения об N воркерах
```
