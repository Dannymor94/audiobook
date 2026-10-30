# Очередь как служба на gamebox

`audiobook-queue.service` — пользовательская служба systemd (`systemctl --user`),
которая держит воркер очереди запущенным всегда, в том числе после перезагрузки:

```
./run.sh queue run --watch 60 --requeue-interrupted
```

- `--watch 60` — когда очередь пуста, воркер не выходит, а раз в 60 с проверяет её
  снова. Замок `heavy.lock` держится только пока идёт задача; в простое он свободен,
  и ручная тяжёлая команда (synth, qc, pron-test…) между задачами запускается.
  Пока задача идёт — ручная команда отказывает, как и раньше.
- `--requeue-interrupted` — задача, которую прервала перезагрузка или падение
  воркера, возвращается в очередь (поле `attempts` в её json). После 3 прерываний
  она уходит в done как `interrupted`. Перезапуск безопасен: все шаги рендера
  продолжают с кеша.

> **Внимание.** Пока служба запущена, каждый `./run.sh queue add …`
> (а также `queue section` / `queue redo`) **начинает выполняться сразу**,
> в пределах минуты. Не ставь в очередь то, что не готов запускать прямо сейчас.
> Рендер книги — только после «настройки зафиксированы, запускай» (CLAUDE.md).

Юнит предполагает проект в `~/audiobook` (`%h/audiobook`). Если он лежит
в другой папке — поправь `WorkingDirectory` и `ExecStart` в копии юнита.

## Установка (один раз)

```bash
cd ~/audiobook && git pull
mkdir -p ~/.config/systemd/user
cp scripts/gamebox/audiobook-queue.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now audiobook-queue
```

Чтобы служба работала без открытой ssh-сессии и стартовала после перезагрузки
до входа в систему, нужен linger. Эту команду с `sudo` человек набирает в терминале
сам (агент её не запускает):

```bash
sudo loginctl enable-linger "$USER"
```

Проверка: `loginctl show-user "$USER" --property=Linger` → `Linger=yes`.

После правки юнита: снова `cp …`, затем `systemctl --user daemon-reload` и
`systemctl --user restart audiobook-queue`.

## Управление

```bash
systemctl --user status audiobook-queue      # работает ли, последние строки лога
systemctl --user stop audiobook-queue        # остановить
systemctl --user start audiobook-queue       # запустить
systemctl --user restart audiobook-queue     # перезапустить (после git pull)
systemctl --user disable --now audiobook-queue   # выключить и убрать из автозапуска
```

Логи воркера (какая задача взята, чем закончилась):

```bash
journalctl --user -u audiobook-queue -f            # следить в реальном времени
journalctl --user -u audiobook-queue --since today
```

Вывод самих задач — как и раньше, в `out/queue/logs/<id>.log`;
состояние очереди — `./run.sh queue list`.

## Что важно знать

- `stop` / `restart` прерывают и идущую задачу (systemd завершает всю группу
  процессов). При следующем старте она найдётся как прерванная и вернётся
  в очередь — это засчитывается как одно из 3 прерываний.
- После `git pull` на gamebox служба продолжает работать со старым кодом,
  пока её не перезапустить. Перезапуск лучше делать, когда очередь пуста
  (`./run.sh queue list`).
- Ручной `./run.sh queue run` при запущенной службе не нужен: служба и так
  разберёт очередь. Если запустить его, два воркера не пересекаются —
  их разводит `heavy.lock`.

## Уведомления в Telegram (по желанию)

Воркер очереди может писать в Telegram: задача упала (с последними ~15 строками
её лога), глава готова (успешный `master --section S` без `--first`), задача снята
после 3 прерываний, очередь опустела (один раз за проход и только если что-то
выполнялось — простаивающий `--watch` не пишет ничего).

По умолчанию **выключено**. Это единственный выход пайплайна в сеть, и он
необязателен: без `.env` всё работает как раньше. Если Telegram недоступен,
очередь не встаёт и не падает — в журнал пишется предупреждение, отправка
занимает не больше ~15 с.

1. **Бот.** В Telegram открой `@BotFather` → `/newbot` → имя и username бота.
   BotFather выдаст токен вида `123456789:AA…` — это секрет, никому не пересылай.
2. **Chat id.** Напиши своему боту любое сообщение (иначе бот не сможет тебе
   писать). Затем открой в браузере
   `https://api.telegram.org/bot<токен>/getUpdates` и найди в ответе
   `"chat":{"id":…}` — это число и есть chat id (у групп оно отрицательное).
3. **`.env` на gamebox** — в корне проекта, рядом с `run.sh`. Файл в `.gitignore`
   и в git не попадает. Токен — только здесь, не в `config.yaml` и не в юните.

   ```bash
   cd ~/audiobook
   cat > .env <<'ENV'
   AUDIOBOOK_TG_TOKEN=123456789:AA-замени-на-свой
   AUDIOBOOK_TG_CHAT=123456789
   ENV
   chmod 600 .env
   ```

   Формат — строго `ИМЯ=значение`, без кавычек, пробелов и `export`: файл читают
   и `run.sh` (bash), и systemd (`EnvironmentFile=-%h/audiobook/.env` в юните).
4. **Проверка:**

   ```bash
   ./run.sh notify-test
   ```

   Ответ `GREEN … отправлено` — в чат пришло «проверка связи». `RED …` — причина
   в той же строке (нет переменных, `HTTP 401: Unauthorized` — неверный токен,
   `chat not found` — неверный chat id или боту не написали первым).
   Если `notify-test` ещё нет в `./run.sh --help`, то же самое:
   `set -a; . ./.env; set +a; uv run python -m audiobook.notify`.
5. **Служба** подхватит `.env` после перезапуска: заново `cp` юнита (в нём
   появилась строка `EnvironmentFile`), `systemctl --user daemon-reload`,
   `systemctl --user restart audiobook-queue` — лучше при пустой очереди.

Выключить: удалить или переименовать `.env` (или убрать из него две строки) и
перезапустить службу.
