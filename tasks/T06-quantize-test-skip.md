---
id: T06
title: int8-тесты пропускать, если в torch нет движка квантизации
status: done
owner: codex-gpt-6
agent: codex
machine: code
branch: task/T06
order: 1
depends_on: []
---
## Зачем
На Mac `tests/test_quantize.py` падает 2 тестами (`NoQEngine`): torch собран без
движка квантизации. Правило «pytest зелёный перед сдачей» нарушается у каждого агента.
Int8 отложен ещё в G03, тест должен проверяться только там, где движок есть.

## Сделать
В `tests/test_quantize.py` — `pytest.mark.skipif`: в
`torch.backends.quantized.supported_engines` нет ни одного движка, кроме `"none"`.
Причина пропуска — по-русски. Больше ничего не менять.

## Правила
CLAUDE.md проекта (для Codex — через AGENTS.md) и раздел «Правило для новых механик»
в tasks/README.md: по умолчанию поведение не меняется, хеши чанков те же. Без новых
зависимостей. Тесты слоя 1 на плейсхолдерах во tmp_path, не на цитатах книги.
Трогать только файлы этой задачи (+ свой блок в `__main__.py`, если нужна подкоманда).

## Отчёт

Заметки агента: по уточнению пользователя проверена autouse-фикстура с выбором
первого поддерживаемого движка и восстановлением исходного после каждого теста.
Выставленный движок: `qnnpack` (исходный: `none`, supported_engines: `['qnnpack']`).
Квантизация прошла, но восстановление `none` упало на teardown:
`RuntimeError: quantized engine NoQEngine is not supported`.
Поэтому применён согласованный запасной вариант: два теста реальной квантизации
пропускаются также при активном `engine == "none"`, причина по-русски.
Фикстура не оставлена: восстановить исходный движок в этой сборке невозможно.
Код приложения, конфиг, зависимости и хеши чанков не менялись.

Пробный `uv run pytest -q` с фикстурой (дословно):

```text
...................................................s.................... [ 13%]
........................................................................ [ 26%]
........................................................................ [ 39%]
........................................................................ [ 52%]
...........................................E............................ [ 64%]
....................................................ss.................. [ 77%]
........................................................................ [ 90%]
..................................................                       [100%]
==================================== ERRORS ====================================
________ ERROR at teardown of test_quantize_default_none_and_validation ________

    @pytest.fixture(autouse=True)
    def quantization_engine():
        previous = torch.backends.quantized.engine
        available = [e for e in torch.backends.quantized.supported_engines if e != "none"]
        try:
            if previous == "none" and available:
                torch.backends.quantized.engine = available[0]
            yield
        finally:
>           torch.backends.quantized.engine = previous
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_quantize.py:29: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <torch.backends.quantized._QEngineProp object at 0x1346055d0>
obj = <module 'torch.backends.quantized' from '/Users/danny/Documents/audiobook/.venv/lib/python3.11/site-packages/torch/backends/quantized/__init__.py'>
val = 'none'

    def __set__(self, obj, val: str) -> None:
>       torch._C._set_qengine(_get_qengine_id(val))
E       RuntimeError: quantized engine NoQEngine is not supported

.venv/lib/python3.11/site-packages/torch/backends/quantized/__init__.py:37: RuntimeError
=============================== warnings summary ===============================
tests/test_quantize.py::test_load_model_int8_real_quantize_swaps_linear
tests/test_quantize.py::test_load_model_cache_keyed_by_quantize
  /Users/danny/Documents/audiobook/src/audiobook/synth.py:124: DeprecationWarning: torch.ao.quantization is deprecated and will be removed in 2.10. 
  For migrations of users: 
  1. Eager mode quantization (torch.ao.quantization.quantize, torch.ao.quantization.quantize_dynamic), please migrate to use torchao eager mode quantize_ API instead 
  2. FX graph mode quantization (torch.ao.quantization.quantize_fx.prepare_fx,torch.ao.quantization.quantize_fx.convert_fx, please migrate to use torchao pt2e quantization API instead (prepare_pt2e, convert_pt2e) 
  3. pt2e quantization has been migrated to torchao (https://github.com/pytorch/ao/tree/main/torchao/quantization/pt2e) 
  see https://github.com/pytorch/ao/issues/2259 for more details
    model.model = torch.ao.quantization.quantize_dynamic(

tests/test_quantize.py::test_load_model_int8_real_quantize_swaps_linear
tests/test_quantize.py::test_load_model_cache_keyed_by_quantize
  /Users/danny/Documents/audiobook/.venv/lib/python3.11/site-packages/torch/ao/quantization/quantize.py:570: DeprecationWarning: torch.ao.quantization is deprecated and will be removed in 2.10. 
  For migrations of users: 
  1. Eager mode quantization (torch.ao.quantization.quantize, torch.ao.quantization.quantize_dynamic), please migrate to use torchao eager mode quantize_ API instead 
  2. FX graph mode quantization (torch.ao.quantization.quantize_fx.prepare_fx,torch.ao.quantization.quantize_fx.convert_fx, please migrate to use torchao pt2e quantization API instead (prepare_pt2e, convert_pt2e) 
  3. pt2e quantization has been migrated to torchao (https://github.com/pytorch/ao/tree/main/torchao/quantization/pt2e) 
  see https://github.com/pytorch/ao/issues/2259 for more details
    convert(model, mapping, inplace=True)

tests/test_quantize.py::test_load_model_int8_real_quantize_swaps_linear
  /Users/danny/Documents/audiobook/.venv/lib/python3.11/site-packages/torch/ao/nn/quantized/modules/utils.py:72: UserWarning: torch.quantize_per_tensor, torch.quantize_per_channel and other quantized tensor creation functions that produce tensors with dtype torch.quint8, torch.qint8, and torch.qint32 are deprecated and will be removed in a future PyTorch release. Please see https://github.com/pytorch/pytorch/issues/184982 for more information. (Triggered internally at /Users/runner/work/pytorch/pytorch/aten/src/ATen/quantized/Quantizer.cpp:116.)
    qweight = torch.quantize_per_tensor(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR tests/test_quantize.py::test_quantize_default_none_and_validation - Run...
550 passed, 3 skipped, 5 warnings, 1 error in 13.08s
```

Итоговый `uv run pytest -q` (дословно):

```text
...................................................s.................... [ 13%]
........................................................................ [ 26%]
........................................................................ [ 39%]
........................................................................ [ 52%]
..................................................s..s.................. [ 65%]
...................................................ss................... [ 78%]
........................................................................ [ 91%]
.................................................                        [100%]
548 passed, 5 skipped in 15.56s
```
