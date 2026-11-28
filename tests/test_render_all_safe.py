import json
import shutil
import subprocess
from pathlib import Path

import pytest

from audiobook import chunker, paths


def test_missing_only_preserves_existing_manifest_and_wav(tmp_path, monkeypatch):
    text = tmp_path / "text"
    blocks = text / "blocks"
    blocks.mkdir(parents=True)
    out = tmp_path / "out"
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    for nn in ("01", "02"):
        (blocks / f"{nn}_demo.blocks.json").write_text(json.dumps(
            {"nn": nn, "slug": "demo", "blocks": []}), encoding="utf-8")
        (text / f"{nn}_demo.norm.txt").write_text("а" * 60, encoding="utf-8")
    old = out / "sections" / "01_demo"
    (old / "chunks").mkdir(parents=True)
    manifest = old / "manifest.jsonl"
    original = b'{"id":"0001","locked":true,"status":"done"}\n'
    manifest.write_bytes(original)
    wav = old / "chunks" / "0001.wav"
    wav.write_bytes(b"approved audio")
    calls = []

    def load(nn, slug):
        calls.append(nn)
        return []

    monkeypatch.setattr(chunker, "load_units", load)
    monkeypatch.setattr(chunker, "build_manifest", lambda units, cfg: [
        {"id": "0001", "status": "pending"}])
    assert chunker.run({}, missing_only=True) == 0
    assert calls == ["02"]
    assert manifest.read_bytes() == original
    assert wav.read_bytes() == b"approved audio"
    assert (out / "sections" / "02_demo" / "manifest.jsonl").is_file()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_render_script_defaults_to_prepare_and_rejects_four(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "render_all.sh"
    copy = tmp_path / "render_all.sh"
    shutil.copyfile(script, copy)
    uv = tmp_path / "uv"
    uv.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" > "$CALL_LOG"\n',
                  encoding="utf-8")
    uv.chmod(0o755)
    import os
    log = tmp_path / "calls"
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("CALL_LOG", str(log))
    assert subprocess.run(["bash", str(copy)], check=False).returncode == 0
    assert log.read_text().strip() == "run --no-sync python -m audiobook chunk --missing-only"
    log.unlink()
    assert subprocess.run(["bash", str(copy), "--render", "--workers", "4"],
                          check=False).returncode == 2
    assert not log.exists()

    assert subprocess.run(["bash", str(copy), "--render"],
                          check=False).returncode == 2
    assert not log.exists()
