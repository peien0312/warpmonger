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
# Uses sqlite3 ".backup" (a consistent snapshot that respects WAL) rather than
# cp, which can capture a torn database when writes are in flight.

set -euo pipefail

# Resolve paths relative to this script so it works from any cwd / cron.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DB_PATH="${MEMBERS_DB:-${APP_DIR}/data/members.db}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
KEEP="${BACKUP_KEEP:-14}"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "ERROR: members DB not found at ${DB_PATH}" >&2
  exit 1
fi

command -v sqlite3 >/dev/null 2>&1 || { echo "ERROR: sqlite3 not installed" >&2; exit 1; }

mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/members-${TIMESTAMP}.db"

# Safe hot copy (handles WAL). Write to a tmp file first, then atomically rename.
TMP="${OUT}.part"
sqlite3 "${DB_PATH}" ".backup '${TMP}'"
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

# Rotate: keep the most recent ${KEEP} local backups.
mapfile -t OLD < <(ls -1t "${BACKUP_DIR}"/members-*.db 2>/dev/null | tail -n +"$((KEEP + 1))")
if (( ${#OLD[@]} > 0 )); then
  rm -f "${OLD[@]}"
  echo "$(date '+%Y-%m-%d %H:%M:%S') pruned ${#OLD[@]} old backup(s), keeping ${KEEP}"
fi
