"""Layer 1: model.quantize option (int8 dynamic quantization, CPU only).
No weights: qwen_tts and the snapshot lookup are faked. Placeholder text only."""
from __future__ import annotations

import json
import sys
import types

import pytest
import torch

from audiobook import paths, voicecfg

_BASE = {
    "model": {"name": "qwen3_tts", "seed": 42, "temperature": 1.0, "language": "ru"},
    "reference": {"path": "ref/ref1.wav"},
}


def _cfg(variant=None, quantize=None) -> dict:
    cfg = json.loads(json.dumps(_BASE))
    if variant is not None:
        cfg["model"]["variant"] = variant
    if quantize is not None:
        cfg["model"]["quantize"] = quantize
    return cfg


# ── voicecfg ──────────────────────────────────────────────────────────────────

def test_quantize_default_none_and_validation():
    assert voicecfg.quantize(_cfg()) == "none"
    assert voicecfg.quantize(_cfg(quantize="none")) == "none"
    assert voicecfg.quantize(_cfg(quantize="int8")) == "int8"
    assert voicecfg.quantize({}) == "none"
    with pytest.raises(SystemExit, match="quantize"):
        voicecfg.quantize(_cfg(quantize="int4"))


def test_model_id_none_identical_to_before():
    """quantize none (or absent) must not change any chunk hash."""
    assert voicecfg.model_id(_cfg()) == "qwen3_tts"
    assert voicecfg.model_id(_cfg(quantize="none")) == "qwen3_tts"
    assert voicecfg.model_id(_cfg(variant="1.7B")) == "qwen3_tts-1.7B"
    assert voicecfg.model_id(_cfg(variant="1.7B", quantize="none")) == "qwen3_tts-1.7B"


def test_model_id_int8_suffixed():
    assert voicecfg.model_id(_cfg(quantize="int8")) == "qwen3_tts-int8"
    assert voicecfg.model_id(_cfg(variant="1.7B", quantize="int8")) == "qwen3_tts-1.7B-int8"


def test_repo_config_quantize_is_none():
    import yaml
    cfg = yaml.safe_load((paths.ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert voicecfg.quantize(cfg) == "none"


# ── worker_config / worker ────────────────────────────────────────────────────

def test_worker_config_carries_quantize(monkeypatch, tmp_path):
    from audiobook.synth import worker_config
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    (tmp_path / "ref").mkdir()
    (tmp_path / "ref" / "ref1.latents.pt").write_bytes(b"x")
    assert worker_config(_cfg())["quantize"] == "none"
    assert worker_config(_cfg(quantize="int8"))["quantize"] == "int8"


def test_worker_passes_quantize_to_load_model():
    import inspect
    from audiobook import worker
    src = inspect.getsource(worker._worker_loop)
    assert 'cfg.get("quantize", "none")' in src


# ── load_model ────────────────────────────────────────────────────────────────

class _Inner(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.lin = torch.nn.Linear(4, 4)


@pytest.fixture
def fake_qwen(monkeypatch):
    import audiobook.synth as synth_mod
    # This fixture replaces the real model with a tiny in-memory fake.
    monkeypatch.setattr(synth_mod, "require_gamebox", lambda: None)
    monkeypatch.setattr(synth_mod, "_model", None)
    monkeypatch.setattr(synth_mod, "_model_key", None)
    monkeypatch.setattr(synth_mod, "_local_snapshot", lambda variant="0.6B": paths.ROOT)
    loads = []

    class FakeModel:
        def __init__(self):
            self.model = _Inner()

        @classmethod
        def from_pretrained(cls, path, dtype=None):
            loads.append(path)
            return cls()

    mod = types.ModuleType("qwen_tts")
    mod.Qwen3TTSModel = FakeModel
    monkeypatch.setitem(sys.modules, "qwen_tts", mod)
    return synth_mod, loads


def test_load_model_none_does_not_quantize(fake_qwen, monkeypatch):
    synth_mod, _ = fake_qwen
    calls = []
    monkeypatch.setattr(torch.ao.quantization, "quantize_dynamic",
                        lambda *a, **k: calls.append((a, k)))
    m = synth_mod.load_model("cpu", "1.7B")
    assert calls == []
    assert isinstance(m.model.lin, torch.nn.Linear)


def test_load_model_int8_calls_quantize_dynamic(fake_qwen, monkeypatch):
    synth_mod, _ = fake_qwen
    calls = []
    sentinel = object()

    def fake_qd(model, spec, dtype=None, **kwargs):
        calls.append((model, spec, dtype))
        return sentinel

    monkeypatch.setattr(torch.ao.quantization, "quantize_dynamic", fake_qd)
    m = synth_mod.load_model("cpu", "1.7B", "int8")
    assert len(calls) == 1
    assert isinstance(calls[0][0], _Inner)
    assert calls[0][1] == {torch.nn.Linear}
    assert calls[0][2] == torch.qint8
    assert m.model is sentinel  # result assigned back


@pytest.mark.skipif(
    not set(torch.backends.quantized.supported_engines) - {"none"}
    or torch.backends.quantized.engine == "none",
    reason="Нет доступного активного движка квантизации torch",
)
def test_load_model_int8_real_quantize_swaps_linear(fake_qwen):
    synth_mod, _ = fake_qwen
    m = synth_mod.load_model("cpu", "1.7B", "int8")
    assert "quantized" in type(m.model.lin).__module__


def test_load_model_int8_requires_cpu(fake_qwen):
    synth_mod, loads = fake_qwen
    with pytest.raises(SystemExit, match="cpu"):
        synth_mod.load_model("cuda", "1.7B", "int8")
    assert loads == []


def test_load_model_rejects_bad_quantize(fake_qwen):
    synth_mod, _ = fake_qwen
    with pytest.raises(SystemExit):
        synth_mod.load_model("cpu", "1.7B", "int4")


@pytest.mark.skipif(
    not set(torch.backends.quantized.supported_engines) - {"none"}
    or torch.backends.quantized.engine == "none",
    reason="Нет доступного активного движка квантизации torch",
)
def test_load_model_cache_keyed_by_quantize(fake_qwen):
    synth_mod, loads = fake_qwen
    a = synth_mod.load_model("cpu", "1.7B", "none")
    assert synth_mod.load_model("cpu", "1.7B", "none") is a
    assert len(loads) == 1
    b = synth_mod.load_model("cpu", "1.7B", "int8")
    assert b is not a and len(loads) == 2
