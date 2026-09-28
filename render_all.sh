#!/usr/bin/env bash
# Full-book render with optional shutdown on clean completion.
#
# Usage:
#   ./render_all.sh [--shutdown]
#
# --shutdown: schedule `sudo shutdown -h +10` after clean render.
#   A "clean render" means zero timeout/pending chunks across all sections.
#   Any timeout leaves the machine up for inspection.
#
# Always run in tmux: the render takes ~8 hours on Ryzen 7 with 4 workers.
# To cancel shutdown: sudo shutdown -c

set -uo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; set +a
export PYTHONUTF8=1

WORKERS=4
SHUTDOWN=0
for arg in "$@"; do
  [ "$arg" = "--shutdown" ] && SHUTDOWN=1
done

UV=/home/danavrata/.local/bin/uv

# ── 1. rechunk (picks up pronounce.yaml + any config changes) ─────────────────
echo ""
echo "=== CHUNK ==="
$UV run python -m audiobook chunk
echo "chunk done: $(date)"

# ── 2. collect sections with pending chunks ────────────────────────────────────
PENDING_SECTIONS=()
for mf in out/sections/*/manifest.jsonl; do
  sec=$(basename "$(dirname "$mf")")
  n=$(python3 -c "
import json
rows=[json.loads(l) for l in open('$mf',encoding='utf-8') if l.strip()]
print(sum(1 for r in rows if r.get('status')!='done'))
")
  if [ "$n" -gt 0 ]; then
    PENDING_SECTIONS+=("$sec")
  fi
done
echo ""
echo "=== SYNTH: ${#PENDING_SECTIONS[@]} sections with pending chunks ==="

# ── 3. synth each pending section ─────────────────────────────────────────────
TOTAL_TIMEOUT=0
FAILED_SECTIONS=()
for sec in "${PENDING_SECTIONS[@]}"; do
  echo ""
  echo "--- $sec ---"
  if $UV run python -m audiobook synth --section "$sec" --workers $WORKERS; then
    # count timeouts in this section after render
    mf="out/sections/$sec/manifest.jsonl"
    n_to=$(python3 -c "
import json
rows=[json.loads(l) for l in open('$mf',encoding='utf-8') if l.strip()]
print(sum(1 for r in rows if r.get('status')=='timeout'))
")
    if [ "$n_to" -gt 0 ]; then
      echo "  TIMEOUT: $n_to chunks in $sec"
      TOTAL_TIMEOUT=$((TOTAL_TIMEOUT + n_to))
    fi
  else
    echo "  FAILED: $sec (non-zero exit)"
    FAILED_SECTIONS+=("$sec")
  fi
done

# ── 4. summary ─────────────────────────────────────────────────────────────────
echo ""
echo "=== RENDER COMPLETE ==="
echo "  total timeouts: $TOTAL_TIMEOUT"
echo "  failed sections: ${#FAILED_SECTIONS[@]}"
for s in "${FAILED_SECTIONS[@]}"; do echo "    $s"; done
echo "  $(date)"

# ── 5. shutdown gating ─────────────────────────────────────────────────────────
if [ $SHUTDOWN -eq 1 ]; then
  if [ $TOTAL_TIMEOUT -eq 0 ] && [ ${#FAILED_SECTIONS[@]} -eq 0 ]; then
    echo ""
    echo "=== CLEAN RENDER — scheduling shutdown in 10 minutes ==="
    echo "  cancel with: sudo shutdown -c"
    sudo shutdown -h +10
  else
    echo ""
    echo "=== SHUTDOWN CANCELLED — non-zero timeouts or failures; inspect and re-run ==="
  fi
fi
