"""Layer 1: job queue — add/list/validation/order/status and the heavy lock across spawn processes."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from audiobook import jobqueue as jq

ROOT = Path(__file__).resolve().parents[1]


def _ok_runner(job, log_path):
    return 0


# ------------------------------------------------------------------ add / list

def test_add_and_list(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["synth", "--section", "01_vvedenie", "--workers", "4"], q)
    assert j["status"] == "pending" and j["exit_code"] is None and j["created"]
    assert (q / "pending" / f"{j['id']}.json").exists()
    assert (q / "logs").is_dir() and (q / "done").is_dir()
    listed = jq.list_jobs(q)
    assert [x["id"] for x in listed] == [j["id"]]
    assert listed[0]["args"] == ["synth", "--section", "01_vvedenie", "--workers", "4"]
    saved = json.loads((q / "pending" / f"{j['id']}.json").read_text(encoding="utf-8"))
    assert set(saved) >= {"id", "created", "args", "status", "exit_code"}


@pytest.mark.parametrize("args", [
    ["synth"], ["chunk"], ["synth", "--workers", "4"], ["synth", "--section"],
    ["chunk", "--section", "--first"], ["synth", "--section="], [], ["queue", "run"],
])
def test_rejected(tmp_path, args):
    with pytest.raises(ValueError):
        jq.add_job(args, tmp_path / "q")
    assert jq.list_jobs(tmp_path / "q") == []


@pytest.mark.parametrize("args", [
    ["synth", "--section", "01"], ["synth", "--section=01"], ["chunk", "--section", "02"],
    ["qc", "--section", "01"], ["doctor"], ["probe", "--max", "5"],
    ["synth", "--workers", "2", "--section", "01", "--first", "3"],
])
def test_accepted(tmp_path, args):
    assert jq.add_job(args, tmp_path / "q")["args"] == args


def test_leading_double_dash_is_stripped(tmp_path):
    assert jq.add_job(["--", "doctor"], tmp_path / "q")["args"] == ["doctor"]


def test_cli_add_list_via_main(tmp_path, monkeypatch, capsys):
    from audiobook import __main__ as m, paths
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert m.main(["queue", "add", "--", "synth", "--section", "01_x"]) == 0
    assert m.main(["queue", "add", "--", "synth"]) == 2
    assert m.main(["queue", "list"]) == 0
    out = capsys.readouterr()
    assert "synth --section 01_x" in out.out
    assert "отклонено" in out.err
    assert len(list((tmp_path / "out" / "queue" / "pending").glob("*.json"))) == 1


# ---------------------------------------------------------------------- worker

def test_run_order_and_status(tmp_path):
    q = tmp_path / "q"
    ids = [jq.add_job(["probe", "--max", str(i)], q)["id"] for i in range(5)]
    assert ids == sorted(ids)
    seen = []

    def runner(job, log_path):
        seen.append(job["args"][2])
        log_path.write_text("ran\n", encoding="utf-8")
        return 3 if job["args"][2] == "2" else 0

    assert jq.run_worker(q, runner, poll=0.01, say=lambda s: None) == 1   # one job failed
    assert seen == ["0", "1", "2", "3", "4"]                              # failure does not stop the loop
    assert list((q / "pending").glob("*.json")) == []
    done = {j["id"]: j for j in jq.list_jobs(q)}
    assert list(done) == ids
    assert done[ids[2]]["status"] == "failed" and done[ids[2]]["exit_code"] == 3
    assert done[ids[0]]["status"] == "done" and done[ids[0]]["exit_code"] == 0
    assert (q / "logs" / f"{ids[0]}.log").read_text(encoding="utf-8") == "ran\n"


def test_runner_exception_is_failed_job(tmp_path):
    q = tmp_path / "q"
    jq.add_job(["doctor"], q)

    def boom(job, log_path):
        raise RuntimeError("x")

    assert jq.run_worker(q, boom, poll=0.01, say=lambda s: None) == 1
    (job,) = jq.list_jobs(q)
    assert job["status"] == "failed" and "RuntimeError" in job["error"]


def test_jobs_added_during_run_are_picked_up(tmp_path):
    q = tmp_path / "q"
    jq.add_job(["probe", "--max", "1"], q)
    seen = []

    def runner(job, log_path):
        seen.append(job["args"][2])
        if job["args"][2] == "1":
            jq.add_job(["probe", "--max", "2"], q)
        return 0

    assert jq.run_worker(q, runner, poll=0.01, say=lambda s: None) == 0
    assert seen == ["1", "2"]


def test_stale_running_job_is_marked_interrupted(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    p = q / "pending" / f"{j['id']}.json"
    p.write_text(json.dumps({**j, "status": "running"}), encoding="utf-8")
    jq.run_worker(q, _ok_runner, poll=0.01, say=lambda s: None)
    (job,) = jq.list_jobs(q)
    assert job["status"] == "interrupted" and not p.exists()


def test_empty_queue_is_ok(tmp_path):
    assert jq.run_worker(tmp_path / "q", _ok_runner, poll=0.01, say=lambda s: None) == 0


def test_real_subprocess_runner_logs_output(tmp_path, monkeypatch):
    """Runs `python -m audiobook doctor --no-models`-free command: `queue list` is cheap and offline."""
    from audiobook import paths
    monkeypatch.setattr(paths, "ROOT", ROOT)
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    log = tmp_path / "job.log"
    code = jq.subprocess_runner({"args": ["--help"]}, log)
    text = log.read_text(encoding="utf-8")
    assert code == 0 and text.startswith("$ ") and "preflight" in text


# ------------------------------------------- lock: two spawn processes, one queue

def _dummy_runner(events: Path, release: Path | None, pid_tag: str):
    def run(job, log_path):
        with events.open("a", encoding="utf-8") as f:
            f.write(f"start {job['id']} {pid_tag} {time.time():.6f}\n")
        if release is not None and job["args"][-1] == "0":      # first job holds the lock until released
            deadline = time.time() + 30
            while not release.exists() and time.time() < deadline:
                time.sleep(0.02)
        time.sleep(0.05)
        with events.open("a", encoding="utf-8") as f:
            f.write(f"end {job['id']} {pid_tag} {time.time():.6f}\n")
        return 0
    return run


def _worker_proc(q: str, events: str, release: str | None, tag: str, waiting: str):
    root = Path(q)

    def say(msg: str) -> None:
        if "жду" in msg:
            Path(waiting).write_text(tag, encoding="utf-8")

    rel = Path(release) if release else None
    jq.run_worker(root, _dummy_runner(Path(events), rel, tag), poll=0.02, say=say)


def test_two_workers_never_overlap_and_take_each_job_once(tmp_path):
    q = tmp_path / "q"
    events, release = tmp_path / "events.txt", tmp_path / "release"
    waiting = tmp_path / "waiting_B"
    ids = [jq.add_job(["probe", "--max", str(i)], q)["id"] for i in range(4)]

    ctx = mp.get_context("spawn")
    a = ctx.Process(target=_worker_proc, args=(str(q), str(events), str(release), "A", str(tmp_path / "waiting_A")))
    a.start()
    deadline = time.time() + 30
    while not events.exists() and time.time() < deadline:      # A holds the lock inside job 0
        time.sleep(0.02)
    assert events.exists(), "worker A did not start"
    b = ctx.Process(target=_worker_proc, args=(str(q), str(events), None, "B", str(waiting)))
    b.start()
    deadline = time.time() + 30
    while not waiting.exists() and time.time() < deadline:     # B must report waiting for the lock
        time.sleep(0.02)
    assert waiting.exists(), "worker B did not wait on the lock"
    release.write_text("go", encoding="utf-8")
    a.join(60)
    b.join(60)
    assert a.exitcode == 0 and b.exitcode == 0

    rows = [ln.split() for ln in events.read_text(encoding="utf-8").splitlines()]
    starts = [r[1] for r in rows if r[0] == "start"]
    assert starts == ids                                         # each job once, in order
    assert {r[2] for r in rows} == {"A"}                         # B got the lock only after the queue was empty
    open_jobs = 0
    for kind, *_ in sorted(rows, key=lambda r: float(r[3])):
        open_jobs += 1 if kind == "start" else -1
        assert open_jobs in (0, 1), "two jobs ran at the same time"
    assert [j["status"] for j in jq.list_jobs(q)] == ["done"] * 4
    assert list((q / "pending").glob("*.json")) == []


# ------------------------------------------------------------ fetch_results.sh

SCRIPT = ROOT / "scripts" / "mac" / "fetch_results.sh"


def test_fetch_script_is_read_only_and_filters_extensions():
    text = SCRIPT.read_text(encoding="utf-8")
    for bad in ("--delete", "--remove-source-files", "--move", "rm ", "--include='*.wav'"):
        assert bad not in text
    for ext in ("mp3", "tsv", "txt", "md", "html", "json", "log"):
        assert f"--include='*.{ext}'" in text
    assert "--exclude='*'" in text
    assert text.startswith("#!/usr/bin/env bash")


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="needs bash")
def test_fetch_script_runs_rsync_with_expected_args(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "rsync"
    fake.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$RSYNC_ARGS"\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    args_file, dest = tmp_path / "args.txt", tmp_path / "dl"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "RSYNC_ARGS": str(args_file), "AUDIOBOOK_FETCH_DEST": str(dest)}
    subprocess.run(["bash", str(SCRIPT), "myhost", "--dry-run"], env=env, check=True,
                   capture_output=True, text=True, encoding="utf-8")
    args = args_file.read_text(encoding="utf-8").splitlines()
    assert args[-2] == "myhost:audiobook/out/" and "--dry-run" in args
    assert args[-1].startswith(str(dest)) and args[-1].endswith("/")
    assert not any(a.startswith("--delete") for a in args)
    day = args[-1].rstrip("/").rsplit("/", 1)[-1]
    assert len(day) == 10 and day[4] == "-" and (dest / day).is_dir()
    assert os.access(SCRIPT, os.X_OK)


def _run_fetch(tmp_path, *args, check=True):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "rsync"
    fake.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$RSYNC_ARGS"\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    args_file, dest = tmp_path / "args.txt", tmp_path / "dl"
    args_file.unlink(missing_ok=True)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "RSYNC_ARGS": str(args_file), "AUDIOBOOK_FETCH_DEST": str(dest)}
    res = subprocess.run(["bash", str(SCRIPT), *args], env=env, check=check,
                         capture_output=True, text=True, encoding="utf-8")
    got = args_file.read_text(encoding="utf-8").splitlines() if args_file.exists() else None
    return res, got


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="needs bash")
def test_fetch_script_md_and_with_wav(tmp_path):
    _res, args = _run_fetch(tmp_path, "myhost")
    assert "--include=*.md" in args and not any(".wav" in a for a in args)   # no wav by default
    for form in (["--with-wav", "golden/compare_a_b/"], ["--with-wav=out/golden/compare_a_b"]):
        _res, args = _run_fetch(tmp_path, "myhost", *form)
        assert "--include=/golden/compare_a_b/**.wav" in args
        assert args.index("--include=/golden/compare_a_b/**.wav") < args.index("--exclude=*")
        assert args[-2] == "myhost:audiobook/out/"
        assert not any(a.startswith("--delete") or a.startswith("--remove") for a in args)
    _res, args = _run_fetch(tmp_path, "--with-wav", "probe", "otherhost", "-n")
    assert args[-2] == "otherhost:audiobook/out/" and "--dry-run" in args
    for bad in (["--with-wav"], ["--with-wav", "../x"], ["--with-wav", "/abs"],
                ["--with-wav", "a/*"], ["--with-wav", "out/"], ["--bogus"]):
        res, args = _run_fetch(tmp_path, *bad, check=False)
        assert res.returncode == 2 and args is None, bad


# ------------------------------------------- validation with argparse semantics

@pytest.mark.parametrize("args", [
    ["synth", "--section", "01", "--section", ""],     # last occurrence wins → empty
    ["synth", "--section", "  "],
    ["chunk", "--section=01", "--section="],
    ["synth", "--sec="],                               # abbreviation, empty
])
def test_rejected_argparse_semantics(tmp_path, args):
    with pytest.raises(ValueError, match="section|--section"):
        jq.add_job(args, tmp_path / "q")


@pytest.mark.parametrize("args", [
    ["synth", "--section", "", "--section", "01"],     # last occurrence wins → 01
    ["synth", "--sec", "01"],                          # argparse abbreviation
])
def test_accepted_argparse_semantics(tmp_path, args):
    assert jq.add_job(args, tmp_path / "q")["args"] == args


def test_validation_uses_real_parser_when_main_exposes_one(tmp_path, monkeypatch):
    import argparse
    from audiobook import __main__ as m

    def build_parser():
        p = argparse.ArgumentParser(prog="audiobook")
        sub = p.add_subparsers(dest="cmd", required=True)
        s = sub.add_parser("synth")
        s.add_argument("--section", default=None)
        sub.add_parser("doctor")
        return p

    monkeypatch.setattr(m, "build_parser", build_parser, raising=False)
    assert jq.validate_args(["synth", "--section", "01"]) is None
    assert "парсером" in jq.validate_args(["doctor", "--nope"])          # unknown option
    assert "парсером" in jq.validate_args(["nosuchcmd"])
    assert "без --section" in jq.validate_args(["synth", "--section", "01", "--section", ""])


def test_config_is_fixed_at_add_and_passed_to_child(tmp_path, monkeypatch):
    q = tmp_path / "q"
    monkeypatch.delenv("AUDIOBOOK_CONFIG", raising=False)
    j1 = jq.add_job(["probe", "--max", "1"], q)
    monkeypatch.setenv("AUDIOBOOK_CONFIG", "trial/config_b.yaml")
    j2 = jq.add_job(["probe", "--max", "2"], q)
    assert (j1["config"], j2["config"]) == ("config.yaml", "trial/config_b.yaml")
    saved = json.loads((q / "pending" / f"{j2['id']}.json").read_text(encoding="utf-8"))
    assert saved["config"] == "trial/config_b.yaml"
    # the worker's own env does not leak into a job added with config.yaml…
    env1 = jq.child_env(j1, {"AUDIOBOOK_CONFIG": "worker_has_this.yaml"})
    assert "AUDIOBOOK_CONFIG" not in env1 and env1[jq.LOCK_HELD_ENV] == "1"
    # …and a trial job gets its own config even if the worker has none
    assert jq.child_env(j2, {})["AUDIOBOOK_CONFIG"] == "trial/config_b.yaml"
    # jobs queued before the field existed keep the worker's env
    assert jq.child_env({"args": []}, {"AUDIOBOOK_CONFIG": "w.yaml"})["AUDIOBOOK_CONFIG"] == "w.yaml"


def test_trial_config_rejected_for_book_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOBOOK_CONFIG", "trial.yaml")
    with pytest.raises(ValueError, match="config.yaml"):
        jq.add_job(["synth", "--section", "01"], tmp_path / "q")
    assert jq.add_job(["probe", "--max", "3"], tmp_path / "q")["config"] == "trial.yaml"


def test_real_runner_passes_config_and_records_pid(tmp_path, monkeypatch):
    from audiobook import paths
    monkeypatch.setattr(paths, "ROOT", ROOT)
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.setenv("AUDIOBOOK_CONFIG", "from_worker.yaml")
    pids = []
    job = {"args": ["--help"], "config": "config.yaml"}
    code = jq.subprocess_runner(job, tmp_path / "a.log", on_start=pids.append)   # real child
    assert code == 0 and len(pids) == 1 and pids[0] > 0
    assert "# config: config.yaml" in (tmp_path / "a.log").read_text(encoding="utf-8")

    seen = {}
    real_popen = jq.subprocess.Popen

    def spy_popen(cmd, **kw):
        seen["env"] = kw["env"]
        return real_popen(cmd, **kw)

    monkeypatch.setattr(jq.subprocess, "Popen", spy_popen)
    jq.subprocess_runner(job, tmp_path / "b.log")
    assert "AUDIOBOOK_CONFIG" not in seen["env"] and seen["env"][jq.LOCK_HELD_ENV] == "1"
    jq.subprocess_runner({**job, "config": "trial.yaml"}, tmp_path / "c.log")
    assert seen["env"]["AUDIOBOOK_CONFIG"] == "trial.yaml"


def test_worker_stores_child_pid_while_running(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["probe", "--max", "1"], q)
    seen = {}

    def runner(job, log_path, on_start=None):
        on_start(4242)
        seen.update(jq._read_json(q / "pending" / f"{job['id']}.json"))
        return 0

    assert jq.run_worker(q, runner, poll=0.01, say=lambda s: None) == 0
    assert seen["status"] == "running" and seen["pid"] == 4242
    (done,) = jq.list_jobs(q)
    assert done["id"] == j["id"] and done["pid"] == 4242 and done["status"] == "done"


def test_running_job_with_live_pid_blocks_worker(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["probe", "--max", "1"], q)
    jq.add_job(["probe", "--max", "2"], q)
    p = q / "pending" / f"{j['id']}.json"
    p.write_text(json.dumps({**j, "status": "running", "pid": 777}), encoding="utf-8")
    ran, said = [], []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0, poll=0.01, say=said.append,
                         alive=lambda pid: pid == 777)
    assert code == 1 and ran == [] and p.exists()               # nothing new started, job kept
    assert any("ещё выполняется" in s and "777" in s for s in said)
    # once the orphan is gone: interrupted, then the rest runs
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0, poll=0.01,
                         say=lambda s: None, alive=lambda pid: False)
    assert code == 1 and len(ran) == 1
    statuses = {x["id"]: x["status"] for x in jq.list_jobs(q)}
    assert statuses[j["id"]] == "interrupted"


def test_pid_alive_posix():
    if sys.platform == "win32":
        assert jq.pid_alive(os.getpid())
        return
    assert jq.pid_alive(os.getpid())
    assert not jq.pid_alive(None) and not jq.pid_alive(0)
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert not jq.pid_alive(proc.pid)


def test_crash_between_done_and_unlink_is_recovered(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["probe", "--max", "1"], q)
    pend = q / "pending" / f"{j['id']}.json"
    finished = {**j, "status": "done", "exit_code": 0}
    (q / "done" / pend.name).write_text(json.dumps(finished), encoding="utf-8")
    pend.write_text(json.dumps({**j, "status": "running", "pid": 1}), encoding="utf-8")
    assert [x["status"] for x in jq.list_jobs(q)] == ["done"]       # no duplicate in the list
    ran = []
    assert jq.run_worker(q, lambda job, lp: ran.append(job) or 0, poll=0.01,
                         say=lambda s: None, alive=lambda pid: True) == 0
    assert ran == [] and not pend.exists()                          # not re-run, not "interrupted"
    (job,) = jq.list_jobs(q)
    assert job["status"] == "done" and job["exit_code"] == 0


def test_finish_writes_done_before_removing_pending(tmp_path, monkeypatch):
    q = tmp_path / "q"
    jq.add_job(["probe", "--max", "1"], q)
    order = []
    real_write, real_unlink = jq._write_json, Path.unlink

    def spy_write(path, data):
        order.append(("write", path.parent.name, data.get("status")))
        real_write(path, data)

    def spy_unlink(self, missing_ok=False):
        order.append(("unlink", self.parent.name, None))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(jq, "_write_json", spy_write)
    monkeypatch.setattr(Path, "unlink", spy_unlink)
    jq.run_worker(q, _ok_runner, poll=0.01, say=lambda s: None)
    i_done = order.index(("write", "done", "done"))
    i_unlink = next(i for i, o in enumerate(order) if o[:2] == ("unlink", "pending"))
    assert i_done < i_unlink
    assert not list((q / "done").glob("*.tmp"))                     # temp + rename, no leftovers
