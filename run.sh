#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; set +a
export PYTHONUTF8=1
uv run python -m audiobook "$@"
