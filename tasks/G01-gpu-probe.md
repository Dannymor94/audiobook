---
id: G01
title: что за видеокарта на gamebox и можно ли на ней озвучивать
status: review
owner: claude-sonnet-4-6
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

### preflight
`preflight` команда отсутствует. Выполнено `uptime; free -g`:
```
10:56:03 up  1:45,  3 users,  load average: 0.41, 0.58, 0.75
               total        used        free      shared  buff/cache   available
Mem:              30           1           0           0          29          29
Swap:              7           0           7
```

### lspci | grep -iE "vga|3d|display"
```
2b:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Ellesmere [Radeon RX 470/480/570/570X/580/580X/590] (rev e7)
```

### ls -la /dev/kfd /dev/dri
```
crw-rw----+ 1 root render 236, 0 Oct 29 09:10 /dev/kfd

/dev/dri:
total 0
drwxr-xr-x   3 root root        100 Oct 29 09:10 .
drwxr-xr-x  20 root root       4580 Oct 29 09:10 ..
drwxr-xr-x   2 root root        100 Oct 29 09:10 by-path
crw-rw----+  1 root video  226,   1 Oct 29 09:10 card1
crw-rw----+  1 root render 226, 128 Oct 29 09:10 renderD128
```

### which rocminfo rocm-smi nvidia-smi vulkaninfo
```
/usr/bin/vulkaninfo
```
(rocminfo, rocm-smi, nvidia-smi — не найдены)

### rocminfo | grep -iE "name|gfx"
```
(нет вывода — rocminfo отсутствует)
```

### vulkaninfo --summary | head -40
```
==========
VULKANINFO
==========

Vulkan Instance Version: 1.4.341

Instance Extensions: count = 26
...
VK_KHR_wayland_surface, VK_KHR_xcb_surface, VK_KHR_xlib_surface ...
(полный список в теле команды выше)
```

### llama-server service conf + build/bin
```
ExecStart=/home/danavrata/llama/llama.cpp/build/bin/llama-server -m /mnt/data/llm-models/Qwen3.8-27B-IQ4_XS.gguf -ngl 24 -t 8 -c 16384 -fa on -ctk q8_0 -ctv q8_0 --jinja --host 0.0.0.0 --port 8081
libggml-base.so
libggml-base.so.0
...
libggml-vulkan.so
libggml-vulkan.so.0
libggml-vulkan.so.0.26.0
libggml.so
```

### groups
```
danavrata adm cdrom sudo dip video plugdev users lxd render input
```

### torch
```
2.14.0+cu130 False None
```
(версия CUDA-сборки, но `cuda.is_available()=False`, HIP=None)

### Заметки агента

GPU — AMD Radeon RX 580 (Ellesmere/Polaris, gfx803). `/dev/kfd` присутствует, пользователь в группах `render` и `video`. ROCm-утилит нет — они не установлены. llama.cpp собран с Vulkan-бэкендом и успешно офлоадит 24 слоя Qwen на эту карту.

PyTorch в окружении audiobook (`2.14.0+cu130`) — CUDA-сборка, но видит 0 CUDA-устройств и HIP отсутствует. Значит, XTTS/CoquiTTS работают только на CPU.

Для PyTorch + RX 580: официальный ROCm прекратил поддержку gfx803 на 6.x. Варианты — ROCm 5.7 или unofficial wheel с патчем для Polaris. Vulkan-бэкенд PyTorch (torch-directml / torch.vulkan) — нестабилен и не поддерживает XTTS. Практический вывод: в обозримой перспективе рендер остаётся на CPU; GPU задействован только для llama.
