#!/usr/bin/env bash
# Pull render results from the gamebox to this Mac.
#   scripts/mac/fetch_results.sh [host] [--dry-run] [--with-wav <dir under out/>]
# host defaults to "gamebox". Copies only mp3/tsv/txt/md/html/json/log from
# ~/audiobook/out/ on the host into ~/Downloads/audiobook/<YYYY-MM-DD>/.
# --with-wav golden/compare_a_b also copies the wav files under out/<dir>/ (subfolders
# included), so a review.html there plays on the Mac. Without it no wav is copied.
# Read-only on the source and additive on the Mac: nothing is deleted or moved on either side.
set -euo pipefail

HOST="gamebox"
DRY=()
WAVDIR=""
usage() { sed -n '2,9p' "$0"; }
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run) DRY=(--dry-run) ;;
    -h|--help) usage; exit 0 ;;
    --with-wav)
      [ $# -ge 2 ] || { echo "--with-wav: нужна папка относительно out/" >&2; exit 2; }
      WAVDIR="$2"; shift ;;
    --with-wav=*) WAVDIR="${1#--with-wav=}" ;;
    -*) echo "неизвестный ключ: $1" >&2; usage >&2; exit 2 ;;
    *) HOST="$1" ;;
  esac
  shift
done

WAV_RULES=()
if [ -n "$WAVDIR" ]; then
  WAVDIR="${WAVDIR#./}"
  WAVDIR="${WAVDIR#out/}"
  WAVDIR="${WAVDIR%/}"
  case "/$WAVDIR/" in
    //|*/../*|*/./*) echo "--with-wav: нужна папка внутри out/, без .. : '$WAVDIR'" >&2; exit 2 ;;
  esac
  case "$WAVDIR" in
    /*|*[\*\?\[]*) echo "--with-wav: относительный путь без шаблонов: '$WAVDIR'" >&2; exit 2 ;;
  esac
  WAV_RULES=(--include="/${WAVDIR}/**.wav")
fi

DEST="${AUDIOBOOK_FETCH_DEST:-$HOME/Downloads/audiobook}/$(date +%F)"
mkdir -p "$DEST"

echo "Забираю ${HOST}:audiobook/out/ -> ${DEST}/${WAVDIR:+  (+ wav из out/${WAVDIR}/)}"
rsync -av ${DRY[@]+"${DRY[@]}"} --prune-empty-dirs \
  --include='*/' \
  --include='*.mp3' --include='*.tsv' --include='*.txt' --include='*.md' \
  --include='*.html' --include='*.json' --include='*.log' \
  ${WAV_RULES[@]+"${WAV_RULES[@]}"} \
  --exclude='*' \
  "${HOST}:audiobook/out/" "${DEST}/"
echo "Готово: ${DEST}/"
