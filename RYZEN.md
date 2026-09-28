# RYZEN.md — развёртывание на Ubuntu / Ryzen 7

Пошаговый чеклист. Проверять сверху вниз; каждый пункт — команда или утверждение с измеримым результатом.

---

## 1. Системные зависимости

```bash
sudo apt update
sudo apt install -y git ffmpeg     # python3.11 в apt 26.04 нет — ставится через uv (см. §3)
ffmpeg -version | head -1           # системный ffmpeg (ELF x86-64)
```

> **Грабли.** `paths.ffmpeg()` ищет `bin/ffmpeg` раньше PATH. Если репозиторий переносился с Mac (rsync тянет `bin/` мимо .gitignore), там лежит Mach-O arm64 — на Linux `Exec format error`. Убрать: `mv bin/ffmpeg bin/ffmpeg.mac.bak` — подхватится системный из PATH. Переносить надо без `bin/` (как `models/`, `ref/`, `out/`).

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

Тест прогоняет 10 чанков из главы 13 на раскладках `1x8`, `2x8`, `4x4`, `8x2`.

**Измерено на gamebox (Ryzen 7 5700X, 8/16, 30 ГБ, fp32, production config):**

| Раскладка | Throughput | RAM/воркер | Итог |
|---|---|---|---|
| 1×16 | 0,183 audio-s/wall-s | 6,5 ГБ | один воркер, все ядра |
| **4×4** | **0,258** | **5,7 ГБ** | **выбран** |
| 8×2 | своп (8×5 ГБ > 30 ГБ) | — | не влезает |

Это стена памяти: fp32-веса (~2,5 ГБ) стримятся каждый шаг, 4 воркера дают +40% к одному. Снижение footprint на Zen 3 не работает (`bench_precision.py`): bf16 ×35 медленнее (нет AVX512-BF16), fp16 → inf/nan, int8-dynamic → 100% runaway. interop-потоки нейтральны.

**Полная книга: 12,4 ч × 3600 / 0,258 ≈ 48 часов стены ≈ две ночи.** Production-раскладка — **fp32 4×4**.

---

## 8. Запуск рендера

Раскладка выбрана — fp32 4×4. Порядок стадий: `synth → qc → assemble → master`.

```bash
export AUDIOBOOK_DEVICE=cpu
SEC=20_glava_13_bazovyj_navyk_ya_tebya_chuvstvu
uv run audiobook synth  --section "$SEC" --workers 4   # 4 параллельных воркера
uv run audiobook qc      --section "$SEC"
uv run audiobook assemble --section "$SEC"
uv run audiobook master   --section "$SEC"
```

`--workers 4` запускает параллельный путь (`render_section_parallel`): манифест пишет только родитель по-чанково, resume не ломается. Без флага — один воркер (0,183 против 0,258).

---

## 9. qBittorrent Web UI с Mac

qBittorrent-nox слушает на `*:8080`. curl с Mac достигает его напрямую, но Chrome выдаёт `ERR_ADDRESS_UNREACHABLE` — iCloud Private Relay создаёт `utun`-интерфейсы и нарушает браузерный доступ к локальным IP (curl обходит это, браузерный стек — нет).

**Рабочий способ: SSH-туннель.**

Запустить туннель (в отдельном терминале или фоне):

```bash
ssh -N -L 8080:localhost:8080 gamebox
```

Открыть в браузере: **http://localhost:8080**

Алиас для ~/.zshrc (удобный запуск):

```bash
alias qbt='ssh -N -L 8080:localhost:8080 gamebox &; sleep 1 && open http://localhost:8080'
```

После добавления: `source ~/.zshrc`, затем просто `qbt`.

**Watch folder:** `/mnt/data/storage` — бросить `.torrent`-файл туда, qBittorrent подхватит и удалит.  
**Download path:** `/mnt/data/storage/Downloads`
