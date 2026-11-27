"""Read-only waveform integrity screen. Signals are not perceptual verdicts."""
from __future__ import annotations

import io
import math
import numpy as np


def screen(data: bytes) -> dict:
    import soundfile as sf
    try:
        with sf.SoundFile(io.BytesIO(data)) as f:
            sr,channels,frames=f.samplerate,f.channels,f.frames
            if (f.format not in ("WAV","WAVEX","RF64") or channels!=1
                    or not 8000<=sr<=96000 or not 0<frames<=120*sr):
                return dict(status="invalid",reason="unsupported_audio_format")
            x=f.read(dtype="float64")
    except (RuntimeError, ValueError, OSError):
        return dict(status="invalid",reason="decode_failed")
    if len(x)!=frames or not np.isfinite(x).all():
        return dict(status="invalid",reason="nonfinite_or_truncated_audio")
    peak=float(np.max(np.abs(x)))
    rms=float(np.sqrt(np.mean(x*x)))
    if not math.isfinite(rms):
        return dict(status="invalid",reason="nonfinite_energy")
    signals=[]
    if peak==0:
        signals.append("digital_silence")
    if peak>=.999:
        signals.append("near_full_scale_peak")
    if abs(float(np.mean(x)))>=.05:
        signals.append("dc_offset")
    return dict(status="measured",sample_rate=sr,frames=frames,
                duration_s=frames/sr,peak=peak,rms=rms,
                near_full_scale_fraction=float(np.mean(np.abs(x)>=.999)),
                signals=signals,diagnostic_only=True)
