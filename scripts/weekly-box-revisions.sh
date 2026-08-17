#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
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
# 產物：logs/weekly-box-revisions-YYYYMMDD-HHMM.log、logs/last-weekly-box-revisions.json、
#       logs/schedule-history/com.cpbl.weekly-box-revisions.jsonl（append-only 歷史）
#
# 用法：scripts/weekly-box-revisions.sh                 # 本季 A+D，近 30 天
#       YEAR=2026 DAYS_BACK=14 scripts/weekly-box-revisions.sh
set -uo pipefail

usage() {
  cat <<'EOU'
scripts/weekly-box-revisions.sh — 每週一次的 box 深度重抓（DATA-BOX-REVISION-SNAPSHOT1 深度層）

在做什麼：把「近 DAYS_BACK 天的已完成場」的 box 重抓一次（kind A 與 D 各一輪），
          讓官方賽後修正收斂進 cpbl.box_pitching_revisions 快照。會對 cpbl.com.tw
          發出真實爬蟲請求（Playwright），並寫入本機資料庫。

會寫什麼：logs/weekly-box-revisions-<TS>.log（完整輸出）
          logs/last-weekly-box-revisions.json（最近一次結果）
          logs/schedule-history/com.cpbl.weekly-box-revisions.jsonl（append-only 歷史）
          cpbl schema 的 box 相關表（經 cpbl-refresh-box-deep）

怎麼呼叫：scripts/weekly-box-revisions.sh                    # 本季 A+D，近 30 天
          YEAR=2026 DAYS_BACK=14 scripts/weekly-box-revisions.sh
          排程由 launchd 觸發（com.cpbl.weekly-box-revisions，週一 14:10）
          環境變數：YEAR／DAYS_BACK／REFRESH_LOCK_DIR

退出碼：0 成功｜75 refresh lock 忙碌而跳過（**不是成功**）｜127 本機 DB 容器未啟動
        ｜64 參數錯誤｜其他 = cpbl-refresh-box-deep 的退出碼
EOU
}

# argv 守衛擺在任何副作用之前：本檔會開真實爬蟲，`--help` 被當成位置參數吞掉就是
# DEV-CLI-HELP-GUARD1 那次事故（查核者想看用法，結果對官網開爬並寫入 DB）。
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  "") ;;
  *) echo "未知參數：$1（本檔不吃位置參數，設定走環境變數；--help 看用法）" >&2; exit 64 ;;
esac

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
YEAR="${YEAR:-$(date +%Y)}"
DAYS_BACK="${DAYS_BACK:-30}"
LOCK_DIR="${REFRESH_LOCK_DIR:-/private/tmp/cpbl-analytics-refresh.lock}"
STARTED_AT="$(date '+%Y-%m-%dT%H:%M:%S%z')"
LABEL="com.cpbl.weekly-box-revisions"
# 本檔的 plist 不設 REFRESH_TRIGGER（且 plist 不在 #132 射程內，一個位元不改），故以
# **父行程**判執行身分。缺席偵測只採計 launchd 觸發的執行——手動補跑不算「排程有跑」，
# 否則手動救火會把壞掉的排程蓋成健康。
#
# 實測（2026-08-15，launchd 三次／互動 shell 兩次，見 #132 交付報告）：
#   launchd 觸發   → PPID=1、父行程 /sbin/launchd
#   互動 shell 觸發 → PPID=登入 shell 的 pid
#
# ⚠️ **不要改用 XPC_SERVICE_NAME**。macOS 只讓 launchd 直接 spawn 的那一個行程看到
# job label，它 fork 出來的子行程一律被重設為字串 "0"（同一次執行裡 bash 讀到
# dev.cpbl132.id2a，而 /usr/bin/env 與 python3 都讀到 "0"）。這個變數在 bash 這一層
# 剛好可用、傳下去就失真，是個會在改版時安靜壞掉的判準。
#
# 判不出來時一律記 manual（fail closed）：誤記成 launchd 會讓手動跑冒充排程跑而靜默，
# 誤記成 manual 只會多報一次缺席——吵，但看得見。
if [ "${PPID:-0}" = "1" ]; then
  TRIGGER="launchd"
else
  TRIGGER="manual"
fi

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
LOG="logs/weekly-box-revisions-${TS}.log"
STATUS="logs/last-weekly-box-revisions.json"

# result（人讀的既有詞彙）→ state（schedule_watch.py 的判定詞彙）。
history_append() {  # $1=state $2=exit_code $3=note
  set -- "$1" "$2" "$3"
  if [ "$1" = "running" ]; then   # running 不帶 finished_at／exit_code，否則語意是假的
    python3 "$REPO_DIR/scripts/refresh_status.py" history-append \
      --history-label "$LABEL" --state running --trigger "$TRIGGER" \
      --started-at "$STARTED_AT" --log "$LOG" --note "$3" || true
  else
    python3 "$REPO_DIR/scripts/refresh_status.py" history-append \
      --history-label "$LABEL" --state "$1" --trigger "$TRIGGER" \
      --started-at "$STARTED_AT" --finished-at "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
      --exit-code "$2" --log "$LOG" --note "$3" || true
  fi
}

write_status() {  # $1=result $2=exit_code $3=note
  cat > "$STATUS" <<EOJ
{"result":"$1","exit_code":$2,"note":"$3","year":$YEAR,"days_back":$DAYS_BACK,
 "started_at":"$STARTED_AT","finished_at":"$(date '+%Y-%m-%dT%H:%M:%S%z')","log":"$LOG"}
EOJ
  case "$1" in
    ok) history_append "succeeded" "$2" "$3" ;;
    skipped) history_append "skipped" "$2" "$3" ;;
    *) history_append "failed" "$2" "$3" ;;
  esac
}

# 忙碌即跳過：每日 refresh／weekly-game-pitches 優先，本檔絕不等待、絕不搶佔既有 lock。
#
# ⚠️ 退出碼是 75 不是 0（OPS-SCHEDULE-FAILURE-BLIND1）。舊版寫 `skipped` 卻 `exit 0`：
# 狀態檔的 result 欄雖可分辨，但 launchd 記到的 LastExitStatus 兩者都是 0，而 launchd
# 正是 2026-08-10 那次失敗唯一被人看到的那個面。「該跑沒跑卻回報成功」比崩潰更難發現。
# 75 沿用 scrape-daily.sh 既有詞彙（EX_TEMPFAIL），語意不變：不等待、不搶佔、直接讓路。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  LOCK_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -z "$LOCK_PID" ]; then
    # 可能是另一個程序剛 mkdir、尚未寫入 pid；不可把它誤判成 stale 後刪除。
    echo "[$(date '+%F %T')] refresh lock 存在但無 pid，保守跳過（下週再收斂）" | tee "$LOG"
    write_status "skipped" 75 "refresh lock busy (no pid)"
    exit 75
  fi
  if kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "[$(date '+%F %T')] 其他 refresh 進行中（pid=${LOCK_PID}），本週深度重抓跳過" | tee "$LOG"
    write_status "skipped" 75 "refresh lock busy"
    exit 75
  fi
  # stale lock 回收：持有者已死。沒有這段，鎖目錄一旦被留下就會永久跳過、永久沒訊號。
  echo "[$(date '+%F %T')] 回收 stale lock（前持有者 pid=${LOCK_PID} 已不存在）" | tee "$LOG"
  rm -f "$LOCK_DIR/pid" 2>/dev/null
  if ! rmdir "$LOCK_DIR" 2>/dev/null || ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date '+%F %T')] stale lock 回收失敗，跳過（下週再收斂）" | tee -a "$LOG"
    write_status "skipped" 75 "stale lock reclaim failed"
    exit 75
  fi
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

# 取得鎖之後立刻留下 running 一列：讓「開跑後死掉」與「從未開跑」在歷史上可分辨。
history_append "running" 0 "acquired refresh lock"

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
