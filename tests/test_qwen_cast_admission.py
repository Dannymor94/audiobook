"""Casting operator must refuse other hosts before model/network access."""
import importlib.util
from pathlib import Path
import sys

import pytest

from audiobook import gamebox


@pytest.mark.parametrize("system,host", [("Darwin", "danny-serv"), ("Linux", "unknown")])
@pytest.mark.parametrize("script", ["qwen_cast_operator", "qwen_cast_provision"])
def test_cast_entry_fails_closed(monkeypatch, tmp_path, system, host, script):
    path = Path(__file__).resolve().parents[1] / "scripts" / (script+".py")
    spec = importlib.util.spec_from_file_location(script, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(gamebox.platform, "system", lambda: system)
    monkeypatch.setattr(gamebox.socket, "gethostname", lambda: host)
    if script.endswith("operator"):
        # Configuration only routes project paths; no model imports.
        monkeypatch.setattr(module, "configure", lambda a: None)
        args = [script, "--stage", "custom", "--production", str(tmp_path), "--out", str(tmp_path)]
    else:
        args = [script, "--assets", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(gamebox.GameboxRequired, match="GAMEBOX_REQUIRED"):
        module.main()
