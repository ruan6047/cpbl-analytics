#!/usr/bin/env bash
# 在任何 production migration/upsert 前，備份且驗證 cpbl schema；stdout 只輸出備份路徑。
set -euo pipefail

VPS="${VPS:-root@45.76.100.29}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/personal-website}"
BACKUP_DIR="${BACKUP_DIR:-/tmp}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/cpbl-prod-${STAMP}.sql.gz"
PARTIAL_PATH="${BACKUP_PATH}.partial.$$"

mkdir -p "$BACKUP_DIR"
trap 'rm -f "$PARTIAL_PATH"' EXIT

ssh -o BatchMode=yes "$VPS" \
  "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec prod_pg pg_dump \
    -U \"\$DB_USER\" -d \"\$DB_NAME\" --schema=cpbl --clean --if-exists --no-owner" \
  | gzip -c > "$PARTIAL_PATH"

test -s "$PARTIAL_PATH"
gzip -t "$PARTIAL_PATH"
mv "$PARTIAL_PATH" "$BACKUP_PATH"
trap - EXIT
printf '%s\n' "$BACKUP_PATH"
