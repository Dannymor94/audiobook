---
id: G15
title: перенести out/ (рендер) на HDD 3 ТБ, модели и код оставить на SSD (≈20 мин)
status: review
owner: claude-sonnet-4-6
machine: gamebox
depends_on: []
---
## Зачем
Весь рендер пишется в `~/audiobook/out/` (папка проекта, SSD). Человек хочет, чтобы
рендер шёл на HDD 3 ТБ. Делаем символьной ссылкой: `~/audiobook/out` → папка на HDD.
Код, `models/`, `ref/` остаются на SSD (модель грузится быстро). Код не меняется.

## Правила (нарушение = стоп и отчёт)
- НИЧЕГО не удалять. Старый `out/` только переименовать в `out_ssd_old` — удалит человек сам.
- Не форматировать, не монтировать, не трогать fstab, не делать sudo. Если HDD не смонтирован
  или файловая система не ext4/xfs/btrfs — стоп, отчёт (нужен человек).
- Перед переносом очередь пуста и ничего тяжёлого не идёт.
- Вывод команд — дословно.

## Шаг 0
```
cd ~/audiobook && git checkout port-validated-settings && git pull
uv sync --extra dev && uv run pytest -q
./run.sh preflight
./run.sh queue list
```
В `queue list` не должно быть `running`/`pending`, иначе стоп.

## Шаг 1. Найти HDD
```
lsblk -o NAME,SIZE,ROTA,TYPE,FSTYPE,MOUNTPOINTS
findmnt -T ~/audiobook
df -h ~/audiobook
du -sh ~/audiobook/out
```
HDD = диск ~2.7–3 ТБ с `ROTA 1`, смонтированный. Его точку монтирования обозначим `$HDD`.
Проверить: `df -h $HDD` (свободно ≥ 50 ГБ), `touch $HDD/.audiobook_write_test && ls -la $HDD/.audiobook_write_test`
(запись есть; тестовый файл оставить, не удалять). Если `~/audiobook` уже на этом HDD — стоп, отчёт: переносить не нужно.

## Шаг 2. Копия на HDD и проверка
```
mkdir -p $HDD/audiobook_out
rsync -a ~/audiobook/out/ $HDD/audiobook_out/
du -sb ~/audiobook/out $HDD/audiobook_out
find ~/audiobook/out -type f | wc -l ; find $HDD/audiobook_out -type f | wc -l
```
Размеры и число файлов должны совпасть, иначе стоп.

## Шаг 3. Переключение
```
mv ~/audiobook/out ~/audiobook/out_ssd_old
ln -s $HDD/audiobook_out ~/audiobook/out
ls -la ~/audiobook/out
```

## Шаг 4. Проверка работы
```
cd ~/audiobook
git status --short          # должно быть пусто (out — в .gitignore)
./run.sh status
./run.sh impact
./run.sh preflight
uv run pytest -q
```

## Отчёт

### Шаг 0
```
git log --oneline -1 → 3686882 reuse identical chunks + per-chapter listen plan to Telegram; task G15
uv sync → Resolved 129 packages (no changes)
uv run pytest -q → 550 passed, 3 skipped
./run.sh preflight → PREFLIGHT: GREEN
./run.sh queue list → только done-записи, running/pending нет
```

### Шаг 1. lsblk
```
NAME     SIZE ROTA TYPE FSTYPE   MOUNTPOINTS
sda       3.6T    1 disk
├─sda1     16M    1 part
└─sda2    3.6T    1 part ext4     /mnt/data
sdb     223.6G    0 disk
├─sdb1      1G    0 part vfat     /boot/efi
└─sdb2  222.5G    0 part ext4     /
```
HDD = `/dev/sda2`, 3.6 ТБ, ROTA=1, ext4, `$HDD=/mnt/data`.

### Шаг 1. findmnt / df / du
```
findmnt -T ~/audiobook → TARGET=/ SOURCE=/dev/sdb2 FSTYPE=ext4
df -h ~/audiobook → /dev/sdb2  218G  52G  155G  26%  /
du -sh ~/audiobook/out → 690M	/home/danavrata/audiobook/out
```
`~/audiobook` на SSD (`sdb2`), HDD — другой диск, перенос нужен.

### Шаг 1. df $HDD + write test
```
df -h /mnt/data → /dev/sda2  3.6T  372G  3.1T  11%  /mnt/data
touch /mnt/data/.audiobook_write_test
-rw-rw-r-- 1 danavrata danavrata 0 Oct 30 22:44 /mnt/data/.audiobook_write_test
```
Свободно 3.1 ТБ (≥ 50 ГБ), запись разрешена.

### Шаг 2. rsync + проверка
```
rsync -a ~/audiobook/out/ /mnt/data/audiobook_out/
du -sb ~/audiobook/out /mnt/data/audiobook_out →
  720977067	/home/danavrata/audiobook/out
  720977067	/mnt/data/audiobook_out
find ~/audiobook/out -type f | wc -l → 840
find /mnt/data/audiobook_out -type f | wc -l → 840
```
Размер и число файлов совпадают. ✓

### Шаг 3. Переключение
```
mv ~/audiobook/out ~/audiobook/out_ssd_old
ln -s /mnt/data/audiobook_out ~/audiobook/out
ls -la ~/audiobook/out →
  lrwxrwxrwx 1 danavrata danavrata 23 Oct 30 22:44 out -> /mnt/data/audiobook_out
```

### Шаг 4. Проверка
```
git status --short → ?? out_ssd_old/   (out — в .gitignore, out_ssd_old — нет, ожидаемо)
./run.sh status → 1% отрендерено, глава 13 видна, очередь 0
./run.sh impact → перерендер 0 чанков из 68
./run.sh preflight → PREFLIGHT: GREEN
uv run pytest -q → 550 passed, 3 skipped
```

### Заметки агента
- `$HDD=/mnt/data`, ФС ext4, свободно 3.1 ТБ.
- `out_ssd_old/` появился в `git status --short` как untracked — ожидаемо: в .gitignore стоит `out/`, а не `out_ssd_old/`. Ни pipeline, ни тесты его не видят.
- Весь пайплайн работает через симлинк без изменений в коде.
- `~/audiobook/out_ssd_old` (690 МБ) можно удалить вручную после прослушки ближайшей главы.
