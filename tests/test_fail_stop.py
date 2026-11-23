"""Layer 1: fail-stop for chained section pipelines.

Fake runners only — no TTS, no audio, no real subprocess.
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


# ------------------------------------------------- fail-stop during drain

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
    assert ran == ["chunk"]   # synth/qc/assemble never ran
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


def test_non_chained_jobs_keep_running_after_failure(tmp_path):
    """Existing behaviour: unrelated jobs are not cancelled by a failure."""
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


# ---------------------------------------- watcher restart does not bypass

def test_restart_cancels_interrupted_job_with_failed_dep(tmp_path):
    """Scenario: worker crashed while synth was running; chunk had already failed.
    On restart with --requeue-interrupted, synth is requeued but then cancelled
    because its dependency (chunk) is in done/ as failed."""
    q = tmp_path / "q"

    chunk_job = jq.add_job(["chunk", "--section", "01_x"], q)
    chunk_job.update(status="failed", exit_code=1, finished=jq._now())
    jq._finish(chunk_job, q / "pending" / f"{chunk_job['id']}.json", q / "done")

    synth_job = jq.add_job(["synth", "--section", "01_x", "--workers", "2"], q,
                            depends_on=chunk_job["id"])
    synth_path = q / "pending" / f"{synth_job['id']}.json"
    synth_job.update(status="running", pid=99999)
    jq._write_json(synth_path, synth_job)

    ran = []
    code = jq.run_worker(q, lambda job, lp: ran.append(job) or 0,
                         poll=0.01, say=lambda s: None,
                         alive=lambda pid: False,
                         requeue_interrupted=True)
    assert code == 1 and ran == []
    statuses = {j["id"]: j["status"] for j in jq.list_jobs(q)}
    assert statuses[chunk_job["id"]] == "failed"
    assert statuses[synth_job["id"]] == "cancelled"


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
