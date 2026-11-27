"""Legacy submission disabled. CLI helper retained for exact-job reconciliation."""
import subprocess

def cli(*args):
    # Never print raw config, auth diagnostics, response headers, or secrets.
    result = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("KAGGLE_COMMAND_FAILED:" + args[0])
    return result.stdout


def main():
    raise RuntimeError("SUBMISSION_LOCKED_CLOUD_QUOTA_01")

if __name__=="__main__":
    main()
