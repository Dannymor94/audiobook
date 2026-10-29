"""File-based job queue so heavy tasks on the render box never overlap.

Layout (under out/queue/):
    pending/<id>.json   waiting or running jobs
    done/<id>.json      finished jobs (status done | failed | interrupted)
    logs/<id>.log       stdout+stderr of each job
    heavy.lock          held exclusively by a running `queue run` worker

Job json: {id, created, args, status, exit_code, ...}. Jobs are ordered by id,
which starts with a zero-padded nanosecond timestamp.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from . import paths

GUARDED = ("synth", "chunk")          # never queued for the whole book
Runner = Callable[[dict, Path], int]


def queue_root() -> Path:
    return paths.OUT / "queue"


def _dirs(root: Path) -> tuple[Path, Path, Path]:
    pending, done, logs = root / "pending", root / "done", root / "logs"
    for d in (pending, done, logs):
        d.mkdir(parents=True, exist_ok=True)
    return pending, done, logs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict) -> None:
    """Atomic: temp file in the same folder, then rename."""
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ validation

def validate_args(args: list[str]) -> str | None:
    """Reason for rejecting the job, or None if it may be queued."""
    if not args:
        return "пустая команда"
    cmd = args[0]
    if cmd == "queue":
        return "queue внутри очереди зависнет на собственном замке"
    if cmd in GUARDED:
        has_section = any(
            (a == "--section" and i + 1 < len(args) and args[i + 1] and not args[i + 1].startswith("-"))
            or (a.startswith("--section=") and len(a) > len("--section="))
            for i, a in enumerate(args))
        if not has_section:
            return f"{cmd} без --section — это рендер всей книги, в очередь нельзя"
    return None


# --------------------------------------------------------------------- storage

def add_job(args: list[str], root: Path | None = None) -> dict:
    root = root or queue_root()
    args = list(args)
    if args and args[0] == "--":
        args = args[1:]
    reason = validate_args(args)
    if reason:
        raise ValueError(reason)
    pending, _, _ = _dirs(root)
    job_id = f"{time.time_ns():020d}-{uuid.uuid4().hex[:4]}"
    job = {"id": job_id, "created": _now(), "args": args, "status": "pending", "exit_code": None}
    _write_json(pending / f"{job_id}.json", job)
    return job


def list_jobs(root: Path | None = None) -> list[dict]:
    """Pending/running jobs in run order, then finished ones in finish order."""
    root = root or queue_root()
    pending, done, _ = _dirs(root)
    out: list[dict] = []
    for d in (pending, done):
        for p in sorted(d.glob("*.json")):
            try:
                out.append(_read_json(p))
            except (OSError, ValueError):
                out.append({"id": p.stem, "args": [], "status": "unreadable", "exit_code": None})
    return out


def _next_pending(pending: Path, skip: set[str]) -> dict | None:
    for p in sorted(pending.glob("*.json")):
        if p.stem in skip:
            continue
        try:
            job = _read_json(p)
        except (OSError, ValueError):
            skip.add(p.stem)
            continue
        if job.get("status") == "pending":
            return job
        skip.add(p.stem)
    return None


# ------------------------------------------------------------------------ lock

def _try_lock(fh) -> bool:
    if sys.platform == "win32":
        import msvcrt
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh) -> None:
    if sys.platform == "win32":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def exclusive_lock(path: Path, poll: float = 0.5,
                   on_wait: Callable[[], None] | None = None) -> Iterator[None]:
    """Block until we hold the exclusive lock on `path`; released on exit or crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+", encoding="utf-8")
    try:
        waited = False
        while not _try_lock(fh):
            if not waited and on_wait:
                on_wait()
            waited = True
            time.sleep(poll)
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()


# ---------------------------------------------------------------------- worker

def subprocess_runner(job: dict, log_path: Path) -> int:
    """Run `python -m audiobook <args>` with output appended to the job log."""
    cmd = [sys.executable, "-m", "audiobook", *job["args"]]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        return subprocess.run(cmd, cwd=str(paths.ROOT), stdout=log, stderr=subprocess.STDOUT,
                              env=env).returncode


def run_worker(root: Path | None = None, runner: Runner | None = None, poll: float = 0.5,
               say: Callable[[str], None] = print) -> int:
    """Take pending jobs one by one under the heavy lock until none are left.

    Returns 0 if every job passed, 1 if any failed or was found interrupted.
    """
    root = root or queue_root()
    runner = runner or subprocess_runner
    pending, done, logs = _dirs(root)
    failed = 0
    with exclusive_lock(root / "heavy.lock", poll=poll,
                        on_wait=lambda: say("замок heavy.lock занят другим воркером, жду…")):
        # The lock is ours, so a job still marked running belongs to a dead worker.
        for p in sorted(pending.glob("*.json")):
            try:
                job = _read_json(p)
            except (OSError, ValueError):
                continue
            if job.get("status") == "running":
                job.update(status="interrupted", exit_code=None, finished=_now())
                _write_json(done / p.name, job)
                p.unlink()
                failed += 1
                say(f"{job['id']}: прерван (воркер упал?) — перенесён в done как interrupted")

        skip: set[str] = set()
        while True:
            job = _next_pending(pending, skip)
            if job is None:
                break
            path = pending / f"{job['id']}.json"
            job.update(status="running", started=_now())
            _write_json(path, job)
            say(f"{job['id']}: {' '.join(job['args'])}")
            log_path = logs / f"{job['id']}.log"
            try:
                code = int(runner(job, log_path))
            except Exception as e:  # noqa: BLE001
                code = -1
                job["error"] = f"{type(e).__name__}: {e}"
            job.update(exit_code=code, status="done" if code == 0 else "failed", finished=_now())
            _write_json(done / path.name, job)
            path.unlink()
            if code != 0:
                failed += 1
            say(f"{job['id']}: {job['status']} (код {code})")
    say("очередь пуста" if not failed else f"очередь пуста, с ошибками: {failed}")
    return 1 if failed else 0


# ------------------------------------------------------------------------- CLI

def cli(sub: str, args: list[str]) -> int:
    if sub == "add":
        try:
            job = add_job(args)
        except ValueError as e:
            print(f"отклонено: {e}", file=sys.stderr)
            return 2
        print(f"в очереди: {job['id']}  {' '.join(job['args'])}")
        return 0
    if sub == "list":
        jobs = list_jobs()
        if not jobs:
            print("очередь пуста")
        for j in jobs:
            code = "" if j.get("exit_code") is None else f" код={j['exit_code']}"
            print(f"{j['id']}  {j.get('status', '?'):<11}{code}  {' '.join(j.get('args', []))}")
        return 0
    if sub == "run":
        return run_worker()
    print(f"queue {sub}: неизвестная подкоманда", file=sys.stderr)
    return 2
