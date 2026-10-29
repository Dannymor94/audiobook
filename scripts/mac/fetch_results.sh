#!/usr/bin/env bash
# Pull render results from the gamebox to this Mac.
#   scripts/mac/fetch_results.sh [host] [--dry-run]
# host defaults to "gamebox". Copies only mp3/tsv/txt/html/json/log (never wav)
# from ~/audiobook/out/ on the host into ~/Downloads/audiobook/<YYYY-MM-DD>/.
# Read-only on the source: nothing is deleted or moved there.
set -euo pipefail

HOST="gamebox"
DRY=()
for arg in "$@"; do
  case "$arg" in
    -n|--dry-run) DRY=(--dry-run) ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) HOST="$arg" ;;
  esac
done

DEST="${AUDIOBOOK_FETCH_DEST:-$HOME/Downloads/audiobook}/$(date +%F)"
mkdir -p "$DEST"

echo "Забираю ${HOST}:audiobook/out/ -> ${DEST}/"
rsync -av ${DRY[@]+"${DRY[@]}"} --prune-empty-dirs \
  --include='*/' \
  --include='*.mp3' --include='*.tsv' --include='*.txt' \
  --include='*.html' --include='*.json' --include='*.log' \
  --exclude='*' \
  "${HOST}:audiobook/out/" "${DEST}/"
echo "Готово: ${DEST}/"
