"""Слой 2: все тесты идут в условиях, максимально похожих на Windows-прод."""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

mp.set_start_method("spawn", force=True)   # fork на Mac прячет ошибки


@pytest.fixture(autouse=True)
def windows_like_env(tmp_path, monkeypatch):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(fake_home / ".cache"))
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("AUDIOBOOK_DEVICE", "cpu")
    # A developer's .env must never make a test post to Telegram.
    monkeypatch.delenv("AUDIOBOOK_TG_TOKEN", raising=False)
    monkeypatch.delenv("AUDIOBOOK_TG_CHAT", raising=False)
    monkeypatch.setenv("TTS_HOME", str(ROOT / "models" / "tts"))
    monkeypatch.setenv("HF_HOME", str(ROOT / "models" / "hf"))
    yield fake_home
    leaked = [p for p in fake_home.rglob("*") if p.is_file()]
    assert not leaked, f"пайплайн пишет мимо models/: {leaked[:5]}"


@pytest.fixture
def slow():
    if os.environ.get("RUN_SLOW") != "1":
        pytest.skip("RUN_SLOW=1 для тестов с реальными моделями")
