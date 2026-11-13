#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; set +a
export PYTHONUTF8=1
if [ "${1:-}" = "stress-eval" ]; then
  shift
  exec uv run python -m audiobook.stress_eval "$@"
fi
uv run python -m audiobook "$@"
