"""Layer-1 tests for parallel-synth planning (resume + partition). No models."""
from __future__ import annotations


def _rows(n: int, status="pending") -> list[dict]:
    return [{"id": f"{i:04d}", "text": f"chunk {i}", "hash": f"h{i}",
             "status": status} for i in range(n)]


def test_partition_round_robin_covers_all_and_balances(tmp_path):
    from audiobook.synth import _plan_parallel
    groups, skipped = _plan_parallel(_rows(10), tmp_path, num_workers=4)
    assert skipped == 0
    assert [len(g) for g in groups] == [3, 3, 2, 2]          # 10 round-robin over 4
    ids = sorted(r["id"] for g in groups for r in g)
    assert ids == [f"{i:04d}" for i in range(10)]            # every chunk placed once


def test_done_with_wav_is_skipped_missing_wav_resynths(tmp_path):
    from audiobook.synth import _plan_parallel
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    rows = _rows(4)
    rows[0]["status"] = "done"; (chunks_dir / "0000.wav").write_bytes(b"x")  # done + wav → skip
    rows[1]["status"] = "done"                                                # done, no wav → redo
    rows[2]["status"] = "timeout"                                             # not done → redo
    # rows[3] pending → redo
    groups, skipped = _plan_parallel(rows, chunks_dir, num_workers=2)
    assert skipped == 1
    todo_ids = sorted(r["id"] for g in groups for r in g)
    assert todo_ids == ["0001", "0002", "0003"]


def test_all_done_leaves_no_work(tmp_path):
    from audiobook.synth import _plan_parallel
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    rows = _rows(3, status="done")
    for r in rows:
        (chunks_dir / f"{r['id']}.wav").write_bytes(b"x")
    groups, skipped = _plan_parallel(rows, chunks_dir, num_workers=4)
    assert skipped == 3
    assert not any(groups)
