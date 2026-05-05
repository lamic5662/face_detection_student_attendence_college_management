#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/smart_attendance"
SHARED_DIR="$APP_ROOT/shared"
BACKUP_DIR="${BACKUP_DIR:-$SHARED_DIR/backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [[ -z "${DB_NAME:-}" || -z "${DB_USER:-}" || -z "${DB_PASSWORD:-}" ]]; then
  echo "DB_NAME, DB_USER, and DB_PASSWORD must be set in the environment."
  exit 1
fi

mysqldump \
  --single-transaction \
  --quick \
  --host="${DB_HOST:-127.0.0.1}" \
  --port="${DB_PORT:-3306}" \
  --user="$DB_USER" \
  --password="$DB_PASSWORD" \
  "$DB_NAME" | gzip > "$BACKUP_DIR/mysql_${DB_NAME}_${STAMP}.sql.gz"

tar -czf "$BACKUP_DIR/uploads_${STAMP}.tar.gz" \
  -C "$SHARED_DIR" uploads

find "$BACKUP_DIR" -type f -mtime +14 -delete

echo "Backup completed: $BACKUP_DIR"
