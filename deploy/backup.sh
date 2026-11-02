#!/usr/bin/env bash
# Nightly backup of the database and uploaded files. Run from cron on the app server.
#   BACKUP_DIR=/backups/member-onboarding KEEP_DAYS=30 ./backup.sh
#
# Encryption keys are deliberately not included: store them separately. Restoring
# needs these backups AND the keys, and neither is useful alone.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"
BACKUP_DIR="${BACKUP_DIR:-/backups/member-onboarding}"
MEDIA_PATH="${MEDIA_PATH:-/var/lib/member-onboarding/media}"
KEEP_DAYS="${KEEP_DAYS:-30}"

stamp="$(date +%Y-%m-%d_%H%M)"
target="$BACKUP_DIR/$stamp"
mkdir -p "$target"

pg_dump --format=custom --file="$target/database.dump" "$DATABASE_URL"
tar --create --gzip --file="$target/media.tar.gz" --directory="$MEDIA_PATH" .

# An unreadable backup must fail loudly tonight, not on the day it is needed.
pg_restore --list "$target/database.dump" > /dev/null
tar --list --gzip --file="$target/media.tar.gz" > /dev/null

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +
echo "Backup finished: $target"
