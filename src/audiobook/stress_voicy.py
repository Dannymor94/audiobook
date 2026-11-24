"""Pinned Voicy v3 LoRA for an isolated in-memory S4b diagnostic only.

Reference algorithm: olluorg/voicy scripts/stress_ft_merge.py.
No PEFT, checkpoint writes, network, or production adapter registration.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

BASE_REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
BASE_PIN = "fd4b254389122332181a7c3db7f27e918eec64e3"
ADAPTER_PIN = "e644ae00257fdd4db0e51b11057370dff6be8bc2"
ADAPTER_SHA256 = "702338d0e81ef8d04715ebd19ebe5eaf43b83446c04ee37f1a9108a9235f2b99"
TARGET_PATTERN = r"layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj)"
TARGETS = tuple(f"layers.{i}.{kind}.{name}_proj" for i in range(28)
                for kind, names in (("self_attn", ("q", "k", "v", "o")),
                                    ("mlp", ("gate", "up", "down")))
                for name in names)


def validate_config(cfg: dict) -> None:
    if (type(cfg.get("r")) is not int or cfg["r"] != 16
            or type(cfg.get("alpha")) is not int or cfg["alpha"] != 32
            or cfg.get("applied_to") != "talker.model"
            or cfg.get("target_modules") != TARGET_PATTERN
            or cfg.get("base") != BASE_REPO
            or cfg.get("base_revision") != BASE_PIN):
        raise ValueError("UNEXPECTED_VOICY_CONFIG")


def validate_pairs(tensors: dict, params: dict, targets: tuple[str, ...]) -> None:
    import torch

    expected = {f"{stem}.lora_{part}.weight" for stem in targets for part in ("A", "B")}
    if set(tensors) != expected:
        raise ValueError("ADAPTER_INVENTORY_MISMATCH")
    for stem in targets:
        w = params.get(f"talker.model.{stem}.weight")
        a, b = (tensors[f"{stem}.lora_{part}.weight"] for part in ("A", "B"))
        if (w is None or w.ndim != 2 or w.dtype != torch.float32 or w.device.type != "cpu"
                or a.dtype != torch.bfloat16 or b.dtype != torch.bfloat16
                or a.device.type != "cpu" or b.device.type != "cpu"
                or tuple(a.shape) != (16, w.shape[1]) or tuple(b.shape) != (w.shape[0], 16)
                or not torch.isfinite(a).all() or not torch.isfinite(b).all()):
            raise ValueError("ADAPTER_TARGET_MISMATCH")


def apply_pairs(tensors: dict, params: dict, targets: tuple[str, ...]) -> None:
    """Match upstream BF16 checkpoint merge, then cast into FP32 inference model."""
    import torch

    validate_pairs(tensors, params, targets)
    # No inference is allowed if any update fails; caller must discard the model.
    with torch.no_grad():
        for stem in targets:
            w = params[f"talker.model.{stem}.weight"]
            a, b = (tensors[f"{stem}.lora_{part}.weight"] for part in ("A", "B"))
            merged = (w + (b.float() @ a.float()) * 2.0).to(torch.bfloat16).float()
            if not torch.isfinite(merged).all():
                raise ValueError("NONFINITE_MERGE")
            w.copy_(merged)


def read_adapter(adapter_dir: Path) -> tuple[bytes, bytes]:
    """Fail before loading the large TTS model; actual merge rechecks bytes."""
    if not all((adapter_dir / name).is_file() for name in ("adapter.json", "adapter.safetensors")):
        raise ValueError("ADAPTER_FILES_MISSING")
    cfg_bytes = (adapter_dir / "adapter.json").read_bytes()
    validate_config(json.loads(cfg_bytes))
    data = (adapter_dir / "adapter.safetensors").read_bytes()
    if len(data) != 34908456 or hashlib.sha256(data).hexdigest() != ADAPTER_SHA256:
        raise ValueError("ADAPTER_DIGEST_MISMATCH")
    return cfg_bytes, data


def apply_voicy(model, snapshot: Path, adapter_dir: Path) -> dict:
    from safetensors import safe_open
    from safetensors.torch import load

    if snapshot.name != BASE_PIN:
        raise ValueError("BASE_REVISION_MISMATCH")
    cfg_bytes, data = read_adapter(adapter_dir)
    tensors = load(data)
    if sum(t.numel() for t in tensors.values()) != 17432576:
        raise ValueError("ADAPTER_PARAMETER_COUNT_MISMATCH")
    params = dict(model.named_parameters())
    validate_pairs(tensors, params, TARGETS)
    # Upstream merges in original checkpoint dtype. Require BF16 for every
    # targeted matrix instead of silently using a different rounding scheme.
    with safe_open(str(snapshot / "model.safetensors"), framework="pt", device="cpu") as f:
        for stem in TARGETS:
            name = f"talker.model.{stem}.weight"
            source = f.get_slice(name)
            if source.get_dtype() != "BF16" or tuple(source.get_shape()) != tuple(params[name].shape):
                raise ValueError("BASE_TARGET_DTYPE_OR_SHAPE_MISMATCH")
    apply_pairs(tensors, params, TARGETS)
    return dict(adapter_revision=ADAPTER_PIN, adapter_sha256=ADAPTER_SHA256,
                adapter_config_sha256=hashlib.sha256(cfg_bytes).hexdigest(),
                base_revision=BASE_PIN, matrices=len(TARGETS), scale=2.0,
                merge_dtype="bf16", inference_dtype="fp32", checkpoint_written=False)
