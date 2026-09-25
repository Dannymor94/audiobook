"""Process-isolated synthesis with a per-chunk wall-clock timeout.

A single stuck generation must not kill the batch. Synthesis runs in a
persistent child process (the model is loaded once, reused across chunks); the
parent enforces the timeout by reading the result with a deadline. On timeout
the parent KILLS the child process itself (terminate, then kill) and respawns
it for the next chunk — this is the portable way, unlike ``signal.alarm`` which
is POSIX/main-thread only. Everything crossing the boundary is picklable and
the context is ``spawn`` (Windows-safe).
"""
from __future__ import annotations

import multiprocessing as mp
import queue as _queue
from typing import Any, Callable

import numpy as np


def _worker_loop(cfg: dict, in_q, out_q) -> None:
    """Child entry point: load model+latents once, then synth tasks on demand.

    Module-level so ``spawn`` can import it in the child. Sends "ready" once the
    model is loaded, then for each task a {"ok": True, "wav": ndarray} or
    {"ok": False, "error": repr}. A ``None`` task ends the loop.
    """
    # Pin the BLAS backend's thread count BEFORE torch is imported. On macOS
    # torch uses Accelerate/vecLib, whose threading is NOT governed by
    # torch.set_num_threads but by these env vars; a spawn child otherwise picks
    # its own (QoS/core-dependent) count, so its FP reduction order — hence the
    # logits, hence sampling — diverges from the in-process audition harness, and
    # a generation near the open-end runaway boundary hangs in the worker while it
    # terminates in-process. Fixing the count makes the worker reproduce the
    # audition. os.cpu_count() matches the calibration/audition environment.
    import os as _os

    _n = str(_os.cpu_count() or 4)
    for _var in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS",
                 "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        _os.environ[_var] = _n

    from audiobook.device import configure_cpu_threads
    from audiobook.synth import (
        CapExceeded, load_latents, load_model, max_tokens_for_text, synthesize,
    )

    configure_cpu_threads(workers=cfg.get("num_workers", 1))
    model = load_model(cfg["device"])
    latents = load_latents(cfg["latents_path"])
    cap = cfg.get("cap")  # {base_ms, ms_per_char, margin} or None to disable
    out_q.put("ready")
    while True:
        task = in_q.get()
        if task is None:
            return
        try:
            mnt = max_tokens_for_text(task["text"], **cap) if cap else None
            wav = synthesize(
                model, task["text"], latents, task["seed"],
                cfg["temperature"], cfg["language"], max_new_tokens=mnt,
            )
            out_q.put({"ok": True, "wav": np.asarray(wav, dtype=np.float32)})
        except CapExceeded as e:  # runaway hit the length cap → cheap retry, worker stays up
            out_q.put({"ok": False, "cap_hit": True, "error": repr(e)})
        except Exception as e:  # report, do not crash the worker
            out_q.put({"ok": False, "error": repr(e)})


class TimeoutSynth:
    """Persistent synth worker with a per-call timeout.

    ``synth(text, seed)`` returns the wav, or ``None`` for a failed generation
    to retry with another seed: either the output saturated the per-chunk length
    cap (a runaway caught cheaply; worker stays up) or the call exceeded
    ``timeout_s`` (last-resort guard; the child is killed and respawned).
    Use as a context manager, or call ``close()``.
    """

    def __init__(
        self,
        cfg: dict,
        timeout_s: float,
        target: Callable = _worker_loop,
        start_timeout_s: float = 900,
    ) -> None:
        self._cfg = cfg
        self._timeout_s = timeout_s
        self._target = target
        self._start_timeout_s = start_timeout_s
        self._ctx = mp.get_context("spawn")
        self._p: Any = None
        self._start()

    def _start(self) -> None:
        self._in = self._ctx.Queue()
        self._out = self._ctx.Queue()
        self._p = self._ctx.Process(
            target=self._target, args=(self._cfg, self._in, self._out), daemon=True
        )
        self._p.start()
        try:
            msg = self._out.get(timeout=self._start_timeout_s)
        except _queue.Empty:
            self._kill()
            raise RuntimeError("synth worker failed to start (model load timed out)")
        if msg != "ready":
            raise RuntimeError(f"unexpected worker startup message: {msg!r}")

    def synth(self, text: str, seed: int) -> np.ndarray | None:
        self._in.put({"text": text, "seed": seed})
        try:
            res = self._out.get(timeout=self._timeout_s)
        except _queue.Empty:
            self._kill()
            self._start()  # respawn (reloads model) for the next chunk
            return None
        if not res["ok"]:
            if res.get("cap_hit"):
                return None  # runaway capped in seconds; worker alive, retry next seed
            raise RuntimeError(f"synth failed: {res['error']}")
        return res["wav"]

    def _kill(self) -> None:
        if self._p is None:
            return
        self._p.terminate()
        self._p.join(5)
        if self._p.is_alive():
            self._p.kill()
            self._p.join()

    def close(self) -> None:
        try:
            if self._p is not None and self._p.is_alive():
                self._in.put(None)
                self._p.join(5)
        except Exception:
            pass
        self._kill()

    def __enter__(self) -> "TimeoutSynth":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
