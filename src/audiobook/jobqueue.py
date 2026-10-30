"""File-based job queue so heavy tasks on the render box never overlap.

Layout (under out/queue/):
    pending/<id>.json   waiting or running jobs
    done/<id>.json      finished jobs (status done | failed | interrupted)
    logs/<id>.log       stdout+stderr of each job
    heavy.lock          held exclusively by a running `queue run` worker

Job json: {id, created, args, config, status, exit_code, pid, ...}. Jobs are
ordered by id, which starts with a zero-padded nanosecond timestamp.

``config`` is fixed at `queue add` time (AUDIOBOOK_CONFIG or config.yaml) and
handed to the child, so the worker's own environment never changes which
config a job runs with. ``pid`` is the child's pid while it runs: a job found
"running" after a worker crash is marked interrupted only if that pid is gone;
if the child is still alive the worker starts nothing and says so.

Crash order: done/<id>.json is written (temp + rename) before pending/<id>.json
is removed; a pending file whose done/ twin exists is a leftover and is dropped.

`queue run --requeue-interrupted`: a job found "running" with a dead pid (the
box rebooted) goes back to pending with ``attempts`` += 1 instead of to done;
after MAX_INTERRUPTED interruptions it is moved to done as interrupted.
`queue run --watch N`: after the queue drains, poll it every N seconds forever,
holding heavy.lock only while jobs run (scripts/gamebox/audiobook-queue.service).

Notifications (``notifier``, default notify.send — a no-op unless the Telegram
env vars are set): a failed job (with its log tail), a successful full-section
``master`` (chapter ready), a job moved to done as interrupted, and the queue
running dry — once per drain and only if something ran, so an idle --watch
worker stays silent. A notifier error never reaches the queue.
"""
from __future__ import annotations

import argparse
import contextlib
import inspect
import io
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

from . import notify, paths

GUARDED = ("synth", "chunk")          # never queued for the whole book
DEFAULT_CONFIG = "config.yaml"
CONFIG_ENV = "AUDIOBOOK_CONFIG"
Runner = Callable[..., int]           # (job, log_path[, on_start=callable(pid)]) -> exit code
MAX_INTERRUPTED = 3                   # requeue_interrupted: give up after this many
Notifier = Callable[[str], object]    # text -> sent? ; must not block for long


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

def _main_module():
    from . import __main__ as main_mod
    return main_mod


def _real_parser() -> argparse.ArgumentParser | None:
    """The CLI parser of audiobook.__main__ if it exposes a builder."""
    build = getattr(_main_module(), "build_parser", None)
    return build() if callable(build) else None


def _minimal_parser(cmd: str) -> argparse.ArgumentParser:
    """Stand-in while __main__ has no parser builder: only --section, with
    argparse semantics (last occurrence wins, --section=X, abbreviations,
    a missing value is an error); other options are left to the child."""
    p = argparse.ArgumentParser(prog=f"audiobook {cmd}", add_help=False)
    p.add_argument("--section", default=None)
    return p


def _parse(parser: argparse.ArgumentParser, args: list[str],
           known_only: bool) -> tuple[argparse.Namespace | None, str]:
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            ns = parser.parse_known_args(args)[0] if known_only else parser.parse_args(args)
    except SystemExit:
        lines = [ln for ln in err.getvalue().splitlines() if ln.strip()]
        return None, lines[-1] if lines else "аргументы не разбираются"
    return ns, ""


def validate_args(args: list[str], config: str | None = None) -> str | None:
    """Reason for rejecting the job, or None if it may be queued."""
    if not args:
        return "пустая команда"
    cmd = args[0]
    if cmd == "queue":
        return "queue внутри очереди зависнет на собственном замке"
    real = _real_parser()
    if real is not None:
        ns, why = _parse(real, args, known_only=False)
        if ns is None:
            return f"не разбирается парсером audiobook: {why}"
        section = getattr(ns, "section", None)
    elif cmd in GUARDED:
        ns, why = _parse(_minimal_parser(cmd), args[1:], known_only=True)
        if ns is None:
            return f"{cmd}: {why}"
        section = ns.section
    else:
        section = None
    if cmd in GUARDED and not (section or "").strip():
        return f"{cmd} без --section (или с пустым) — это рендер всей книги, в очередь нельзя"
    main_only = getattr(_main_module(), "_MAIN_CONFIG_ONLY", set())
    if config not in (None, DEFAULT_CONFIG) and cmd in main_only:
        return (f"{cmd} с {CONFIG_ENV}={config}: команда пишет в кеш и манифесты книги "
                "и работает только с config.yaml")
    return None


def config_at_add() -> str:
    """The config a job added now must run with."""
    return os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG


# --------------------------------------------------------------------- storage

def add_job(args: list[str], root: Path | None = None) -> dict:
    root = root or queue_root()
    args = list(args)
    if args and args[0] == "--":
        args = args[1:]
    config = config_at_add()
    reason = validate_args(args, config)
    if reason:
        raise ValueError(reason)
    pending, _, _ = _dirs(root)
    job_id = f"{time.time_ns():020d}-{uuid.uuid4().hex[:4]}"
    job = {"id": job_id, "created": _now(), "args": args, "config": config,
           "status": "pending", "exit_code": None}
    _write_json(pending / f"{job_id}.json", job)
    return job


def list_jobs(root: Path | None = None) -> list[dict]:
    """Pending/running jobs in run order, then finished ones in finish order."""
    root = root or queue_root()
    pending, done, _ = _dirs(root)
    out: list[dict] = []
    finished = {p.name for p in done.glob("*.json")}
    for d in (pending, done):
        for p in sorted(d.glob("*.json")):
            if d is pending and p.name in finished:
                continue  # crash leftover: the job is already in done/
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


LOCK_HELD_ENV = "AUDIOBOOK_LOCK_HELD"  # set by `queue run` for its child jobs


@contextmanager
def heavy_command_lock(name: str) -> Iterator[None]:
    """Non-blocking heavy.lock for a heavy command run by hand (synth, qc, chunk…).
    Two heavy jobs on one section rewrite each other's manifest; a manual synth
    next to a queued one must refuse, not wait silently. A job started by the
    queue worker already runs under the worker's lock (LOCK_HELD_ENV=1)."""
    import os
    if os.environ.get(LOCK_HELD_ENV) == "1":
        yield
        return
    path = queue_root() / "heavy.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+", encoding="utf-8")
    try:
        if not _try_lock(fh):
            raise SystemExit(f"{name}: занято — идёт задача очереди или другой тяжёлый "
                             "процесс (heavy.lock). Поставь в очередь: ./run.sh queue add -- …")
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()


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

def pid_alive(pid: int | None) -> bool:
    """Is a process with this pid running? Best effort; a reused pid reads as alive."""
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # exists, owned by someone else
    except OSError:
        return False
    return True


def child_env(job: dict, base: dict | None = None) -> dict:
    """Environment of a job's child: the config fixed at add time, the lock flag."""
    env = dict(os.environ if base is None else base)
    env["PYTHONUTF8"] = "1"
    env[LOCK_HELD_ENV] = "1"  # the worker holds heavy.lock for this child
    cfg = job.get("config")
    if cfg == DEFAULT_CONFIG:
        env.pop(CONFIG_ENV, None)
    elif cfg:
        env[CONFIG_ENV] = str(cfg)
    # no "config" key: a job queued before this field existed keeps the worker's env
    return env


def subprocess_runner(job: dict, log_path: Path,
                      on_start: Callable[[int], None] | None = None) -> int:
    """Run `python -m audiobook <args>` with output appended to the job log."""
    cmd = [sys.executable, "-m", "audiobook", *job["args"]]
    env = child_env(job)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"$ {' '.join(cmd)}\n")
        if job.get("config"):
            log.write(f"# config: {job['config']}\n")
        log.flush()
        proc = subprocess.Popen(cmd, cwd=str(paths.ROOT), stdout=log,
                                stderr=subprocess.STDOUT, env=env)
        if on_start is not None:
            try:
                on_start(proc.pid)
            except Exception:  # noqa: BLE001  (bookkeeping must not orphan the child)
                pass
        return proc.wait()


def _accepts_on_start(runner: Runner) -> bool:
    try:
        return "on_start" in inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False


def _finish(job: dict, pending_path: Path, done: Path) -> None:
    """done/<id>.json first (atomic), then drop pending — a crash in between
    leaves a pending twin that recovery removes."""
    _write_json(done / pending_path.name, job)
    pending_path.unlink(missing_ok=True)


def _notify(notifier: Notifier | None, build: Callable[[], str]) -> None:
    """Build and send a notification; nothing here may stop the queue."""
    if notifier is None:
        return
    try:
        notifier(build())
    except Exception:  # noqa: BLE001
        pass


def _notify_finished(notifier: Notifier | None, job: dict, log_path: Path) -> None:
    if job.get("status") == "failed":
        _notify(notifier, lambda: notify.job_failed(job, notify.log_tail(log_path)))
        return
    section = notify.master_section(job.get("args") or [])
    if section:
        _notify(notifier, lambda: notify.chapter_ready(
            section, notify.chapter_extra(job, notify.log_tail(log_path))))


def _recover(pending: Path, done: Path, say: Callable[[str], None],
             alive: Callable[[int | None], bool],
             requeue: bool = False,
             notifier: Notifier | None = None) -> tuple[int, list[dict]]:
    """Clean up after a dead worker. Returns (interrupted count, jobs whose
    child is still alive — while any exists, nothing new may start).

    A dead "running" job counts one more interrupted attempt (``attempts``).
    With ``requeue`` it goes back to pending (every render step resumes from
    the cache, so a re-run is safe) until MAX_INTERRUPTED attempts; then, and
    always without ``requeue``, it is moved to done as interrupted."""
    interrupted, live = 0, []
    for p in sorted(pending.glob("*.json")):
        if (done / p.name).exists():
            p.unlink(missing_ok=True)  # finished, crash before the pending file went
            say(f"{p.stem}: уже в done — лишний pending удалён")
            continue
        try:
            job = _read_json(p)
        except (OSError, ValueError):
            continue
        if job.get("status") != "running":
            continue
        if alive(job.get("pid")):
            live.append(job)
            continue
        attempts = int(job.get("attempts") or 0) + 1
        if requeue and attempts < MAX_INTERRUPTED:
            job.pop("pid", None)
            job.update(status="pending", attempts=attempts, requeued=_now())
            _write_json(p, job)
            say(f"{job['id']}: прерван (перезагрузка/падение воркера) — снова в очереди, "
                f"прерываний {attempts} из {MAX_INTERRUPTED}")
            continue
        job.update(status="interrupted", exit_code=None, finished=_now(), attempts=attempts)
        _finish(job, p, done)
        interrupted += 1
        tail = f" (прерываний: {attempts})" if requeue else ""
        say(f"{job['id']}: прерван (воркер упал?) — перенесён в done как interrupted{tail}")
        _notify(notifier, lambda job=job, n=attempts: notify.job_interrupted(job, n))
    return interrupted, live


def run_worker(root: Path | None = None, runner: Runner | None = None, poll: float = 0.5,
               say: Callable[[str], None] = print,
               alive: Callable[[int | None], bool] = pid_alive,
               requeue_interrupted: bool = False,
               watch: float | None = None,
               max_cycles: int | None = None,
               stop: Callable[[], bool] | None = None,
               sleep: Callable[[float], None] = time.sleep,
               notifier: Notifier | None = None) -> int:
    """Take pending jobs one by one under the heavy lock until none are left.

    Returns 0 if every job passed, 1 if any failed, was found interrupted, or a
    job of a dead worker is still running (then nothing new is started).

    ``requeue_interrupted``: a job left "running" by a dead worker (reboot) is
    put back to pending instead of done — see _recover.

    ``watch`` (seconds): do not exit when the queue is empty; poll it every
    ``watch`` seconds forever. heavy.lock is taken only while there is work and
    released while idle, so a manual heavy command can run between jobs (it
    refuses, as before, while a job runs). ``max_cycles`` / ``stop`` end the
    loop (tests); the return value is then the last drain's.

    ``notifier`` (text -> anything; default notify.send): see the module doc.
    """
    notifier = notify.send if notifier is None else notifier
    if watch is None:
        res = _drain(root, runner, poll, say, alive, requeue_interrupted, notifier)
        if res.drained and res.ran:
            _notify(notifier, lambda: notify.queue_drained(res.n_done, res.n_failed))
        return res.code
    return _watch_loop(root, runner, poll, say, alive, requeue_interrupted,
                       float(watch), max_cycles, stop, sleep, notifier)


def _scan(root: Path, alive: Callable[[int | None], bool]) -> tuple[bool, list[dict]]:
    """Lock-free look at pending/: (is there anything to take or recover,
    jobs marked running whose pid is alive). A live running job belongs to
    another worker (or a dead worker's surviving child): wait, don't queue up
    on the lock behind it."""
    pending, done, _ = _dirs(root)
    work, live = False, []
    for p in sorted(pending.glob("*.json")):
        if (done / p.name).exists():
            work = True  # crash leftover: recovery drops it
            continue
        try:
            job = _read_json(p)
        except (OSError, ValueError):
            continue
        st = job.get("status")
        if st == "running" and alive(job.get("pid")):
            live.append(job)
        elif st in ("pending", "running"):
            work = True
    return work, live


def _watch_loop(root, runner, poll, say, alive, requeue, watch, max_cycles, stop,
                sleep, notifier: Notifier | None = None) -> int:
    root = root or queue_root()
    code, cycles = 0, 0
    n_done = n_failed = 0   # since the last "queue empty" notification
    state = ""          # what was last announced while idle; avoid journal spam
    while True:
        work, live = _scan(root, alive)
        if live:
            now = "live:" + ",".join(j["id"] for j in live)
            if now != state:
                for job in live:
                    say(f"{job['id']}: выполняется (pid {job.get('pid')}) — жду завершения")
            state = now
        elif work:
            res = _drain(root, runner, poll, say, alive, requeue, notifier)
            code = res.code
            n_done, n_failed = n_done + res.n_done, n_failed + res.n_failed
            if res.drained and n_done + n_failed:
                _notify(notifier, lambda d=n_done, f=n_failed: notify.queue_drained(d, f))
                n_done = n_failed = 0
            state = ""
        elif state != "idle":
            say(f"жду новые задачи (проверка каждые {watch:g} с)")
            state = "idle"
        cycles += 1
        if (max_cycles is not None and cycles >= max_cycles) or (stop is not None and stop()):
            return code
        sleep(watch)


class _DrainResult:
    """Outcome of one _drain pass. ``drained``: the pass ended with no pending
    job left (False when it refused to start because a live job blocks)."""

    __slots__ = ("code", "n_done", "n_failed", "drained")

    def __init__(self, code: int, n_done: int, n_failed: int, drained: bool) -> None:
        self.code, self.n_done, self.n_failed, self.drained = code, n_done, n_failed, drained

    @property
    def ran(self) -> bool:
        return bool(self.n_done or self.n_failed)


def _drain(root: Path | None, runner: Runner | None, poll: float,
           say: Callable[[str], None], alive: Callable[[int | None], bool],
           requeue: bool = False, notifier: Notifier | None = None) -> _DrainResult:
    """One pass of run_worker: hold heavy.lock until no pending job is left.
    ``n_failed`` counts failed jobs and jobs moved to done as interrupted."""
    root = root or queue_root()
    runner = runner or subprocess_runner
    pass_pid = _accepts_on_start(runner)
    pending, done, logs = _dirs(root)
    failed = n_done = 0
    with exclusive_lock(root / "heavy.lock", poll=poll,
                        on_wait=lambda: say("замок heavy.lock занят другим воркером, жду…")):
        # The lock is ours, so a job still marked running belongs to a dead
        # worker — but its child may have outlived it.
        failed, live = _recover(pending, done, say, alive, requeue, notifier)
        if live:
            for job in live:
                say(f"{job['id']}: ещё выполняется (pid {job.get('pid')}, воркер упал, "
                    "процесс жив) — новые задачи не запускаю; queue run после его завершения")
            return _DrainResult(1, 0, failed, drained=False)

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

            def on_start(pid: int, job=job, path=path) -> None:
                job["pid"] = pid
                _write_json(path, job)

            try:
                if pass_pid:
                    code = int(runner(job, log_path, on_start=on_start))
                else:
                    code = int(runner(job, log_path))
            except Exception as e:  # noqa: BLE001
                code = -1
                job["error"] = f"{type(e).__name__}: {e}"
            job.update(exit_code=code, status="done" if code == 0 else "failed", finished=_now())
            _finish(job, path, done)
            if code != 0:
                failed += 1
            else:
                n_done += 1
            say(f"{job['id']}: {job['status']} (код {code})")
            _notify_finished(notifier, job, log_path)
    say("очередь пуста" if not failed else f"очередь пуста, с ошибками: {failed}")
    return _DrainResult(1 if failed else 0, n_done, failed, drained=True)


# ------------------------------------------------------------------------- CLI

# ------------------------------------------------------------------ shortcuts

def section_exists(section: str) -> bool:
    """A section name is "<nn>_<slug>" of some text/blocks/*.blocks.json."""
    for jf in (paths.TEXT / "blocks").glob("*.blocks.json"):
        try:
            d = _read_json(jf)
        except (OSError, ValueError):
            continue
        if f"{d.get('nn')}_{d.get('slug')}" == section:
            return True
    return False


def section_jobs(section: str, workers: int = 2, first: int | None = None) -> list[list[str]]:
    """Whole render of ONE section: chunk → synth → qc → assemble → master → suspects
    → sync (text↔time map) → listen-plan of the chapter, sent to Telegram if set up
    (the last two for a full section only)."""
    f = ["--first", str(first)] if first else []
    sec = ["--section", section]
    return [["chunk", *sec],
            ["synth", *sec, "--workers", str(workers), *f],
            ["qc", *sec],
            ["assemble", *sec, *f],
            ["master", *sec, *f],
            ["suspects", *sec, *f],
            *([] if first else [["sync", *sec],
                                ["listen-plan", *sec, "--tag", section, "--random", "5", "--notify"]])]


def redo_jobs(section: str, chunk_ids: list[str], candidates: int = 3) -> list[list[str]]:
    return [["redo", section, cid, "--candidates", str(candidates)] for cid in chunk_ids]


def add_many(jobs: list[list[str]], root: Path | None = None) -> list[dict]:
    """All or nothing: every job is validated before the first one is queued."""
    config = config_at_add()
    for args in jobs:
        reason = validate_args(args, config)
        if reason:
            raise ValueError(f"{' '.join(args)}: {reason}")
    return [add_job(args, root) for args in jobs]


def _print_added(jobs: list[dict]) -> None:
    for job in jobs:
        cfg = "" if job["config"] == DEFAULT_CONFIG else f"  [{CONFIG_ENV}={job['config']}]"
        print(f"в очереди: {job['id']}  {' '.join(job['args'])}{cfg}")


def cli_shortcut(a) -> int:
    """queue section / queue redo (argparse namespace from __main__)."""
    if not section_exists(a.section):
        print(f"отклонено: нет секции {a.section!r} (см. text/blocks/)", file=sys.stderr)
        return 2
    if a.queue_cmd == "section":
        jobs = section_jobs(a.section, a.workers, a.first)
    else:
        jobs = redo_jobs(a.section, a.chunk_ids, a.candidates)
    try:
        _print_added(add_many(jobs))
    except ValueError as e:
        print(f"отклонено: {e}", file=sys.stderr)
        return 2
    print("дальше: ./run.sh queue run")
    return 0


def cli(sub: str, args: list[str], watch: float | None = None,
        requeue_interrupted: bool = False) -> int:
    if sub == "add":
        try:
            job = add_job(args)
        except ValueError as e:
            print(f"отклонено: {e}", file=sys.stderr)
            return 2
        cfg = "" if job["config"] == DEFAULT_CONFIG else f"  [{CONFIG_ENV}={job['config']}]"
        print(f"в очереди: {job['id']}  {' '.join(job['args'])}{cfg}")
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
        if watch is not None and watch <= 0:
            print("queue run --watch: нужно число секунд > 0", file=sys.stderr)
            return 2
        try:
            return run_worker(requeue_interrupted=requeue_interrupted, watch=watch)
        except KeyboardInterrupt:
            if watch is None:
                raise
            print("воркер остановлен (Ctrl-C)", file=sys.stderr)
            return 130
    print(f"queue {sub}: неизвестная подкоманда", file=sys.stderr)
    return 2
