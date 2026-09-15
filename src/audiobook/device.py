from __future__ import annotations

import os


def pick_device(requested: str | None = None) -> str:
    """auto -> cuda > mps > cpu. На Windows/Ryzen всегда cpu. MPS у XTTS частичный — для репетиции переезда гоняйте cpu."""
    import torch

    want = (requested or os.environ.get("AUDIOBOOK_DEVICE", "auto")).lower()
    if want != "auto":
        return want
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def configure_cpu_threads(workers: int) -> None:
    """Потоки torch делим между процессами-воркерами, иначе они друг друга душат."""
    import torch

    phys = os.cpu_count() or 4
    torch.set_num_threads(max(1, phys // max(1, workers)))
