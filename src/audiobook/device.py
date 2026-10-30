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


def threads_per_worker(workers: int, override: int | None = None) -> int:
    """torch threads for one worker: ``render.cpu_threads`` if set, else the
    logical CPU count split between the workers."""
    if override:
        return max(1, int(override))
    return max(1, (os.cpu_count() or 4) // max(1, workers))


def configure_cpu_threads(workers: int, override: int | None = None) -> None:
    """Потоки torch делим между процессами-воркерами, иначе они друг друга душат.
    ``override`` (render.cpu_threads) задаёт число потоков на воркер явно."""
    import torch

    torch.set_num_threads(threads_per_worker(workers, override))
