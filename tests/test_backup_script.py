"""Layer 1: scripts/mac/backup_gamebox.sh — additive only (no --delete, no rm),
the excludes, the lock, the one-line summary; launchd template and README."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "scripts" / "mac"
SCRIPT = MAC / "backup_gamebox.sh"
EXCLUDES = ("--exclude='*.part'", "--exclude='*.part.*'", "--exclude='*.tmp'",
            "--exclude='/export/_old/'", "--exclude='/listen/chunks/'",
            "--exclude='/queue/heavy.lock'")
needs_bash = pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None,
                                reason="needs bash")


def test_backup_script_is_additive_and_has_excludes():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in text
    for bad in ("--delete", "--remove-source-files", "--move", "rm ", "--inplace", "--partial"):
        assert bad not in text, bad
    for ex in EXCLUDES:
        assert ex in text, ex
    assert '"${HOST}:audiobook/out/"' in text and 'HOST="gamebox"' in text
    assert "AudiobookBackup" in text and os.access(SCRIPT, os.X_OK)


def test_mac_scripts_never_remove_files():
    scripts = sorted(MAC.glob("*.sh"))
    assert {p.name for p in scripts} >= {"fetch_results.sh", "backup_gamebox.sh"}
    for p in scripts:
        text = p.read_text(encoding="utf-8")
        for bad in ("rm ", "--delete", "--remove-source-files", "unlink "):
            assert bad not in text, f"{p.name}: {bad}"


def _fake_bin(tmp_path: Path, body: str, name: str = "rsync") -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / name
    fake.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return bin_dir


_STATS = ('printf "%s\\n" "$@" > "$RSYNC_ARGS"\n'
          'echo "Number of files: 20 (reg: 18, dir: 2)"\n'
          'echo "Number of regular files transferred: 7"\n'
          'echo "Total transferred file size: 1,234,567 bytes"\n'
          'exit "${RSYNC_RC:-0}"\n')


def _run(tmp_path, *args, rc=0, check=True):
    bin_dir = _fake_bin(tmp_path, _STATS)
    args_file, base = tmp_path / "args.txt", tmp_path / "backup"
    args_file.unlink(missing_ok=True)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "RSYNC_ARGS": str(args_file), "AUDIOBOOK_BACKUP_DIR": str(base),
           "RSYNC_RC": str(rc)}
    res = subprocess.run(["bash", str(SCRIPT), *args], env=env, check=check,
                         capture_output=True, text=True, encoding="utf-8")
    got = args_file.read_text(encoding="utf-8").splitlines() if args_file.exists() else None
    return res, got, base


@needs_bash
def test_backup_rsync_args_and_summary(tmp_path):
    res, args, base = _run(tmp_path)
    assert args[-2] == "gamebox:audiobook/out/" and args[-1] == f"{base / 'out'}/"
    assert "-a" in args and "--stats" in args and "--dry-run" not in args
    assert not any(a.startswith(("--delete", "--remove")) for a in args)
    for ex in EXCLUDES:
        assert ex.replace("'", "") in args
    lines = res.stdout.strip().splitlines()
    assert len(lines) == 1 and "файлов 7" in lines[0] and "байт 1,234,567" in lines[0]
    assert not (base / ".backup.lock").exists()           # released on exit
    _res, args, _ = _run(tmp_path, "otherhost", "--dry-run")
    assert args[-2] == "otherhost:audiobook/out/" and "--dry-run" in args
    assert "пробный прогон" in _res.stdout


@needs_bash
def test_backup_errors_and_vanished_files(tmp_path):
    res, _args, _ = _run(tmp_path, rc=24)                  # files vanished mid-run: fine
    assert res.returncode == 0
    res, _args, _ = _run(tmp_path, rc=12, check=False)
    assert res.returncode == 12 and "ОШИБКА" in res.stderr
    res, args, _ = _run(tmp_path, "--bogus", check=False)
    assert res.returncode == 2 and args is None


@needs_bash
def test_backup_lock_skips_concurrent_run_and_takes_stale_one(tmp_path):
    base = tmp_path / "backup"
    (base / ".backup.lock").mkdir(parents=True)
    (base / ".backup.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")  # alive
    res, args, _ = _run(tmp_path)
    assert args is None and "уже идёт" in res.stdout
    assert (base / ".backup.lock").is_dir()                # someone else's lock stays
    dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()
    (base / ".backup.pid").write_text(f"{dead}\n", encoding="utf-8")
    res, args, _ = _run(tmp_path)
    assert args is not None and "забираю" in res.stdout
    assert not (base / ".backup.lock").exists()


@needs_bash
@pytest.mark.skipif(shutil.which("rsync") is None, reason="needs real rsync")
def test_backup_end_to_end_with_real_rsync(tmp_path):
    """Real rsync through a fake ssh that runs the remote side locally."""
    remote_home = tmp_path / "remote"
    out = remote_home / "audiobook" / "out"
    files = {
        "sections/01_a/chunks/c1.wav": True, "sections/01_a/manifest.jsonl": True,
        "sections/01_a/section.mp3": True, "queue/done/1.json": True,
        "queue/logs/1.log": True, "export/book.mp3": True, "listen/plan.mp3": True,
        "sections/01_a/chunks/c2.wav.part": False, "sections/01_a/x.part.wav": False,
        "sections/01_a/manifest.jsonl.tmp": False, "export/_old/s1/book.mp3": False,
        "listen/chunks/c1.wav": False, "queue/heavy.lock": False,
    }
    for rel in files:
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"data " + rel.encode("utf-8"))
    bin_dir = _fake_bin(tmp_path, (
        'while [ "$1" = "-o" ]; do shift 2; done\n'
        'shift\n'                                   # host
        'cd "$FAKE_REMOTE_HOME" && exec sh -c "$*"\n'), name="ssh")
    base = tmp_path / "backup"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "FAKE_REMOTE_HOME": str(remote_home), "AUDIOBOOK_BACKUP_DIR": str(base)}

    def run(*a):
        return subprocess.run(["bash", str(SCRIPT), *a], env=env, check=True,
                              capture_output=True, text=True, encoding="utf-8")

    run("--dry-run")
    assert not any(p.is_file() for p in (base / "out").rglob("*"))   # dry run copies nothing
    res = run()
    for rel, kept in files.items():
        assert (base / "out" / rel).is_file() == kept, rel
    assert "файлов 7" in res.stdout
    (out / "sections" / "01_a" / "section.mp3").unlink()    # gone on the host…
    res = run()
    assert (base / "out" / "sections" / "01_a" / "section.mp3").is_file()   # …stays in backup
    assert "файлов 0" in res.stdout


def test_launchd_template_and_readme():
    plist = (MAC / "com.audiobook.backup.plist.template").read_text(encoding="utf-8")
    assert "<integer>10800</integer>" in plist and "StartInterval" in plist
    assert "/bin/bash" in plist and "<string>-lc</string>" in plist
    assert "PATH_TO_AUDIOBOOK/scripts/mac/backup_gamebox.sh" in plist
    assert "AudiobookBackup/backup.log" in plist
    assert "/Users/" not in plist and "/home/" not in plist
    import plistlib
    data = plistlib.loads(plist.encode("utf-8"))
    assert data["Label"] == "com.audiobook.backup" and data["StartInterval"] == 10800
    readme = (MAC / "README.md").read_text(encoding="utf-8")
    for s in ("launchctl load", "launchctl unload", "~/Library/LaunchAgents",
              "PATH_TO_AUDIOBOOK", "--dry-run", "без `--delete`", "backup.log"):
        assert s in readme, s
