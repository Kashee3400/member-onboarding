#!/usr/bin/env bash
# Nightly backup of the uploaded files, and of the database where this server can take
# it. Run from cron on the app server:
#   15 2 * * * BACKUP_DIR=/var/backups/member-onboarding /opt/member-onboarding/app/deploy/backup.sh
#
# The database: every table is row-level secured with FORCE, so a dump as the owner
# returns errors, not data. On our servers the DB server dumps it nightly as postgres
# (erp_master deploy/windows/pg_backup.ps1). Elsewhere set BACKUP_DATABASE_URL to a
# role with BYPASSRLS and read access, and this script dumps it too.
#
# Uploaded documents are sealed with FIELD_ENCRYPTION_KEYS, which are deliberately not
# included: keep them in the password manager. Restoring needs these backups AND the
# keys, and neither is useful alone.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/member-onboarding}"
MEDIA_PATH="${MEDIA_PATH:-/var/lib/member-onboarding/media}"
KEEP_DAYS="${KEEP_DAYS:-14}"
MIN_KEEP="${MIN_KEEP:-3}"
# Optional second copy off this machine, any rsync target such as user@nas:/backups/onboarding.
COPY_TO="${COPY_TO:-}"

stamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
log="$BACKUP_DIR/backup.log"
exec > >(tee -a "$log") 2>&1
echo "== $(date -Is) backup $stamp"

media="$BACKUP_DIR/media_$stamp.tar.gz"
tar --create --gzip --file="$media.part" --directory="$MEDIA_PATH" .
# An unreadable backup must fail loudly tonight, not on the day it is needed.
tar --list --gzip --file="$media.part" > /dev/null
mv "$media.part" "$media"
echo "media: $media ($(du -h "$media" | cut -f1), $(tar --list --gzip --file="$media" | grep -vc '/$') files)"

if [[ -n "${BACKUP_DATABASE_URL:-}" ]]; then
  dump="$BACKUP_DIR/database_$stamp.dump"
  pg_dump --format=custom --file="$dump.part" "$BACKUP_DATABASE_URL"
  pg_restore --list "$dump.part" > /dev/null
  mv "$dump.part" "$dump"
  echo "database: $dump ($(du -h "$dump" | cut -f1))"
fi

# Old backups go, but the newest MIN_KEEP of each kind stay whatever their age.
for kind in media database; do
  { ls -1t "$BACKUP_DIR"/${kind}_*.* 2>/dev/null || true; } | tail -n +"$((MIN_KEEP + 1))" |
    while read -r old; do
      if [[ -n "$(find "$old" -mtime +"$KEEP_DAYS")" ]]; then rm -f -- "$old"; echo "pruned $old"; fi
    done
done

if [[ -n "$COPY_TO" ]]; then
  rsync --archive --include='media_*' --include='database_*' --exclude='*' "$BACKUP_DIR/" "$COPY_TO/"
  echo "copied to $COPY_TO"
fi
echo "== done"
