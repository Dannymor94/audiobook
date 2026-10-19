#!/usr/bin/env python3
import scipy.io.wavfile as wf, numpy as np
from pathlib import Path
sr, data = wf.read("ref/ref3.wav")
d = data.astype(np.float32) / 32768
ws = int(sr * 0.01)  # 10ms windows
print("400-900ms RMS profile (looking for speech onset after gap):")
for i in range(40, 90):
    chunk = d[i*ws:(i+1)*ws]
    rms = float(np.sqrt(np.mean(chunk**2)))
    bar = min(int(rms * 200), 40)
    print(f"{i*10:4d}ms rms={rms:.4f}  {'#'*bar}")
