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
