#!/usr/bin/env bash
#
# backup_members.sh — nightly hot backup of data/members.db
#
# members.db is the ONLY irreplaceable site-owned data (members / wishlist /
# 到貨通知 / 收件資料). Everything else is re-derivable from the POS. This DB
# lives ONLY on the VM (deploy.sh never ships or overwrites data/), so this
# script must be installed and cron'd ON THE VM — not from a deploy.
#
# Install on the VM (as user warpmonger):
#   crontab -e
#   # Backup members.db nightly at 03:00 (server local time)
#   0 3 * * * /home/warpmonger/abbeystoys/scripts/backup_members.sh >> /home/warpmonger/abbeystoys/backups/backup.log 2>&1
#
# Optional off-VM copy: export BACKUP_GCS_BUCKET=gs://your-bucket/members-backups
# (in the crontab line or a wrapper) and each backup is also uploaded via gsutil.
#
# Uses the sqlite3 online-backup API (a consistent snapshot that respects WAL)
# rather than cp, which can capture a torn database when writes are in flight.
# Implemented via python3's stdlib sqlite3 module so it needs no sqlite3 CLI
# (the VM does not have one). PYTHON_BIN can override the interpreter.

set -euo pipefail

# Resolve paths relative to this script so it works from any cwd / cron.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DB_PATH="${MEMBERS_DB:-${APP_DIR}/data/members.db}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
KEEP="${BACKUP_KEEP:-14}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "ERROR: members DB not found at ${DB_PATH}" >&2
  exit 1
fi

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || { echo "ERROR: ${PYTHON_BIN} not found" >&2; exit 1; }

mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/members-${TIMESTAMP}.db"

# Safe hot copy (handles WAL) via the sqlite3 online-backup API. Write to a tmp
# file first, then atomically rename so a crash never leaves a partial .db.
TMP="${OUT}.part"
"${PYTHON_BIN}" - "${DB_PATH}" "${TMP}" <<'PY'
import sqlite3, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
mv "${TMP}" "${OUT}"
echo "$(date '+%Y-%m-%d %H:%M:%S') backed up ${DB_PATH} -> ${OUT}"

# Optional off-VM upload to GCS.
if [[ -n "${BACKUP_GCS_BUCKET:-}" ]]; then
  if command -v gsutil >/dev/null 2>&1; then
    gsutil cp "${OUT}" "${BACKUP_GCS_BUCKET%/}/members-${TIMESTAMP}.db"
    echo "$(date '+%Y-%m-%d %H:%M:%S') uploaded to ${BACKUP_GCS_BUCKET%/}/members-${TIMESTAMP}.db"
  else
    echo "WARN: BACKUP_GCS_BUCKET set but gsutil not found; skipping upload" >&2
  fi
fi

# Rotate: keep the most recent ${KEEP} local backups. Portable (no mapfile).
PRUNED=0
while IFS= read -r old; do
  [[ -n "${old}" ]] || continue
  rm -f "${old}"
  PRUNED=$((PRUNED + 1))
done < <(ls -1t "${BACKUP_DIR}"/members-*.db 2>/dev/null | tail -n +"$((KEEP + 1))")
if (( PRUNED > 0 )); then
  echo "$(date '+%Y-%m-%d %H:%M:%S') pruned ${PRUNED} old backup(s), keeping ${KEEP}"
fi
