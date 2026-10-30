---
id: G15
title: перенести out/ (рендер) на HDD 3 ТБ, модели и код оставить на SSD (≈20 мин)
status: todo
owner:
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
Вывод всех шагов дословно; `$HDD`, тип ФС, свободное место; размер перенесённого.
Напомнить человеку: `~/audiobook/out_ssd_old` можно удалить вручную после прослушки ближайшей главы.
`status: review`.
