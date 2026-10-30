#!/usr/bin/env bash
# Additive backup of render results from the gamebox to this Mac.
#   scripts/mac/backup_gamebox.sh [host] [--dry-run]
# host defaults to "gamebox". Pulls ~/audiobook/out/ on the host into
# ~/AudiobookBackup/out/ (AUDIOBOOK_BACKUP_DIR overrides ~/AudiobookBackup):
# chunk wavs, manifests, takes, redo candidates, queue json/logs, section mp3s.
# Skips *.part / *.tmp, out/export/_old/, out/listen/chunks/, heavy.lock.
# Never deletes: a file removed on the gamebox stays in the backup. Read-only on the host.
set -euo pipefail

HOST="gamebox"
DRY=()
DRYNOTE=""
usage() { sed -n '2,8p' "$0"; }
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run) DRY=(--dry-run); DRYNOTE=" (пробный прогон, ничего не скопировано)" ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "неизвестный ключ: $1" >&2; usage >&2; exit 2 ;;
    *) HOST="$1" ;;
  esac
  shift
done

BASE="${AUDIOBOOK_BACKUP_DIR:-$HOME/AudiobookBackup}"
DEST="${BASE}/out"
LOCK="${BASE}/.backup.lock"      # mkdir is atomic: only one run holds it
PIDFILE="${BASE}/.backup.pid"
stamp() { date '+%F %T'; }
mkdir -p "$DEST"

if ! mkdir "$LOCK" 2>/dev/null; then
  OTHER="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OTHER" ] && kill -0 "$OTHER" 2>/dev/null; then
    echo "$(stamp) бэкап: уже идёт другой запуск (pid $OTHER) — пропускаю"
    exit 0
  fi
  echo "$(stamp) бэкап: замок ${LOCK} остался от прерванного запуска — забираю"
fi
echo "$$" > "$PIDFILE"
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

set +e
OUT="$(rsync -a ${DRY[@]+"${DRY[@]}"} --stats \
  -e 'ssh -o BatchMode=yes -o ConnectTimeout=20' \
  --exclude='*.part' --exclude='*.part.*' --exclude='*.tmp' \
  --exclude='/export/_old/' --exclude='/listen/chunks/' \
  --exclude='/queue/heavy.lock' --exclude='.DS_Store' \
  "${HOST}:audiobook/out/" "${DEST}/" 2>&1)"
RC=$?
set -e

# rsync 3.x says "Number of regular files transferred", 2.6.9/openrsync "Number of files transferred".
FILES="$(printf '%s\n' "$OUT" | sed -n 's/^Number of[a-z ]* files transferred: *\([0-9,.]*\).*/\1/p' | head -n 1)"
BYTES="$(printf '%s\n' "$OUT" | sed -n 's/^Total transferred file size: *\([0-9,.]*\).*/\1/p' | head -n 1)"
SUMMARY="файлов ${FILES:-?}, байт ${BYTES:-?}"

# rsync 24 = some source files vanished mid-transfer (a .part renamed): normal on a live box.
if [ "$RC" -eq 0 ] || [ "$RC" -eq 24 ]; then
  echo "$(stamp) бэкап ${HOST}:audiobook/out/ -> ${DEST}/: ${SUMMARY}${DRYNOTE}"
  exit 0
fi
printf '%s\n' "$OUT" | grep -v -e '^Number of' -e '^Total ' -e '^Literal data' -e '^Matched data' \
  -e '^File list' -e '^sent ' -e '^total size' -e '^$' >&2 || true
echo "$(stamp) бэкап ${HOST}: ОШИБКА rsync (код ${RC}); ${SUMMARY}${DRYNOTE}" >&2
exit "$RC"
