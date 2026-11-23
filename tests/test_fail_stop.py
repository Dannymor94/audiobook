"""Layer 1: fail-closed pipeline stop for chained section jobs.

Fake runners only — no TTS, no audio, no real subprocess.

Fail-closed contract: a dependent job may start ONLY if its predecessor is
in done/ with status=done and exit_code=0.  Any other state (missing,
corrupt, wrong status, non-zero exit_code) causes immediate cancellation.
"""
from __future__ import annotations

import json
from pathlib import Path

from audiobook import jobqueue as jq


def _ok(job, lp):
    return 0


def _fail(job, lp):
    return 1


# -------------------------------------------------------------- add_many chain

def test_chain_wires_depends_on(tmp_path):
    q = tmp_path / "q"
    added = jq.add_many([
        ["chunk", "--section", "01_x"],
        ["synth", "--section", "01_x", "--workers", "2"],
        ["qc", "--section", "01_x"],
    ], q, chain=True)
    assert "depends_on" not in added[0]
    assert added[1]["depends_on"] == added[0]["id"]
    assert added[2]["depends_on"] == added[1]["id"]
    for job in added:
        saved = json.loads((q / "pending" / f"{job['id']}.json").read_text(encoding="utf-8"))
        assert saved.get("depends_on") == job.get("depends_on")


def test_no_chain_adds_no_depends_on(tmp_path):
    q = tmp_path / "q"
    added = jq.add_many([["doctor"], ["probe", "--max", "1"]], q, chain=False)
    assert all("depends_on" not in j for j in added)


# ------------------------------------------------- fail-closed: success path

def test_success_pipeline_runs_all_stages(tmp_path):
    q = tmp_path / "q"
    jobs = jq.add_many([
        ["chunk", "--section", "01_x"],
        ["synth", "--section", "01_x", "--workers", "2"],
        ["qc", "--section", "01_x"],
    ], q, chain=True)
    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job["args"][0]) or 0,
                         poll=0.01, say=lambda s: None)
    assert code == 0
    assert ran == ["chunk", "synth", "qc"]
    assert all(j["status"] == "done" for j in jq.list_jobs(q))


# ------------------------------------------------- fail-closed: failure paths

def test_failed_stage_cancels_pipeline(tmp_path):
    q = tmp_path / "q"
    jobs = jq.add_many([
        ["chunk", "--section", "01_x"],
        ["synth", "--section", "01_x", "--workers", "2"],
        ["qc", "--section", "01_x"],
        ["assemble", "--section", "01_x"],
    ], q, chain=True)
    ids = [j["id"] for j in jobs]
    ran = []

    def runner(job, lp):
        ran.append(job["args"][0])
        return 1 if job["args"][0] == "chunk" else 0

    code = jq.run_worker(q, runner, poll=0.01, say=lambda s: None)
    assert code == 1
    assert ran == ["chunk"]
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[ids[0]] == "failed"
    assert statuses[ids[1]] == "cancelled"
    assert statuses[ids[2]] == "cancelled"
    assert statuses[ids[3]] == "cancelled"


def test_middle_failure_cancels_tail_but_not_head(tmp_path):
    q = tmp_path / "q"
    jobs = jq.add_many([
        ["chunk", "--section", "01_x"],
        ["synth", "--section", "01_x", "--workers", "2"],
        ["qc", "--section", "01_x"],
    ], q, chain=True)
    ids = [j["id"] for j in jobs]
    ran = []

    def runner(job, lp):
        ran.append(job["args"][0])
        return 1 if job["args"][0] == "synth" else 0

    jq.run_worker(q, runner, poll=0.01, say=lambda s: None)
    assert ran == ["chunk", "synth"]
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[ids[0]] == "done"
    assert statuses[ids[1]] == "failed"
    assert statuses[ids[2]] == "cancelled"


def test_non_zero_exit_code_on_done_record_cancels_dependent(tmp_path):
    """Defensive: status=done but exit_code != 0 must still cancel."""
    q = tmp_path / "q"
    chunk = jq.add_job(["chunk", "--section", "01_x"], q)
    synth = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                       depends_on=chunk["id"])
    # plant a corrupt-ish done record: status=done but exit_code=1
    chunk.update(status="done", exit_code=1, finished=jq._now())
    jq._finish(chunk, q / "pending" / f"{chunk['id']}.json", q / "done")

    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                         poll=0.01, say=lambda s: None)
    assert code == 1 and ran == []
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[synth["id"]] == "cancelled"


def test_missing_predecessor_record_cancels_dependent(tmp_path):
    """Dep record never reached done/ — job must be cancelled, not started."""
    q = tmp_path / "q"
    # wire a depends_on pointing at a job id that was never added
    ghost_id = "00000000000000000000-dead"
    synth = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                       depends_on=ghost_id)
    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                         poll=0.01, say=lambda s: None)
    assert code == 1 and ran == []
    (done_job,) = jq.list_jobs(q)
    assert done_job["id"] == synth["id"] and done_job["status"] == "cancelled"
    assert "no durable record" in done_job.get("reason", "")


def test_corrupt_predecessor_record_cancels_dependent(tmp_path):
    """Corrupt JSON in done/<dep>.json must cancel, not crash the worker."""
    q = tmp_path / "q"
    chunk = jq.add_job(["chunk", "--section", "01_x"], q)
    synth = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                       depends_on=chunk["id"])
    # move chunk to done/ but with invalid JSON
    pend_path = q / "pending" / f"{chunk['id']}.json"
    pend_path.unlink()
    done_dir = q / "done"
    done_dir.mkdir(parents=True, exist_ok=True)
    (done_dir / f"{chunk['id']}.json").write_text("{not valid json", encoding="utf-8")

    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                         poll=0.01, say=lambda s: None)
    assert code == 1 and ran == []
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[synth["id"]] == "cancelled"
    assert "corrupt" in statuses.get(synth["id"], "") or True  # reason in job record
    done_synth = next(j for j in jq.list_jobs(q) if j["id"] == synth["id"])
    assert "corrupt" in done_synth.get("reason", "")


def test_predecessor_interrupted_cancels_dependent(tmp_path):
    q = tmp_path / "q"
    chunk = jq.add_job(["chunk", "--section", "01_x"], q)
    synth = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                       depends_on=chunk["id"])
    chunk.update(status="interrupted", exit_code=None, finished=jq._now())
    jq._finish(chunk, q / "pending" / f"{chunk['id']}.json", q / "done")

    ran = []
    jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                  poll=0.01, say=lambda s: None)
    assert ran == []
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[synth["id"]] == "cancelled"


def test_predecessor_cancelled_cancels_dependent(tmp_path):
    q = tmp_path / "q"
    chunk = jq.add_job(["chunk", "--section", "01_x"], q)
    synth = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                       depends_on=chunk["id"])
    chunk.update(status="cancelled", exit_code=None, finished=jq._now(),
                 reason="test")
    jq._finish(chunk, q / "pending" / f"{chunk['id']}.json", q / "done")

    ran = []
    jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                  poll=0.01, say=lambda s: None)
    assert ran == []
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[synth["id"]] == "cancelled"


# ---------------------------------------- watcher restart does not bypass

def test_restart_cancels_interrupted_job_with_failed_dep(tmp_path):
    """Worker crashed while synth was running; chunk had already failed.
    On restart with --requeue-interrupted, synth is requeued but then cancelled
    because its predecessor is in done/ as failed (not status=done exit_code=0)."""
    q = tmp_path / "q"
    chunk = jq.add_job(["chunk", "--section", "01_x"], q)
    chunk.update(status="failed", exit_code=1, finished=jq._now())
    jq._finish(chunk, q / "pending" / f"{chunk['id']}.json", q / "done")

    synth = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                       depends_on=chunk["id"])
    synth_path = q / "pending" / f"{synth['id']}.json"
    synth.update(status="running", pid=99999)
    jq._write_json(synth_path, synth)

    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                         poll=0.01, say=lambda s: None,
                         alive=lambda pid: False,
                         requeue_interrupted=True)
    assert code == 1 and ran == []
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[chunk["id"]] == "failed"
    assert statuses[synth["id"]] == "cancelled"


def test_non_chained_jobs_keep_running_after_failure(tmp_path):
    """Existing behaviour: unrelated jobs without depends_on run independently."""
    q = tmp_path / "q"
    jq.add_job(["chunk", "--section", "01_x"], q)
    jq.add_job(["doctor"], q)
    ran = []

    def runner(job, lp):
        ran.append(job["args"][0])
        return 1 if job["args"][0] == "chunk" else 0

    code = jq.run_worker(q, runner, poll=0.01, say=lambda s: None)
    assert code == 1
    assert ran == ["chunk", "doctor"]   # doctor still ran


def test_watch_mode_fail_stop(tmp_path, monkeypatch):
    """In --watch mode, fail-stop works within a single _drain cycle."""
    from audiobook import paths
    q = tmp_path / "out" / "queue"
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    monkeypatch.delenv(jq.LOCK_HELD_ENV, raising=False)

    jobs = jq.add_many([
        ["chunk", "--section", "01_x"],
        ["synth", "--section", "01_x", "--workers", "2"],
    ], q, chain=True)
    ran = []

    def runner(job, lp):
        ran.append(job["args"][0])
        return 1 if job["args"][0] == "chunk" else 0

    jq.run_worker(q, runner, poll=0.01, say=lambda s: None,
                  watch=1, max_cycles=2, sleep=lambda s: None)
    assert ran == ["chunk"]
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[jobs[0]["id"]] == "failed"
    assert statuses[jobs[1]["id"]] == "cancelled"
