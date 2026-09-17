#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
BUCKET_URI="s3://devon-chonnam-3-db-backup-263051787000-ap-northeast-2-an/postgres"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/devon_${TIMESTAMP}.dump"
PARTIAL_FILE="${BACKUP_FILE}.partial"

mkdir -p "$BACKUP_DIR"
trap 'rm -f "$PARTIAL_FILE"' EXIT

cd "$PROJECT_DIR"

docker compose -f compose.deploy.yaml exec -T db \
  pg_dump -U devon -d devon -Fc > "$PARTIAL_FILE"

test -s "$PARTIAL_FILE"
mv "$PARTIAL_FILE" "$BACKUP_FILE"

aws s3 cp "$BACKUP_FILE" "$BUCKET_URI/$(basename "$BACKUP_FILE")"

find "$BACKUP_DIR" -type f -name 'devon_*.dump' -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
