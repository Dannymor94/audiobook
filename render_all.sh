#!/usr/bin/env bash
# Safe two-phase book rendering. No synth unless --render is explicit.
# ./render_all.sh --prepare-only  # create missing manifests, no TTS
# ./render_all.sh --render [--workers 1|2]  # use existing manifests and queue
# Run on gamebox, in persistent tmux/session. No automatic shutdown.
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ ! -f .env ] || . ./.env; set +a
export PYTHONUTF8=1

WORKERS=2
MODE=prepare
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prepare-only) MODE=prepare; shift ;;
    --render) MODE=render; shift ;;
    --workers) [ "$#" -ge 2 ] || exit 2; WORKERS="$2"; shift 2 ;;
    *) echo "Unsupported argument: $1" >&2; exit 2 ;;
  esac
done
case "$WORKERS" in
  1|2) ;;
  *) echo "1.7B: only 1 or 2 workers permitted" >&2; exit 2 ;;
esac
if [ "$MODE" = prepare ]; then
  uv run --no-sync python -m audiobook chunk --missing-only
  exit 0
fi

# Conservative admission budget: measured ~11.6 GB per worker plus reserve.
# Linux MemAvailable includes reclaimable cache; it is not a peak-RSS guarantee.
if [ ! -r /proc/meminfo ]; then
  echo "Render must run on Linux gamebox with measurable RAM" >&2; exit 2
fi
AVAILABLE_KIB=$(awk '$1 == "MemAvailable:" {print $2}' /proc/meminfo)
MIN_KIB=$(( (WORKERS * 12 + 3) * 1024 * 1024 ))
if [[ ! "$AVAILABLE_KIB" =~ ^[0-9]+$ ]] || [ "$AVAILABLE_KIB" -lt "$MIN_KIB" ]; then
  echo "Insufficient available RAM for $WORKERS workers: need $MIN_KIB KiB; measured $AVAILABLE_KIB KiB" >&2
  exit 2
fi

# Do not rechunk at render time. Validate all canonical manifests first, then
# enqueue existing section synth jobs under the same lock as the queue worker.
uv run --no-sync python - "$WORKERS" <<'PY'
import json
import sys
from audiobook import paths, jobqueue
from audiobook.__main__ import load_config
from audiobook.synth import ensure_manifest_current, worker_config

paths.apply_env_defaults()
workers = int(sys.argv[1])
config = load_config()
worker_config(config, workers)
with jobqueue.heavy_command_lock("render-all-preflight"):
    jobs = jobqueue.list_jobs()
    if any(j.get("status") in ("pending", "running", "unreadable") for j in jobs):
        raise SystemExit("Queue must be empty of active jobs before book enqueue")
    sections = []
    for jf in sorted((paths.TEXT / "blocks").glob("*.blocks.json")):
        b = json.loads(jf.read_text(encoding="utf-8"))
        sec = f"{b['nn']}_{b['slug']}"
        norm = paths.TEXT / f"{sec}.norm.txt"
        if not norm.exists():
            raise SystemExit(f"Missing normalized source: {sec}")
        if norm.stat().st_size < 50:
            continue
        sections.append(sec)
    if not sections or len(set(sections)) != len(sections):
        raise SystemExit("Invalid canonical section inventory")
    planned = []
    for sec in sections:
        folder = paths.OUT / "sections" / sec
        mf = folder / "manifest.jsonl"
        if not mf.is_file():
            raise SystemExit(f"Missing manifest: {sec}; run --prepare-only first")
        ensure_manifest_current(config, sec)
        rows = [json.loads(line) for line in mf.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            raise SystemExit(f"Empty manifest: {sec}")
        needs = False
        for row in rows:
            wav = folder / "chunks" / f"{row['id']}.wav"
            if row.get("locked") and (row.get("status") != "done" or not wav.is_file()):
                raise SystemExit(f"Invalid locked audio: {sec}/{row['id']}")
            if row.get("status") != "done" or not wav.is_file():
                needs = True
        if needs:
            planned.append(["synth", "--section", sec, "--workers", str(workers)])
    jobqueue.add_many(planned)
    print(f"Enqueued {len(planned)} section synth jobs; {len(sections)} canonical sections.")
PY
uv run --no-sync python -m audiobook queue run

# A successful worker exit is not by itself evidence that every chunk is done.
uv run --no-sync python - <<'PY'
import json
from audiobook import paths
pending = 0
for jf in sorted((paths.TEXT / "blocks").glob("*.blocks.json")):
    b = json.loads(jf.read_text(encoding="utf-8"))
    sec = f"{b['nn']}_{b['slug']}"
    norm = paths.TEXT / f"{sec}.norm.txt"
    if norm.stat().st_size < 50:
        continue
    folder = paths.OUT / "sections" / sec
    for line in (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pending += int(row.get("status") != "done" or not (folder / "chunks" / f"{row['id']}.wav").is_file())
print(f"Remaining incomplete chunks: {pending}")
raise SystemExit(1 if pending else 0)
PY
