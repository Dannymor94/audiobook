---
id: G01
title: что за видеокарта на gamebox и можно ли на ней озвучивать
status: todo
owner:
machine: gamebox
depends_on: []
---
## Шаги (только чтение, ничего не устанавливать)
1. `./run.sh preflight` если уже есть; иначе `uptime; free -g`.
2. Вывод дословно:
   lspci | grep -iE "vga|3d|display"
   ls -la /dev/kfd /dev/dri 2>&1
   which rocminfo rocm-smi nvidia-smi vulkaninfo 2>&1
   rocminfo 2>/dev/null | grep -iE "name|gfx" | head -20
   vulkaninfo --summary 2>/dev/null | head -40
   cat /etc/systemd/system/llama-server.service.d/*.conf 2>/dev/null | grep -i -E "ngl|vulkan|rocm|hip" ; ls ~/llama/llama.cpp/build/bin | head
   groups
   uv run python -c "import torch;print(torch.__version__, torch.cuda.is_available(), getattr(torch.version,'hip',None))"
3. Ничего не ставить и не менять.

## Отчёт
