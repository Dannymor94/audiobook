"""Submit exactly one fixed public Kaggle notebook and verify its results."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import wave

def cli(*args):
    # Never print raw config, auth diagnostics, response headers, or secrets.
    result = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("KAGGLE_COMMAND_FAILED:" + args[0])
    return result.stdout

def main():
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN_NOT_CONFIGURED")
    config = cli("config", "view")
    m = re.search(r"(?m)^\s*-\s*username:\s*([a-zA-Z0-9_-]+)\s*$", config)
    if not m:
        raise RuntimeError("KAGGLE_ACCOUNT_NOT_RESOLVED")
    print("KAGGLE_AUTH_CONFIG_OK", flush=True)
    quota = json.loads(cli("quota", "--format", "json"))
    gpu = [r for r in quota if r["resource"] == "GPU"]
    if len(gpu) != 1 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?h", gpu[0]["remaining"]):
        raise RuntimeError("GPU_QUOTA_UNKNOWN")
    remaining = float(gpu[0]["remaining"][:-1])
    print(f"GPU_REMAINING_HOURS={remaining}", flush=True)
    if remaining < 1:
        raise RuntimeError("GPU_QUOTA_BELOW_RESERVE")
    run_id = os.environ["GITHUB_RUN_ID"]
    if not run_id.isdigit() or os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise RuntimeError("NO_AUTOMATIC_RESUBMISSION")
    slug = "audiobook-public-smoke-" + run_id
    kernel = m[1] + "/" + slug
    work = Path(os.environ["RUNNER_TEMP"]) / "public-kernel"
    work.mkdir(exist_ok=False)
    shutil.copyfile(Path(__file__).with_name("public_smoke.py"), work/"public_smoke.py")
    meta = dict(id=kernel, title="Audiobook Public Smoke " + run_id,
                code_file="public_smoke.py", language="python", kernel_type="script",
                is_private="true", enable_gpu="true", enable_internet="true",
                dataset_sources=[], competition_sources=[], kernel_sources=[], model_sources=[])
    (work/"kernel-metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    pushed = cli("kernels","push","-p",str(work),"--timeout","600","--accelerator","NvidiaTeslaT4")
    version = re.search(r"Kernel version (\d+) successfully pushed", pushed)
    if not version:
        raise RuntimeError("PUSH_NOT_CONFIRMED_NO_RETRY")
    ref = kernel + "/" + version[1]
    print("KAGGLE_SUBMITTED https://www.kaggle.com/code/" + ref, flush=True)
    deadline = time.monotonic() + 780
    while time.monotonic() < deadline:
        status = cli("kernels","status",ref)
        match = re.search(r'has status "([^"]+)"',status)
        if not match:
            raise RuntimeError("UNKNOWN_STATUS_NO_RETRY")
        state = match[1].split(".")[-1].lower()
        print("KAGGLE_STATUS=" + state, flush=True)
        if state == "complete":
            break
        if state not in ("queued","running","pending"):
            raise RuntimeError("KAGGLE_TERMINAL_FAILURE:" + state)
        time.sleep(20)
    else:
        raise RuntimeError("POLL_TIMEOUT_NO_RESUBMIT")
    output = Path(os.environ["RUNNER_TEMP"]) / "public-output"
    output.mkdir()
    cli("kernels","output",ref,"-p",str(output))
    receipt = output/"public_smoke"/"receipt.json"
    r = json.loads(receipt.read_bytes())
    if (r["policy"]!="kaggle-public-silero-smoke-v1" or r["status"]!="READY"
            or r["model_sha256"]!="ba41b18f6a707ad93605a162998865e7c087153d2e010a26dd02229dab0e672a"
            or r["release_ready"] is not False
            or [c["file"] for c in r["cases"]]!=[f"clip-{i:02d}.wav" for i in range(1,5)]):
        raise RuntimeError("RECEIPT_MISMATCH")
    for c in r["cases"]:
        p=receipt.parent/c["file"]
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=c["sha256"]:
            raise RuntimeError("WAV_HASH_MISMATCH")
        with wave.open(str(p),"rb") as wav:
            if wav.getnchannels()!=1 or wav.getframerate()!=24000 or wav.getnframes()!=c["samples"]:
                raise RuntimeError("WAV_HEADER_MISMATCH")
    print("KAGGLE_PUBLIC_RENDER_PASS")
    print(json.dumps(r))
if __name__=="__main__":
    main()
