"""Слой 1: greptests и проверки, которые ловят Windows-ошибки на Mac."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "audiobook"
PY_FILES = list(SRC.rglob("*.py"))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_every_open_has_utf8():
    bad = []
    for p in PY_FILES:
        for i, line in enumerate(_read(p).splitlines(), 1):
            if re.search(r"\bopen\(", line) and "encoding=" not in line and "rb" not in line and "wb" not in line:
                bad.append(f"{p.name}:{i}")
    assert not bad, f"open() без encoding='utf-8' (на Windows cp1251): {bad}"


def test_no_string_path_joins():
    bad = []
    for p in PY_FILES:
        for i, line in enumerate(_read(p).splitlines(), 1):
            if "os.path.join" in line or re.search(r"""['"][^'"]*/[^'"]*['"]\s*\+""", line):
                bad.append(f"{p.name}:{i}")
    assert not bad, f"склейка путей строками — только pathlib: {bad}"


def test_no_hardcoded_home_cache():
    """Fires on code lines only; comments documenting ~/ are allowed."""
    bad = []
    for p in PY_FILES:
        for line in _read(p).splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "~/.cache" in line or "expanduser" in line:
                bad.append(f"{p.name}: {line.strip()!r}")
    assert not bad, f"обращение к домашнему кэшу: {bad}"


def test_no_hardcoded_home_cache_positive():
    """Greptest must fire on real expanduser/~/.cache in code, not only in comments."""
    def _check(src: str) -> list[str]:
        return [
            ln for ln in src.splitlines()
            if not ln.lstrip().startswith("#")
            and ("~/.cache" in ln or "expanduser" in ln)
        ]

    assert _check("# expanduser / ~/.cache mentioned in a comment\n") == []
    assert _check("path = os.path.expanduser('~/.cache')\n") != []


def test_main_guards_spawn():
    src = _read(SRC / "__main__.py")
    assert 'if __name__ == "__main__"' in src and "spawn" in src


def test_ffmpeg_lookup_prefers_bin(monkeypatch, tmp_path):
    from audiobook import paths
    monkeypatch.setattr(paths, "BIN", tmp_path)
    (tmp_path / "ffmpeg").touch()
    assert paths.ffmpeg() == tmp_path / "ffmpeg"


def test_config_loads_utf8():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for key in ("model", "reference", "pauses_ms", "qc", "master"):
        assert key in cfg
