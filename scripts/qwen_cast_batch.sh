#!/usr/bin/env bash
# Usage: bash scripts/qwen_cast_batch.sh PRODUCTION_ROOT PRIVATE_OUTPUT_ROOT
# Start only after explicit provisioning has completed and pytest is green.
set -u
production=$1
cast_out=$2
task_root=$(cd "$(dirname "$0")/.." && pwd)
export PYTHONPATH="$task_root/src"
export HF_HOME="$production/models/hf"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 AUDIOBOOK_DEVICE=cpu
unset AUDIOBOOK_TG_TOKEN AUDIOBOOK_TG_CHAT
date -u +%FT%TZ > "$cast_out/batch.started.txt"
echo $$ > "$cast_out/batch.pid"
for stage in plan custom design base finish; do
    "$production/.venv/bin/python" -u "$task_root/scripts/qwen_cast_operator.py" \
        --stage "$stage" --production "$production" --out "$cast_out" \
        > "$cast_out/$stage.log" 2>&1
    result=$?
    echo "$result" > "$cast_out/$stage.exit-code.txt"
    if [ "$stage" = plan ] && [ "$result" -ne 0 ]; then
        echo "$result" > "$cast_out/batch.exit-code.txt"
        date -u +%FT%TZ > "$cast_out/batch.finished.txt"
        exit "$result"
    fi
done
date -u +%FT%TZ > "$cast_out/batch.finished.txt"
echo 0 > "$cast_out/batch.exit-code.txt"
