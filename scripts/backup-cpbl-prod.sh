#!/usr/bin/env bash
# 在任何 production migration/upsert 前，備份且驗證 cpbl schema；stdout 只輸出備份路徑。
set -euo pipefail

VPS="${VPS:-root@45.76.100.29}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/personal-website}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/Library/Application Support/cpbl-analytics/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/cpbl-prod-${STAMP}-$$.sql.gz"
PARTIAL_PATH="${BACKUP_PATH}.partial.$$"

if ! [[ "$BACKUP_KEEP" =~ ^[1-9][0-9]*$ ]]; then
  echo "BACKUP_KEEP 必須是正整數" >&2
  exit 64
fi

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

# 檔名時間戳可按字典序排序；只在新備份完整晉升後清除最舊檔案。
ARCHIVES=("$BACKUP_DIR"/cpbl-prod-*.sql.gz)
if [ -e "${ARCHIVES[0]}" ]; then
  REMOVE_COUNT=$((${#ARCHIVES[@]} - BACKUP_KEEP))
  for ((i = 0; i < REMOVE_COUNT; i++)); do
    rm -f "${ARCHIVES[$i]}"
  done
fi
printf '%s\n' "$BACKUP_PATH"
