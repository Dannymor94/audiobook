"""Fixed public Kaggle experiment. No arguments, reference voice or manuscript."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

URL = "https://models.silero.ai/models/tts/ru/v5_cis_base.pt"
SHA = "ba41b18f6a707ad93605a162998865e7c087153d2e010a26dd02229dab0e672a"
CASES = (
    "На холм+е сто+ял з+амок.",
    "На двер+и вис+ел зам+ок.",
    "На стол+е леж+али хл+еб, с+ыр и мук+а.",
    "+Это был+а насто+ящая м+ука.",
)
SPEAKER = "ru_bel_dmitriy"

def main():
    root = Path("/kaggle/working")
    # This is an accidental-environment guard, not provider attestation.
    if not root.is_dir() or not Path("/kaggle/input").is_dir():
        raise RuntimeError("KAGGLE_REQUIRED")
    if any(os.environ.get(k) for k in ("KAGGLE_API_TOKEN", "KAGGLE_KEY", "HF_TOKEN", "GITHUB_TOKEN")):
        raise RuntimeError("UNEXPECTED_CREDENTIAL_ENV")
    if any(Path("/kaggle/input").iterdir()):
        raise RuntimeError("NO_ATTACHED_DATA_ALLOWED")
    out = root / "public_smoke"
    out.mkdir(exist_ok=False)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    import numpy as np
    import soundfile as sf
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA_REQUIRED")
    gpu = torch.cuda.get_device_properties(0)
    if gpu.total_memory < 8 * 1024**3:
        raise RuntimeError("GPU_MEMORY_TOO_SMALL")
    torch.set_num_threads(2)
    torch.manual_seed(42)
    t0 = time.perf_counter()
    x = torch.ones((1024, 1024), device="cuda:0")
    assert float((x @ x)[0, 0].item()) == 1024
    del x
    torch.cuda.synchronize()
    # Public trusted publisher package, verified exact bytes before pickle load.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "silero.pt"
        digest = hashlib.sha256()
        total = 0
        start = time.perf_counter()
        with urllib.request.urlopen(URL, timeout=60) as response, path.open("wb") as target:
            if response.geturl() != URL:
                raise RuntimeError("UNEXPECTED_REDIRECT")
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 1024**3:
                    raise RuntimeError("DOWNLOAD_LIMIT")
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != SHA:
            raise RuntimeError("MODEL_HASH_MISMATCH")
        download_s = time.perf_counter() - start
        start = time.perf_counter()
        model = torch.package.PackageImporter(str(path)).load_pickle("tts_models", "model")
        model.to(torch.device("cuda:0"))
        if SPEAKER not in model.speakers:
            raise RuntimeError("SPEAKER_UNAVAILABLE")
        torch.cuda.synchronize()
        setup_s = time.perf_counter() - start
        rows = []
        for i, text in enumerate(CASES, 1):
            torch.manual_seed(42)
            torch.cuda.manual_seed_all(42)
            torch.cuda.synchronize()
            start = time.perf_counter()
            with torch.no_grad():
                wav = model.apply_tts(text=text, speaker=SPEAKER, sample_rate=24000)
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            audio = wav.detach().cpu().numpy()
            if audio.ndim != 1 or not 24000 <= len(audio) <= 30*24000 or not np.isfinite(audio).all() or not np.any(audio):
                raise RuntimeError("INVALID_AUDIO")
            name = f"clip-{i:02d}.wav"
            tmp = out / (name + ".part")
            sf.write(tmp, audio, 24000, format="WAV", subtype="PCM_16")
            tmp.replace(out / name)
            rows.append(dict(file=name, sha256=hashlib.sha256((out/name).read_bytes()).hexdigest(),
                             samples=len(audio), inference_s=elapsed, rtf=elapsed/(len(audio)/24000)))
        receipt = dict(policy="kaggle-public-silero-smoke-v1", status="READY",
                       model_sha256=SHA, gpu=gpu.name, gpu_count=torch.cuda.device_count(),
                       vram_bytes=gpu.total_memory, torch=str(torch.__version__), cuda=torch.version.cuda,
                       download_s=download_s, setup_s=setup_s, elapsed_s=time.perf_counter()-t0,
                       cases=rows, release_ready=False)
        (out/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print("PUBLIC_SILERO_GPU_READY")

if __name__ == "__main__":
    main()
