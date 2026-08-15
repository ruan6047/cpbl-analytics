#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
# 每日本機自動爬取（由 launchd 觸發，免手動 CLI）。
#
# 為什麼在本機跑：CPBL 官網（HiNetCDN）封海外 IP，VPS 爬不到，只有台灣 IP（此 Mac）
# 能爬（同 refresh-cpbl-prod.sh 的理由）。本機爬成功後預設呼叫 refresh-cpbl-prod.sh，
# 先備份 production cpbl schema，再做非破壞性 upsert 與 API freshness 驗證。
#
# 產物（供 AI 接手診斷）：
#   logs/refresh-YYYYMMDD-HHMM.log  完整 stdout/stderr
#   logs/last-status.json           最近一次手動或排程結果（含 scrape/sync 分相狀態）
#   logs/last-launchd-status.json   最近一次 launchd 觸發狀態（不被手動 fallback 覆蓋）
# cpbl-refresh-recent 另會在 cpbl.refresh_log 寫一列（ok 布林 + note + detail jsonb），
# 失敗時 ok=false 且非零退出。AI 接手流程：讀 last-status.json → 失敗則 tail log +
# 查 `SELECT * FROM cpbl.refresh_log WHERE ok=false ORDER BY refreshed_at DESC LIMIT 1`。
#
# 用法：scripts/scrape-daily.sh --help   # 只印用法，不碰任何東西
#       scripts/scrape-daily.sh          # 完整增量（games+累計+對戰+分項+逐球…）
#       scripts/scrape-daily.sh fast     # 只更新 games+累計，跳過耗時細項
set -uo pipefail

# ============================================================== argv 守衛
# 這一段必須留在檔案最前面、任何副作用之前——往下移就等於沒有。
#
# 未知參數本檔早已拒絕（下方「參數只接受 fast」，exit 64），缺的是 `--help`：
# 打它只會拿到一句「參數只接受 fast」，那是拒絕不是答案。想知道這支在做什麼的人
# 應該拿到用法並 exit 0。守衛擺在 REFRESH_TRIGGER 檢查之前，`--help` 才不會因為
# 環境變數沒設對而變成另一種拒絕。
usage() {
  cat <<'EOF'
scripts/scrape-daily.sh — 每日本機自動爬取，成功後同步 production（launchd 觸發）

在做什麼
  1. 取 refresh lock（同一把鎖與 weekly-* 排程互斥），確認本機 DB 容器在
  2. 跑 cpbl-refresh-recent 做增量爬取
  3. 爬取成功且 SYNC_PROD≠0 時，以 SKIP_SCRAPE=1 WITH_DETAIL=1 呼叫
     scripts/refresh-cpbl-prod.sh 同步到 production
  4. 把分相結果寫進狀態檔，供 AI／人接手診斷

會寫什麼（⚠️ 高後果，且沒有 dry-run）
  · 本機 PostgreSQL：cpbl-refresh-recent 的增量寫入
  · production PostgreSQL：由步驟 3 的同步鏈寫入（SYNC_PROD=0 可關閉）
  · 本機檔案系統：logs/refresh-YYYYMMDD-HHMMSS.log（只留最近 30 份）、
    logs/last-status.json、logs/last-launchd-status.json

怎麼呼叫
  scripts/scrape-daily.sh          # 完整增量（games+累計+對戰+分項+逐球…）
  scripts/scrape-daily.sh fast     # 只更新 games+累計，跳過耗時細項
  SYNC_PROD=0 scripts/scrape-daily.sh   # 只爬本機，不同步 production
  位置參數只接受 fast；其餘一律 exit 64。launchd 以無參數呼叫。

環境變數
  REFRESH_TRIGGER   manual（預設）或 launchd；其他值一律 exit 64
  SYNC_PROD         0＝爬完不同步 production（預設 1）
  REFRESH_LOCK_DIR  互斥鎖目錄（預設 /private/tmp/cpbl-analytics-refresh.lock）

離開碼
  0 成功 · 64 參數錯 · 70 狀態檔寫入失敗 · 75 鎖被佔用 · 127 本機 DB 容器沒開
  其餘＝爬取或同步階段的原始離開碼

背景：docs/AI_RUNBOOK.md（每日排程與失敗快篩）
EOF
}

if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
  esac
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
ARGS="${1:-}"   # "fast" → 只更新 games+累計
TRIGGER="${REFRESH_TRIGGER:-manual}"
STARTED_AT="$(date '+%Y-%m-%dT%H:%M:%S%z')"
LOCK_DIR="${REFRESH_LOCK_DIR:-/private/tmp/cpbl-analytics-refresh.lock}"
SYNC_ENABLED=1
[ "${SYNC_PROD:-1}" = "0" ] && SYNC_ENABLED=0

if [ "$TRIGGER" != "manual" ] && [ "$TRIGGER" != "launchd" ]; then
  echo "REFRESH_TRIGGER 必須是 manual 或 launchd" >&2
  exit 64
fi
if [ -n "$ARGS" ] && [ "$ARGS" != "fast" ]; then
  printf '未知參數：%s\n' "$ARGS" >&2
  printf '位置參數只接受 fast；用法請打 --help。\n' >&2
  exit 64
fi

release_lock() {
  if [ -f "$LOCK_DIR/pid" ] && [ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" = "$$" ]; then
    rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  LOCK_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -z "$LOCK_PID" ]; then
    # 可能是另一個程序剛 mkdir、尚未寫入 pid；不可把它誤判成 stale 後刪除。
    echo "refresh lock unavailable: ${LOCK_DIR}" >&2
    exit 75
  fi
  if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "refresh already running: pid=${LOCK_PID}" >&2
    exit 75
  fi
  rm -f "$LOCK_DIR/pid" 2>/dev/null
  if ! rmdir "$LOCK_DIR" 2>/dev/null || ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "refresh lock unavailable: ${LOCK_DIR}" >&2
    exit 75
  fi
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
trap release_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
LOG="logs/refresh-${TS}.log"
STATUS="logs/last-status.json"
SCHEDULED_STATUS="logs/last-launchd-status.json"

echo "[$(date '+%F %T')] start: cpbl-refresh-recent ${ARGS}" | tee "$LOG"
if ! python3 "$REPO_DIR/scripts/refresh_status.py" start \
  --status "$STATUS" --scheduled-status "$SCHEDULED_STATUS" \
  --trigger "$TRIGGER" --args "$ARGS" --log "$LOG" \
  --started-at "$STARTED_AT" --sync-enabled "$SYNC_ENABLED"; then
  echo "[$(date '+%F %T')] FATAL: 無法寫入 refresh running 狀態" | tee -a "$LOG"
  exit 70
fi

# 前置檢查：本機 DB（OrbStack/Docker 上的 5433）必須在
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q cpbl-analytics-db; then
  echo "[$(date '+%F %T')] FATAL: 本機 DB 容器未啟動（OrbStack 沒開？）" | tee -a "$LOG"
  CODE=127
else
  # --group scrape：官網爬蟲需 playwright（scrape group）。uv run 為 inexact sync
  # 不會主動剪套件，但顯式帶 group 可防有人跑過 `uv sync`（exact）剪掉後靜默失敗。
  if [ -n "$ARGS" ]; then
    "$UV" run --group scrape cpbl-refresh-recent "$ARGS" >>"$LOG" 2>&1
  else
    "$UV" run --group scrape cpbl-refresh-recent >>"$LOG" 2>&1
  fi
  CODE=$?
fi
echo "[$(date '+%F %T')] scrape exit=${CODE}" | tee -a "$LOG"

# 本機爬成功後自動同步生產（SKIP_SCRAPE：資料已在本機，只 upsert 到 prod + VPS 重建特徵）。
# 關閉：SYNC_PROD=0 scripts/scrape-daily.sh
SYNC_ATTEMPTED=0
SYNC_CODE=0
if [ "$CODE" -eq 0 ] && [ "$SYNC_ENABLED" -eq 1 ]; then
  SYNC_ATTEMPTED=1
  echo "[$(date '+%F %T')] sync prod (SKIP_SCRAPE=1 WITH_DETAIL=1)" | tee -a "$LOG"
  SKIP_SCRAPE=1 WITH_DETAIL=1 bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh" >>"$LOG" 2>&1
  SYNC_CODE=$?
  if [ "$SYNC_CODE" -eq 0 ]; then
    echo "[$(date '+%F %T')] sync prod ok" | tee -a "$LOG"
  else
    echo "[$(date '+%F %T')] sync prod FAILED exit=${SYNC_CODE} (見 log)" | tee -a "$LOG"
  fi
fi

OVERALL_CODE="$CODE"
if [ "$CODE" -eq 0 ] && [ "$SYNC_ATTEMPTED" -eq 1 ] && [ "$SYNC_CODE" -ne 0 ]; then
  OVERALL_CODE="$SYNC_CODE"
fi
echo "[$(date '+%F %T')] overall exit=${OVERALL_CODE}" | tee -a "$LOG"

# 只留最近 30 份逐次 log
ls -1t logs/refresh-*.log 2>/dev/null | tail -n +31 | xargs -I{} rm -f {} 2>/dev/null || true

FINISH_ARGS=(
  finish
  --status "$STATUS" --scheduled-status "$SCHEDULED_STATUS"
  --trigger "$TRIGGER" --args "$ARGS" --log "$LOG"
  --started-at "$STARTED_AT" --finished-at "$(date '+%Y-%m-%dT%H:%M:%S%z')"
  --sync-enabled "$SYNC_ENABLED" --scrape-code "$CODE"
  --sync-attempted "$SYNC_ATTEMPTED"
)
if [ "$SYNC_ATTEMPTED" -eq 1 ]; then
  FINISH_ARGS+=(--sync-code "$SYNC_CODE")
fi
if ! python3 "$REPO_DIR/scripts/refresh_status.py" "${FINISH_ARGS[@]}"; then
  echo "[$(date '+%F %T')] FATAL: 無法寫入 refresh final 狀態" | tee -a "$LOG"
  exit 70
fi

exit "$OVERALL_CODE"
