#!/usr/bin/env bash
# 每週一次的 box 深度重抓（DATA-BOX-REVISION-SNAPSHOT1 深度層）。
#
# 為什麼要這一支：每日 refresh（scrape-daily.sh → cpbl-refresh-recent）只重抓
# [昨天,今天] 2 天窗——一場比賽的 box 一旦被成功抓過一次，自動排程不會再回頭碰它。
# 若官方在賽後 2 天以後才修正 ER（規則 9.01(b)(1)），現行架構下永遠不會被
# cpbl.box_pitching_revisions 觀測到。本檔每週把「近 30 天已完成場」的 box 重抓
# 一次，讓 30 天內的修正收斂進快照。30 天是保守選擇不是量測結果——見
# cpbl.ingest.run_refresh_box_deep 模組 docstring 的完整推理；累積出第一批
# days_since_game 分布後應回頭檢視這個窗要不要調整。
#
# 與每日窗完全分開：不改 run_refresh_recent.py 的 2 天窗邏輯，本檔呼叫獨立 CLI
# （cpbl-refresh-box-deep），兩者共用同一份 scrape_gamelogs() 但入口、排程、
# 失敗行為互不影響——每日窗的 SLA 不會被這裡的請求量拖慢。
#
# 紅線：**排程失敗不得中斷既有每日 refresh**，且**失敗不得自動重試**（HiNet 挑戰
# 對連續冷啟動會升級節流）。落地方式比照 weekly-game-pitches.sh 三層：
#   1. 獨立 launchd job、獨立 log 與狀態檔——每日鏈完全不讀本檔任何產物。
#   2. 共用同一把 refresh lock，且**忙碌即跳過**（不等待、不搶佔）：與每日鏈及
#      weekly-game-pitches.sh 三者互斥，但本檔絕不因為想跑而卡住其他排程。
#   3. 單一 kind 失敗不重試、不中止另一 kind；整體失敗直接以非零碼結束，
#      **不在本檔內重試**——下週排程會用同一個「近 30 天」窗從頭跑一次，這週
#      沒抓到的場次下週自然涵蓋（窗是相對「今天」算的，不是斷點續傳）。
#
# 時段選擇：**週一 14:10**（中職固定休兵日，無新完成場）。
#   · 距 weekly-game-pitches.sh（週一 13:10）1 小時緩衝——兩者都走同一把 refresh
#     lock、忙碌即跳過，撞期也不會卡住彼此，但留緩衝可降低「其中一個因撞期而
#     整週跳過」的機率（weekly-game-pitches.sh 抓 stats.cpbl 無反爬，本檔抓
#     cpbl.com.tw 走 Playwright，兩者耗時特性不同，值得分開時段觀察各自耗時）。
#   · 距每日 10:10 觸發點更遠，時間上不重疊。
#
# 產物：logs/weekly-box-revisions-YYYYMMDD-HHMM.log、logs/last-weekly-box-revisions.json
#
# 用法：scripts/weekly-box-revisions.sh                 # 本季 A+D，近 30 天
#       YEAR=2026 DAYS_BACK=14 scripts/weekly-box-revisions.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
YEAR="${YEAR:-$(date +%Y)}"
DAYS_BACK="${DAYS_BACK:-30}"
LOCK_DIR="${REFRESH_LOCK_DIR:-/private/tmp/cpbl-analytics-refresh.lock}"
STARTED_AT="$(date '+%Y-%m-%dT%H:%M:%S%z')"

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
LOG="logs/weekly-box-revisions-${TS}.log"
STATUS="logs/last-weekly-box-revisions.json"

write_status() {  # $1=result $2=exit_code $3=note
  cat > "$STATUS" <<EOJ
{"result":"$1","exit_code":$2,"note":"$3","year":$YEAR,"days_back":$DAYS_BACK,
 "started_at":"$STARTED_AT","finished_at":"$(date '+%Y-%m-%dT%H:%M:%S%z')","log":"$LOG"}
EOJ
}

# 忙碌即跳過：每日 refresh／weekly-game-pitches 優先，本檔絕不等待、絕不搶佔既有 lock。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$(date '+%F %T')] 其他 refresh 進行中，本週深度重抓跳過（下週再收斂）" | tee "$LOG"
  write_status "skipped" 0 "refresh lock busy"
  exit 0
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
release_lock() {
  if [ -f "$LOCK_DIR/pid" ] && [ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" = "$$" ]; then
    rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
trap release_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

echo "[$(date '+%F %T')] start: box 深度重抓 year=${YEAR} days_back=${DAYS_BACK} kinds=A,D" | tee "$LOG"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q cpbl-analytics-db; then
  echo "[$(date '+%F %T')] FATAL: 本機 DB 容器未啟動（OrbStack 沒開？）" | tee -a "$LOG"
  write_status "failed" 127 "local DB container not running"
  exit 127
fi

CODE=0
for KIND in A D; do
  echo "[$(date '+%F %T')] kind=${KIND}" | tee -a "$LOG"
  # cpbl.com.tw 走 Playwright（scrape group）；不得自動重試——單一 kind 失敗
  # 記錄後直接進下一個 kind，整體結果仍記為失敗，交由下週排程從頭跑。
  "$UV" run --group scrape cpbl-refresh-box-deep "$YEAR" "$KIND" "$DAYS_BACK" >>"$LOG" 2>&1
  RC=$?
  echo "[$(date '+%F %T')] kind=${KIND} exit=${RC}" | tee -a "$LOG"
  [ "$RC" -ne 0 ] && CODE="$RC"
done

echo "[$(date '+%F %T')] overall exit=${CODE}" | tee -a "$LOG"
ls -1t logs/weekly-box-revisions-*.log 2>/dev/null | tail -n +13 | xargs -I{} rm -f {} 2>/dev/null || true
[ "$CODE" -eq 0 ] && write_status "ok" 0 "" || write_status "failed" "$CODE" "see log"
exit "$CODE"
