"""Layer 1: queue survives a reboot — requeue of interrupted jobs with an
attempt cap, the --watch loop, lock released while idle, the systemd unit."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiobook import jobqueue as jq, paths

ROOT = Path(__file__).resolve().parents[1]


class _WorkerDied(BaseException):
    """Not an Exception: escapes run_worker like a kill/reboot would, leaving
    the job marked running with the child's pid."""


def _dying_runner(job, log_path, on_start=None):
    on_start(4242)
    raise _WorkerDied


def _mark_running(q: Path, job_id: str, pid: int = 999) -> Path:
    p = q / "pending" / f"{job_id}.json"
    job = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps({**job, "status": "running", "pid": pid}), encoding="utf-8")
    return p


def test_default_still_moves_interrupted_to_done(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    _mark_running(q, j["id"])
    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0, poll=0.01,
                         say=lambda s: None, alive=lambda pid: False)
    assert code == 1 and ran == []
    (job,) = jq.list_jobs(q)
    assert job["status"] == "interrupted" and job["attempts"] == 1


def test_requeue_runs_interrupted_job_again(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    j2 = jq.add_job(["probe", "--max", "1"], q)
    _mark_running(q, j["id"])
    ran, said = [], []
    code = jq.run_worker(q, lambda job, lp: ran.append(job["id"]) or 0, poll=0.01,
                         say=said.append, alive=lambda pid: False, requeue_interrupted=True)
    assert code == 0
    assert ran == [j["id"], j2["id"]]                     # the interrupted job keeps its place
    done = {x["id"]: x for x in jq.list_jobs(q)}
    assert done[j["id"]]["status"] == "done" and done[j["id"]]["attempts"] == 1
    assert "attempts" not in done[j2["id"]]
    assert any("снова в очереди" in s and "1 из 3" in s for s in said)


def test_requeue_gives_up_after_three_interruptions(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    p = q / "pending" / f"{j['id']}.json"
    kw = dict(poll=0.01, say=lambda s: None, alive=lambda pid: False, requeue_interrupted=True)
    with pytest.raises(_WorkerDied):                      # run 1: dies
        jq.run_worker(q, _dying_runner, **kw)
    for n in (1, 2):                                      # runs 2, 3: requeued, die again
        assert jq._read_json(p)["status"] == "running"
        with pytest.raises(_WorkerDied):
            jq.run_worker(q, _dying_runner, **kw)
        assert jq._read_json(p)["attempts"] == n
    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0, **kw)
    assert code == 1 and ran == [] and not p.exists()
    (job,) = jq.list_jobs(q)
    assert job["status"] == "interrupted" and job["attempts"] == 3


def test_requeue_leaves_live_child_alone(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    p = _mark_running(q, j["id"], pid=777)
    code = jq.run_worker(q, _dying_runner, poll=0.01, say=lambda s: None,
                         alive=lambda pid: pid == 777, requeue_interrupted=True)
    assert code == 1 and jq._read_json(p)["status"] == "running"


# ----------------------------------------------------------------------- watch

def test_watch_picks_up_jobs_added_while_idle_and_stops(tmp_path, monkeypatch):
    q = tmp_path / "out" / "queue"
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    monkeypatch.delenv(jq.LOCK_HELD_ENV, raising=False)
    ran, said, sleeps = [], [], []

    def sleep(s):
        sleeps.append(s)
        # Idle: heavy.lock must be free for a manual heavy command.
        with jq.heavy_command_lock("synth"):
            pass
        if len(sleeps) == 1:
            jq.add_job(["probe", "--max", "1"], q)

    code = jq.run_worker(q, lambda job, lp: ran.append(job["args"]) or 0, poll=0.01,
                         say=said.append, watch=7, max_cycles=4, sleep=sleep)
    assert code == 0
    assert ran == [["probe", "--max", "1"]]
    assert sleeps == [7, 7, 7]                            # no sleep after the last cycle
    assert sum("жду новые задачи" in s for s in said) == 2  # once per idle stretch, not per poll


def test_watch_holds_lock_while_a_job_runs(tmp_path, monkeypatch):
    q = tmp_path / "out" / "queue"
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    monkeypatch.delenv(jq.LOCK_HELD_ENV, raising=False)
    jq.add_job(["probe", "--max", "1"], q)
    refused = []

    def runner(job, lp):
        try:
            with jq.heavy_command_lock("synth"):
                pass
        except SystemExit as e:
            refused.append(str(e))
        return 0

    jq.run_worker(q, runner, poll=0.01, say=lambda s: None, watch=1, max_cycles=1,
                  sleep=lambda s: None)
    assert refused and "занято" in refused[0]


def test_watch_stop_callback(tmp_path):
    q = tmp_path / "q"
    calls = []
    code = jq.run_worker(q, _dying_runner, poll=0.01, say=lambda s: None, watch=5,
                         stop=lambda: calls.append(1) or len(calls) >= 2,
                         sleep=lambda s: None)
    assert code == 0 and len(calls) == 2


def test_watch_waits_for_live_job_of_another_worker_quietly(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    _mark_running(q, j["id"], pid=555)
    said = []
    code = jq.run_worker(q, _dying_runner, poll=0.01, say=said.append,
                         alive=lambda pid: pid == 555, watch=1, max_cycles=5,
                         sleep=lambda s: None)
    assert code == 0
    assert sum("выполняется (pid 555)" in s for s in said) == 1


def test_watch_recovers_and_requeues_after_reboot(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    _mark_running(q, j["id"])
    ran = []
    jq.run_worker(q, lambda job, lp: ran.append(job["id"]) or 0, poll=0.01,
                  say=lambda s: None, alive=lambda pid: False, requeue_interrupted=True,
                  watch=60, max_cycles=2, sleep=lambda s: None)
    assert ran == [j["id"]]
    (job,) = jq.list_jobs(q)
    assert job["status"] == "done" and job["attempts"] == 1


def test_cli_rejects_nonpositive_watch(capsys):
    assert jq.cli("run", [], watch=0) == 2
    assert "--watch" in capsys.readouterr().err


# --------------------------------------------------------------------- systemd

def test_systemd_unit_template():
    unit = (ROOT / "scripts" / "gamebox" / "audiobook-queue.service").read_text(encoding="utf-8")
    assert "queue run --watch 60 --requeue-interrupted" in unit
    assert "%h/audiobook" in unit and "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit
    assert "/home/" not in unit and "User=" not in unit      # no user names, --user unit
    readme = (ROOT / "scripts" / "gamebox" / "README.md").read_text(encoding="utf-8")
    for s in ("systemctl --user", "loginctl enable-linger", "journalctl --user -u audiobook-queue",
              "queue add"):
        assert s in readme
