"""Layer 1: preflight decision logic on injected values + thin I/O parsers. No models, no network."""
from __future__ import annotations

import subprocess

from audiobook import preflight as pf
from audiobook.preflight import Check, GitFacts, evaluate, format_rows, is_green

CLEAN = GitFacts("task/T01", "abc1234", (), True, "abc1234", 0, 0)


def _ev(**kw):
    base = dict(load1=0.5, available_gb=32.0, procs=[], git=CLEAN)
    base.update(kw)
    return evaluate(**base)


def _by(rows, prefix):
    return [r for r in rows if r.name.startswith(prefix)]


def test_all_green():
    rows = _ev()
    assert is_green(rows)
    assert all(r.ok is True for r in rows)


def test_load_threshold_and_override():
    assert _by(_ev(load1=4.0), "load")[0].ok is False          # not strictly below default 4
    assert _by(_ev(load1=3.99), "load")[0].ok is True
    assert _by(_ev(load1=6.0, max_load=8), "load")[0].ok is True


def test_ram_threshold_and_override():
    assert _by(_ev(available_gb=15.9), "RAM")[0].ok is False
    assert _by(_ev(available_gb=16.0), "RAM")[0].ok is True
    assert _by(_ev(available_gb=8.0, min_free_gb=4), "RAM")[0].ok is True


def test_unmeasurable_values_warn_not_fail():
    rows = _ev(load1=None, available_gb=None, procs=None, git=None)
    assert all(r.ok is None for r in rows)
    assert is_green(rows)                                       # WARN never turns RED
    assert all(line.startswith("WARN") for line in format_rows(rows))


def test_foreign_heavy_process_detected():
    procs = [(10, "/usr/bin/python -m audiobook synth --section 01"),
             (11, "sshd: user")]
    rows = _ev(procs=procs)
    r = _by(rows, "чужие тяжёлые")[0]
    assert r.ok is False and "10" in r.hint
    assert not is_green(rows)


def test_heavy_patterns():
    heavy = ["faster-whisper run", "python transcribe.py", "llama-server -m x.gguf",
             "uv run python -m audiobook qc --section 02",
             "python -m audiobook probe --max 60"]
    light = ["python -m audiobook doctor", "python -m audiobook preflight",
             "python -m audiobook queue list", "python -m audiobook synthesize-docs",
             "vim notes.txt"]
    procs = [(100 + i, a) for i, a in enumerate(heavy + light)]
    found = {a for _, a in pf.foreign_heavy(procs, frozenset())}
    assert found == set(heavy)


def test_own_pid_and_parent_excluded():
    procs = [(50, "python -m audiobook probe --dry-run"),      # us
             (49, "bash -c python -m audiobook synth --section 1"),   # our parent
             (7, "python -m audiobook synth --section 2")]            # foreign
    left = pf.foreign_heavy(procs, {50, 49})
    assert [pid for pid, _ in left] == [7]
    assert _by(_ev(procs=procs, own_pids={50, 49}), "чужие тяжёлые")[0].ok is False
    assert _by(_ev(procs=procs[:2], own_pids={50, 49}), "чужих")[0].ok is True


def test_git_dirty_is_red():
    g = GitFacts("main", "abc1234", (" M src/audiobook/x.py",), True, "abc1234", 0, 0)
    r = _by(_ev(git=g), "git: незакоммиченные")[0]
    assert r.ok is False and "x.py" in r.hint


def test_git_head_vs_origin():
    behind = GitFacts("b", "aaa", (), True, "bbb", 0, 2)
    r = _by(_ev(git=behind), "git HEAD !=")[0]
    assert r.ok is False and r.hint == "git pull" and "позади на 2" in r.name
    nobranch = GitFacts("b", "aaa", (), True, None)
    assert _by(_ev(git=nobranch), "git HEAD == origin/b")[0].ok is False
    offline = GitFacts("b", "aaa", (), False, "aaa")
    assert _by(_ev(git=offline), "git HEAD == origin/b")[0].ok is None
    assert is_green(_ev(git=offline))
    detached = GitFacts("HEAD", "aaa", (), True, None)
    assert _by(_ev(git=detached), "git ветка")[0].ok is False


def test_format_rows():
    lines = format_rows([Check("a", True), Check("b", False, "fix"), Check("c", None, "hm")])
    assert lines == ["GREEN  a", "RED    b  -> fix", "WARN   c  -> hm"]


def test_parse_ps_and_meminfo():
    out = "  PID COMMAND\n    1 /sbin/init\n  234 python -m audiobook synth --section 1\n"
    assert pf.parse_ps(out) == [(1, "/sbin/init"), (234, "python -m audiobook synth --section 1")]
    assert pf.parse_meminfo("MemTotal: 100 kB\nMemAvailable:   16777216 kB\n") == 16.0
    assert pf.parse_meminfo("nothing") is None


def test_read_git_against_local_remote(tmp_path):
    """Real git, local bare 'origin' on disk: no network involved."""
    def git(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", "-C", str(cwd), *a],
                              capture_output=True, text=True, encoding="utf-8", check=True)
    try:
        git(tmp_path, "--version")
    except (OSError, subprocess.CalledProcessError):
        import pytest
        pytest.skip("git недоступен")
    bare, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    git(tmp_path, "init", "-b", "main", str(work))
    (work / "f.txt").write_text("1", encoding="utf-8")
    git(work, "add", "f.txt")
    git(work, "commit", "-m", "one")
    git(work, "remote", "add", "origin", str(bare))
    git(work, "push", "origin", "main")

    facts = pf.read_git(work)
    assert facts.branch == "main" and facts.fetched and not facts.dirty
    assert facts.remote_head == facts.head and (facts.ahead, facts.behind) == (0, 0)
    assert is_green(evaluate(load1=0, available_gb=99, procs=[], git=facts))

    (work / "f.txt").write_text("2", encoding="utf-8")
    assert len(pf.read_git(work).dirty) == 1
    git(work, "commit", "-am", "two")
    ahead = pf.read_git(work)
    assert ahead.ahead == 1 and ahead.remote_head != ahead.head
    assert not is_green(evaluate(load1=0, available_gb=99, procs=[], git=ahead))

    git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    off = pf.read_git(work)
    assert off.fetched is False
    assert _by(evaluate(load1=0, available_gb=99, procs=[], git=off), "git HEAD == origin")[0].ok is None


def test_read_git_outside_repo_is_none(tmp_path):
    assert pf.read_git(tmp_path) is None
