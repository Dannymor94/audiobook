"""Слой 3: реальные модели. RUN_SLOW=1 pytest -m slow"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slow


def test_xtts_synth_and_whisper_qc(slow, tmp_path):
    import difflib
    import soundfile as sf
    from TTS.api import TTS
    from faster_whisper import WhisperModel

    from audiobook import paths
    from audiobook.device import pick_device

    text = "Ты не поломан. Ты просто давно не слышал себя."
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(pick_device())
    wav = tts.tts(text=text, speaker_wav=str(paths.REF / "isaev_ref.wav"), language="ru")
    out = tmp_path / "x.wav"
    sf.write(out, wav, 24000)

    model = WhisperModel(str(paths.MODELS / "whisper" / "small"), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(out), language="ru")
    got = " ".join(s.text for s in segs).strip().lower()
    cer = 1 - difflib.SequenceMatcher(None, got, text.lower()).ratio()
    assert cer < 0.10, (got, cer)


def test_int8_renders_short_placeholder_phrase(slow):
    """int8 (dynamic quantization) on CPU renders one short placeholder phrase.
    Layer-3 smoke only: checks a non-silent wav comes out; the audible quality
    verdict is the G03 golden-set listening, not this test."""
    import numpy as np
    import yaml

    from audiobook import paths, voicecfg
    from audiobook.synth import load_latents, load_model, synthesize

    cfg = yaml.safe_load((paths.ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["model"]["quantize"] = "int8"
    model = load_model("cpu", voicecfg.variant(cfg), voicecfg.quantize(cfg))
    latents = load_latents(voicecfg.latents_path(cfg))
    wav = synthesize(model, "Тестовая фраза для проверки.", latents,
                     cfg["model"]["seed"], cfg["model"]["temperature"],
                     cfg["model"]["language"])
    assert len(wav) > 0 and float(np.abs(wav).max()) > 1e-3
