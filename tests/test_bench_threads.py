"""render.cpu_threads + bench aggregation (no models)."""
import os

from audiobook import bench
from audiobook.device import threads_per_worker


def test_threads_default_and_override():
    n = os.cpu_count() or 4
    assert threads_per_worker(2) == max(1, n // 2)
    assert threads_per_worker(2, 6) == 6
    assert threads_per_worker(2, 0) == max(1, n // 2)   # empty/0 → default


def test_effective_rtf_uses_slowest_worker():
    assert bench.effective_rtf([(60.0, 10.0), (30.0, 10.0)]) == 3.0


def test_worker_config_passes_cpu_threads(monkeypatch, tmp_path):
    from audiobook import synth, voicecfg
    lat = tmp_path / "lat.pt"
    lat.write_bytes(b"x")
    monkeypatch.setattr(voicecfg, "latents_path", lambda c: lat)
    cfg = {"model": {"name": "qwen3_tts", "variant": "1.7B", "temperature": 1.0, "language": "ru"},
           "render": {"cpu_threads": 6}, "pauses_ms": {}}
    assert synth.worker_config(cfg, 2)["cpu_threads"] == 6
    cfg["render"] = {}
    assert synth.worker_config(cfg, 2)["cpu_threads"] is None
