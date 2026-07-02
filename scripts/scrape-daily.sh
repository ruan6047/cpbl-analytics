#!/usr/bin/env bash
# 每日本機自動爬取（由 launchd 觸發，免手動 CLI）。
#
# 為什麼在本機跑：CPBL 官網（HiNetCDN）封海外 IP，VPS 爬不到，只有台灣 IP（此 Mac）
# 能爬（同 refresh-cpbl-prod.sh 的理由）。此腳本只更新「本機」DB；要同步上線另跑
# refresh-cpbl-prod.sh（含 SSH + prod upsert）。
#
# 產物（供 AI 接手診斷）：
#   logs/refresh-YYYYMMDD-HHMM.log  完整 stdout/stderr
#   logs/last-status.json           最近一次結果：ok / exit_code / log 路徑 / 末 20 行
# cpbl-refresh-recent 另會在 cpbl.refresh_log 寫一列（ok 布林 + note + detail jsonb），
# 失敗時 ok=false 且非零退出。AI 接手流程：讀 last-status.json → 失敗則 tail log +
# 查 `SELECT * FROM cpbl.refresh_log WHERE ok=false ORDER BY refreshed_at DESC LIMIT 1`。
#
# 用法：scripts/scrape-daily.sh          # 完整增量（games+累計+對戰+分項+逐球…）
#       scripts/scrape-daily.sh fast     # 只更新 games+累計，跳過耗時細項
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
mkdir -p logs

TS="$(date +%Y%m%d-%H%M)"
LOG="logs/refresh-${TS}.log"
STATUS="logs/last-status.json"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
ARGS="${1:-}"   # "fast" → 只更新 games+累計

echo "[$(date '+%F %T')] start: cpbl-refresh-recent ${ARGS}" | tee "$LOG"

# 前置檢查：本機 DB（OrbStack/Docker 上的 5433）必須在
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q cpbl-analytics-db; then
  echo "[$(date '+%F %T')] FATAL: 本機 DB 容器未啟動（OrbStack 沒開？）" | tee -a "$LOG"
  CODE=127
else
  # --group scrape：官網爬蟲需 playwright（scrape group）。uv run 為 inexact sync
  # 不會主動剪套件，但顯式帶 group 可防有人跑過 `uv sync`（exact）剪掉後靜默失敗。
  "$UV" run --group scrape cpbl-refresh-recent ${ARGS} >>"$LOG" 2>&1
  CODE=$?
fi
echo "[$(date '+%F %T')] exit=${CODE}" | tee -a "$LOG"

# 本機爬成功後自動同步生產（SKIP_SCRAPE：資料已在本機，只 upsert 到 prod + VPS 重建特徵）。
# 關閉：SYNC_PROD=0 scripts/scrape-daily.sh
if [ "$CODE" -eq 0 ] && [ "${SYNC_PROD:-1}" != "0" ]; then
  echo "[$(date '+%F %T')] sync prod (SKIP_SCRAPE=1 WITH_DETAIL=1)" | tee -a "$LOG"
  SKIP_SCRAPE=1 WITH_DETAIL=1 bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh" >>"$LOG" 2>&1 \
    && echo "[$(date '+%F %T')] sync prod ok" | tee -a "$LOG" \
    || echo "[$(date '+%F %T')] sync prod FAILED (見 log)" | tee -a "$LOG"
fi

# 只留最近 30 份逐次 log
ls -1t logs/refresh-*.log 2>/dev/null | tail -n +31 | xargs -I{} rm -f {} 2>/dev/null || true

# AI 友善狀態檔（末 20 行用 python 安全轉成 JSON 字串）
TAIL_JSON="$(tail -n 20 "$LOG" | python3 -c 'import sys,json;print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')"
OK_BOOL=$( [ "$CODE" -eq 0 ] && echo true || echo false )
cat > "$STATUS" <<JSON
{
  "ts": "$(date '+%F %T %z')",
  "ok": ${OK_BOOL},
  "exit_code": ${CODE},
  "args": "${ARGS}",
  "log": "${LOG}",
  "tail": ${TAIL_JSON}
}
JSON

exit "$CODE"
