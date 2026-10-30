# Скрипты для Mac

Оба скрипта только **читают** gamebox и только **добавляют** файлы на Mac:
ничего не удаляют и не перемещают ни там, ни здесь. Доступ к gamebox — по ssh
(`ssh gamebox` должен входить без пароля, по ключу).

- `fetch_results.sh` — забрать результаты для прослушивания (mp3, отчёты, без wav)
  в `~/Downloads/audiobook/<дата>/`.
- `backup_gamebox.sh` — резервная копия всего `out/` gamebox в `~/AudiobookBackup/out/`.

## Резервная копия рендера (`backup_gamebox.sh`)

Рендер книги идёт ~3 дня на одном диске gamebox. Скрипт копирует на Mac всё, что
восстанавливать дорого: wav чанков, манифесты, takes, кандидаты redo, json и логи
очереди, mp3 глав, index/sync/suspects.

Не копируется: недописанные `*.part` / `*.tmp`, `out/export/_old/`,
`out/listen/chunks/` (пересобирается из чанков), замок `out/queue/heavy.lock`.

Копия **только дополняется**: `--delete` не используется никогда. Файл, удалённый
или ставший orphan на gamebox, в копии остаётся. Место на Mac растёт — чистить
`~/AudiobookBackup` при необходимости человек решает сам.

```bash
scripts/mac/backup_gamebox.sh --dry-run     # что было бы скопировано, ничего не пишет
scripts/mac/backup_gamebox.sh               # копия с хоста gamebox
scripts/mac/backup_gamebox.sh otherhost     # другой хост из ~/.ssh/config
```

В конце — одна строка: время, сколько файлов и байт перенесено. Два запуска
одновременно не идут: второй видит замок `~/AudiobookBackup/.backup.lock` и
пропускает ход. Замок от прерванного запуска (выключили Mac) снимается сам при
следующем запуске.

Первый запуск долгий (все wav), дальше переносятся только новые и изменённые файлы.

### Автозапуск каждые 3 часа (launchd)

Шаблон `com.audiobook.backup.plist.template` — агент launchd: запуск при входе
в систему и каждые 3 часа (`StartInterval` 10800), лог в
`~/AudiobookBackup/backup.log`. Это настройка Mac для человека, не часть пайплайна.

Установка (один раз):

```bash
cd путь/к/клону/audiobook
mkdir -p ~/Library/LaunchAgents ~/AudiobookBackup
cp scripts/mac/com.audiobook.backup.plist.template ~/Library/LaunchAgents/com.audiobook.backup.plist
```

Открой `~/Library/LaunchAgents/com.audiobook.backup.plist` и замени
`PATH_TO_AUDIOBOOK` на полный путь к клону (вывод `pwd` в его корне). Затем:

```bash
plutil -lint ~/Library/LaunchAgents/com.audiobook.backup.plist   # → OK
launchctl load ~/Library/LaunchAgents/com.audiobook.backup.plist
```

Проверка:

```bash
launchctl list | grep com.audiobook.backup    # есть строка; второй столбец 0 = последний запуск успешен
tail -n 20 ~/AudiobookBackup/backup.log       # строки «бэкап gamebox:… файлов N, байт M»
```

Если в логе `Permission denied` / `Host key verification failed` — ssh из фона
не смог войти: проверь, что `ssh gamebox true` проходит в терминале без вопросов
(ключ в ssh-agent / Keychain, хост уже в `known_hosts`). Скрипт запускает ssh
с `BatchMode=yes`, поэтому не зависает на запросе пароля, а сразу пишет ошибку.

Если Mac спал во время запуска, launchd запустит пропущенный раз после пробуждения.

Остановить / выключить:

```bash
launchctl unload ~/Library/LaunchAgents/com.audiobook.backup.plist
```

После правки plist — `unload`, затем снова `load`. Убрать совсем — `unload` и
удалить файл plist из `~/Library/LaunchAgents` (сама копия в `~/AudiobookBackup`
при этом остаётся).

### Восстановление на gamebox (аварийно)

Если на gamebox пропал или испорчен `out/` (новый диск, переустановка), вернуть копию
обратно — **без `--delete`** и сначала пробным прогоном:

```bash
# на gamebox очередь должна стоять: systemctl --user stop audiobook-queue
rsync -a --dry-run --stats ~/AudiobookBackup/out/ gamebox:audiobook/out/
rsync -a           --stats ~/AudiobookBackup/out/ gamebox:audiobook/out/
```

- Никогда не добавлять `--delete`: это удалит на gamebox всё, чего нет в копии,
  в том числе отрендеренное после последнего бэкапа.
- По умолчанию rsync перезапишет файл на gamebox, если в копии он отличается.
  Чтобы не трогать файлы, которые на gamebox уже есть, — добавь `--ignore-existing`.
- После восстановления на gamebox: `./run.sh status` и `./run.sh queue list`;
  затем `systemctl --user start audiobook-queue`. Лишние (orphan) wav из копии
  убирает механизм rehash/orphan пайплайна, а не ручное удаление.
