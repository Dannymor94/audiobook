"""Preflight for the render box: resources, foreign heavy processes, git state, doctor.

The decision logic (`evaluate`) is a pure function over measured values so it is
testable without touching the machine. The `read_*` helpers are the thin I/O layer;
each returns None when a value cannot be measured (non-Linux, no `ps`, no git) and
the check then degrades to WARN instead of failing.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from . import paths

DEFAULT_MAX_LOAD = 4.0
DEFAULT_MIN_FREE_GB = 16.0

# Commands of `python -m audiobook` that load models or burn CPU for minutes
# (a superset of __main__._HEAVY, checked by a test). Entries are regex parts:
# `golden render` synthesises, `golden init|compare` do not.
HEAVY_SUBCOMMANDS = (
    "synth", "qc", "chunk", "accept", "probe", "bench", "calibrate", "pick-ref", "credits", "passage",
    "ref-compare", "ref-scout", "pron-test", "redo", "headings", "phoneme-check",
    r"golden\s+render",
)
HEAVY_RE = re.compile(
    r"whisper|transcri|llama-server|"
    r"-m\s+audiobook\s+(?:" + "|".join(HEAVY_SUBCOMMANDS) + r")(?:\s|$)",
    re.IGNORECASE,
)


class Check(NamedTuple):
    name: str
    ok: bool | None      # True = GREEN, False = RED, None = WARN (could not measure)
    hint: str = ""


@dataclass(frozen=True)
class GitFacts:
    branch: str                       # "HEAD" when detached
    head: str                         # short sha
    dirty: tuple[str, ...]            # tracked, uncommitted changes (porcelain lines)
    fetched: bool                     # git fetch succeeded (network is there)
    remote_head: str | None           # short sha of origin/<branch> after fetch
    ahead: int | None = None
    behind: int | None = None


# ---------------------------------------------------------------- pure logic

def foreign_heavy(procs: list[tuple[int, str]], own_pids: set[int] | frozenset[int]
                  ) -> list[tuple[int, str]]:
    """Heavy processes other than ourselves (own pid and its parent are excluded)."""
    return [(pid, args) for pid, args in procs
            if pid not in own_pids and HEAVY_RE.search(args)]


def parse_ps(text: str) -> list[tuple[int, str]]:
    """Parse `ps -eo pid,args` output into (pid, args)."""
    out: list[tuple[int, str]] = []
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            out.append((int(parts[0]), parts[1]))
    return out


def evaluate(*, load1: float | None, available_gb: float | None,
             procs: list[tuple[int, str]] | None, git: GitFacts | None,
             max_load: float = DEFAULT_MAX_LOAD, min_free_gb: float = DEFAULT_MIN_FREE_GB,
             own_pids: set[int] | frozenset[int] = frozenset()) -> list[Check]:
    """Turn measured values into check rows. None input means 'not measurable' -> WARN."""
    rows: list[Check] = []

    if load1 is None:
        rows.append(Check("load(1м): не измерить", None, "нет /proc/loadavg и os.getloadavg"))
    else:
        rows.append(Check(f"load(1м) {load1:.2f} < {max_load:g}", load1 < max_load,
                          "машина занята — дождаться или посмотреть top"))

    if available_gb is None:
        rows.append(Check("RAM available: не измерить", None, "нет /proc/meminfo (не Linux)"))
    else:
        rows.append(Check(f"RAM available {available_gb:.1f} ГБ >= {min_free_gb:g}",
                          available_gb >= min_free_gb, "освободить память или поднять --min-free-gb"))

    if procs is None:
        rows.append(Check("чужие тяжёлые процессы: не проверить", None, "нет ps"))
    else:
        foreign = foreign_heavy(procs, own_pids)
        if foreign:
            shown = "; ".join(f"{pid} {args[:60]}" for pid, args in foreign[:3])
            rows.append(Check(f"чужие тяжёлые процессы: {len(foreign)}", False,
                              f"{shown} — не накладывать задачи, см. queue"))
        else:
            rows.append(Check("чужих тяжёлых процессов нет", True))

    if git is None:
        rows.append(Check("git: недоступен", None, "нет git или это не репозиторий"))
        return rows

    detached = git.branch == "HEAD"
    rows.append(Check(f"git ветка {git.branch}", not detached, "detached HEAD — перейти на ветку"))
    rows.append(Check(f"git HEAD {git.head}", True))
    if git.dirty:
        rows.append(Check(f"git: незакоммиченные изменения ({len(git.dirty)})", False,
                          f"{git.dirty[0].strip()} … — закоммитить или stash"))
    else:
        rows.append(Check("git: отслеживаемые файлы чистые", True))

    target = f"origin/{git.branch}"
    if not git.fetched:
        rows.append(Check(f"git HEAD == {target}: не проверить", None, "fetch не удался (нет сети?)"))
    elif git.remote_head is None:
        rows.append(Check(f"git HEAD == {target}", False, f"ветки нет на origin — git push origin {git.branch}"))
    elif git.remote_head == git.head:
        rows.append(Check(f"git HEAD == {target}", True))
    else:
        detail = ""
        if git.behind:
            detail += f" позади на {git.behind}"
        if git.ahead:
            detail += f" впереди на {git.ahead}"
        hint = "git pull" if git.behind and not git.ahead else "синхронизировать с origin"
        rows.append(Check(f"git HEAD != {target}{detail}", False, hint))
    return rows


def is_green(rows: list[Check]) -> bool:
    return all(r.ok is not False for r in rows)


def format_rows(rows: list[Check]) -> list[str]:
    label = {True: "GREEN", False: "RED  ", None: "WARN "}
    out = []
    for r in rows:
        line = f"{label[r.ok]}  {r.name}"
        if r.ok is not True and r.hint:
            line += f"  -> {r.hint}"
        out.append(line)
    return out


# ------------------------------------------------------------------- I/O layer

def read_load() -> float | None:
    try:
        return float((Path("/proc") / "loadavg").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return None


def parse_meminfo(text: str) -> float | None:
    """MemAvailable in GB from /proc/meminfo text."""
    m = re.search(r"^MemAvailable:\s+(\d+)\s*kB", text, re.MULTILINE)
    return int(m.group(1)) / (1024 * 1024) if m else None


def read_available_gb() -> float | None:
    try:
        return parse_meminfo((Path("/proc") / "meminfo").read_text(encoding="utf-8"))
    except OSError:
        return None


def read_procs() -> list[tuple[int, str]] | None:
    try:
        res = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_ps(res.stdout) if res.returncode == 0 else None


def _git(root: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"      # never hang on a credential prompt
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)


def read_git(root: Path | None = None, fetch: bool = True) -> GitFacts | None:
    root = root or paths.ROOT
    try:
        br = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if br.returncode != 0:
            return None
        branch = br.stdout.strip()
        head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
        st = _git(root, "status", "--porcelain", "--untracked-files=no")
        dirty = tuple(ln for ln in st.stdout.splitlines() if ln.strip())
        fetched = False
        if fetch:
            try:
                fetched = _git(root, "fetch", "--quiet", "origin", timeout=30).returncode == 0
            except subprocess.TimeoutExpired:
                fetched = False
        rh = _git(root, "rev-parse", "--short", f"origin/{branch}")
        remote_head = rh.stdout.strip() if rh.returncode == 0 else None
        ahead = behind = None
        if remote_head:
            lr = _git(root, "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}")
            if lr.returncode == 0:
                a, b = lr.stdout.split()
                ahead, behind = int(a), int(b)
        return GitFacts(branch, head, dirty, fetched, remote_head, ahead, behind)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def own_pids() -> set[int]:
    return {os.getpid(), os.getppid()}


def run(config: dict | None, max_load: float = DEFAULT_MAX_LOAD,
        min_free_gb: float = DEFAULT_MIN_FREE_GB, no_models: bool = False) -> bool:
    rows = evaluate(load1=read_load(), available_gb=read_available_gb(),
                    procs=read_procs(), git=read_git(), max_load=max_load,
                    min_free_gb=min_free_gb, own_pids=own_pids())

    # doctor is called as a function, not a subprocess; its own report is captured.
    buf = io.StringIO()
    try:
        from .doctor import run as doctor
        with contextlib.redirect_stdout(buf):
            doctor_ok = bool(doctor(no_models, config))
        doctor_hint = "см. вывод ниже"
    except Exception as e:  # noqa: BLE001
        doctor_ok, doctor_hint = False, f"doctor упал: {e}"
    rows.append(Check("doctor", doctor_ok, doctor_hint))

    print("\n".join(format_rows(rows)))
    if not doctor_ok and buf.getvalue():
        print("\n--- doctor ---")
        print(buf.getvalue().rstrip())
    green = is_green(rows)
    print("\nPREFLIGHT:", "GREEN" if green else "RED")
    return green
