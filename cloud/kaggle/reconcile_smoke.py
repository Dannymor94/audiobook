"""Read-only reconciliation of the first exact Kaggle job. Never submits."""
import hashlib
import json
import os
from pathlib import Path
import re
import wave
from submit_smoke import cli

REF = "dannymorozov/audiobook-public-smoke-46019695614/1"

def main():
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN_NOT_CONFIGURED")
    quota = json.loads(cli("quota", "--format", "json"))
    gpu = [r for r in quota if r["resource"] == "GPU"]
    if len(gpu) != 1:
        raise RuntimeError("GPU_QUOTA_UNKNOWN")
    print("GPU_QUOTA=" + json.dumps({k: gpu[0].get(k) for k in ("used","remaining","total","refreshAt")}), flush=True)
    status = cli("kernels","status",REF)
    match = re.search(r'has status "([^"]+)"',status)
    if not match:
        raise RuntimeError("UNKNOWN_STATUS_KEEP_RESERVATION")
    state = match[1].split(".")[-1].lower()
    print("EXACT_REMOTE_STATUS="+state, flush=True)
    if state != "complete":
        print("NO_NEW_SUBMISSION_RESERVATION_RETAINED_PENDING_RECONCILIATION")
        return
    output = Path(os.environ["RUNNER_TEMP"]) / "reconciled-output"
    output.mkdir(exist_ok=False)
    cli("kernels","output",REF,"-p",str(output))
    receipt = output/"public_smoke"/"receipt.json"
    r = json.loads(receipt.read_bytes())
    if (r["policy"]!="kaggle-public-silero-smoke-v1" or r["status"]!="READY"
            or r["model_sha256"]!="ba41b18f6a707ad93605a162998865e7c087153d2e010a26dd02229dab0e672a"
            or r["release_ready"] is not False
            or [c["file"] for c in r["cases"]]!=[f"clip-{i:02d}.wav" for i in range(1,5)]):
        raise RuntimeError("RECEIPT_MISMATCH")
    for c in r["cases"]:
        p=receipt.parent/c["file"]
        if p.is_symlink() or p.stat().st_size>2*1024**2 or hashlib.sha256(p.read_bytes()).hexdigest()!=c["sha256"]:
            raise RuntimeError("WAV_HASH_MISMATCH")
        with wave.open(str(p),"rb") as wav:
            if wav.getnchannels()!=1 or wav.getframerate()!=24000 or wav.getnframes()!=c["samples"]:
                raise RuntimeError("WAV_HEADER_MISMATCH")
    print("KAGGLE_PUBLIC_RENDER_PASS")
    print(json.dumps(r))
if __name__=="__main__":
    main()
