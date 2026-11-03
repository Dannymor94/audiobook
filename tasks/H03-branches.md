---
id: H03
title: свести ветки — port-validated-settings → main, судьба gamebox-wip
status: todo
owner:
machine: human
order: 1
depends_on: []
---
## Зачем
`port-validated-settings` на ~72 коммита впереди `main`; в `main` свой отдельный
коммит pron-test; `gamebox-wip` не влит (правки config, pronounce.yaml в корне, логи).

## Решить (Антон)
1. Слить `port-validated-settings` в `main` через PR (после H02).
2. `gamebox-wip`: что из правок нужно — перенести задачей; остальное закрыть.

## Отчёт
