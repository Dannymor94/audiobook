import pytest

from audiobook.stress_voicy import BASE_PIN, TARGET_PATTERN, TARGETS, apply_pairs, validate_config

torch = pytest.importorskip("torch")


def test_exact_config_and_target_inventory():
    cfg = dict(r=16, alpha=32, applied_to="talker.model", target_modules=TARGET_PATTERN,
               base="/public-cache/snapshots/" + BASE_PIN)
    validate_config(cfg)
    assert len(TARGETS) == len(set(TARGETS)) == 196
    for k, value in (("r", 8), ("alpha", 16), ("applied_to", "other"),
                     ("target_modules", ".*"), ("base", "/wrong")):
        with pytest.raises(ValueError, match="UNEXPECTED_VOICY_CONFIG"):
            validate_config({**cfg, k: value})


def test_merge_matches_upstream_bf16_rounding_and_only_target():
    stem = TARGETS[0]
    a = torch.arange(48).reshape(16, 3).to(torch.bfloat16) / 128
    b = torch.arange(32).reshape(2, 16).to(torch.bfloat16) / 128
    w = torch.tensor([[0.125, 0.25, 0.5], [0.75, 1.0, 1.25]], dtype=torch.float32)
    other = torch.ones(2)
    target = f"talker.model.{stem}.weight"
    params = {target: w, "other": other}
    tensors = {stem + ".lora_A.weight": a, stem + ".lora_B.weight": b}
    expected = (w.clone() + 2 * (b.float() @ a.float())).to(torch.bfloat16).float()
    apply_pairs(tensors, params, (stem,))
    assert torch.equal(w, expected)
    assert torch.equal(other, torch.ones(2))


def test_incomplete_or_wrong_shape_rejected_before_mutation():
    stem = TARGETS[0]
    w = torch.ones(2, 3)
    params = {f"talker.model.{stem}.weight": w}
    a = torch.ones(16, 3, dtype=torch.bfloat16)
    b = torch.ones(2, 16, dtype=torch.bfloat16)
    tensors = {stem + ".lora_A.weight": a, stem + ".lora_B.weight": b}
    for invalid in ({stem + ".lora_A.weight": a},
                    {**tensors, "unexpected": a},
                    {**tensors, stem + ".lora_B.weight": b[:, :8]},
                    {**tensors, stem + ".lora_A.weight": a.float()}):
        with pytest.raises(ValueError, match="ADAPTER_"):
            apply_pairs(invalid, params, (stem,))
        assert torch.equal(w, torch.ones_like(w))
