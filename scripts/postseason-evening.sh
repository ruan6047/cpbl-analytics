#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
# 季後期間才安裝的事件觸發晚間鏈（#268 WP3）；製作≠啟用，安裝屬 P1 共享操作。
# 季後晚間事件鏈：只在官方 stats 出現「完賽未入庫／新場次／異動」時才連 www，
# 本機三表或異動訊號表有變化才「獨立備份 → 同步三表＋訊號表 → data-only 對帳」。不訓練、不跑 migration、不寫 prod 標記。
#
# 用法：scripts/postseason-evening.sh --help   # 只印用法，不碰任何東西
#       scripts/postseason-evening.sh          # launchd 每 5 分鐘喚醒一次（REFRESH_TRIGGER=launchd）
set -uo pipefail

# ============================================================== argv 守衛
# 必須留在最前面、任何副作用之前（同 scrape-daily.sh／refresh-cpbl-prod.sh 的理由：探索動作
# 不得造成損害）。本腳本不收任何位置參數。
usage() {
  cat <<'EOF'
scripts/postseason-evening.sh — 季後事件觸發晚間鏈（#268；launchd 每 5 分鐘喚醒）

在做什麼（每次喚醒）
  1. plan：讀狀態檔；到期才以 httpx 唯讀讀官方 stats 賽程 API（不取鎖；本機 DB 只寫異動訊號表），
     與本機 DB 比對出事件。沒有事件 → 直接結束（不連 www）。
  2. 有事件且允許（每事件 ≤3 次、間隔 ≥20 分鐘、挑戰類失敗兩次即停當晚、讓位 10:10）：
     取 refresh lock，跑既有 _postseason_games_step（www getgamedatas，E／C）。
  3. 本機 E／C 有變化（或前次已變化未同步），或只有本機異動訊號表變了（www／同步失敗時亦然）：
     POSTSEASON_RESULTS_ONLY=1 SKIP_SCRAPE=1 scripts/refresh-cpbl-prod.sh
     ＝獨立 BACKUP_DIR 已驗證備份 → 只同步 games／game_schedule_status_revisions／
       game_source_revisions／official_change_signals → /api/info data-only 對帳。
  4. 寫狀態檔與（有嘗試時）本機 refresh_log（scope postseason-evening）。
  沒有鐘點截止：跨過 24:00 照常處理；T1–T3 以實際日期時刻記錄。

會寫什麼（⚠️ 有事件時高後果）
  · 本機 PostgreSQL：scrape_games 的 E／C 寫入；refresh_log 一列；official_change_signals（異動訊號）
  · production PostgreSQL：上述四表非破壞性 upsert（只在本機三表或訊號表有變化時）
  · 本機檔案：POSTSEASON_BACKUP_DIR 下的備份（只留 POSTSEASON_BACKUP_KEEP 份）、
    logs/postseason-evening-state.json、logs/last-postseason-evening.json、logs/postseason-evening-*.log
  不寫：prod refresh 標記、game_features、模型、migration、明細／打席表。

怎麼呼叫（不接受位置參數，設定一律走環境變數）
  launchd：ops/launchd/com.cpbl.postseason-evening.plist（StartInterval 300；安裝屬 P1，需另行核定）
  手動單次：REFRESH_TRIGGER=manual bash scripts/postseason-evening.sh
  查看狀態：cat logs/last-postseason-evening.json

環境變數
  REFRESH_TRIGGER          manual（預設）或 launchd；其他值 exit 64
  REFRESH_LOCK_DIR         與每日／每週排程共用的鎖（預設 /private/tmp/cpbl-analytics-refresh.lock）
  POSTSEASON_BACKUP_DIR    晚間鏈專用備份目錄（預設與 10:10 的目錄不同，不輪替掉那 7 份）
  POSTSEASON_BACKUP_KEEP   晚間鏈備份保留份數（預設 3）
  POSTSEASON_LAUNCHD_LABEL bootout 用的 label（預設 com.cpbl.postseason-evening）

離開碼
  0 正常（含無事件、讓位、冷卻）· 64 參數錯 · 68 對帳不等（停止當晚，隔日 12:00 後再試）
  69 其他同步失敗已 halt（bootout，等人工）
  70 狀態檔寫入失敗 · 75 鎖被佔用（不刪、不搶，等下次喚醒）

停止與回復：docs/AI_RUNBOOK.md〈季後晚間事件鏈〉
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

# 位置參數契約（逐支不同，刻意不與守衛共用）：本腳本一個位置參數都不收。
if [ "$#" -gt 0 ]; then
  printf '未知參數：%s\n' "$1" >&2
  printf '本腳本不接受位置參數，設定一律走環境變數；用法請打 --help。\n' >&2
  exit 64
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
TRIGGER="${REFRESH_TRIGGER:-manual}"
LOCK_DIR="${REFRESH_LOCK_DIR:-/private/tmp/cpbl-analytics-refresh.lock}"
BACKUP_DIR_EVENING="${POSTSEASON_BACKUP_DIR:-$HOME/Library/Application Support/cpbl-analytics/backups-postseason-evening}"
BACKUP_KEEP_EVENING="${POSTSEASON_BACKUP_KEEP:-3}"
LABEL="${POSTSEASON_LAUNCHD_LABEL:-com.cpbl.postseason-evening}"

if [ "$TRIGGER" != "manual" ] && [ "$TRIGGER" != "launchd" ]; then
  echo "REFRESH_TRIGGER 必須是 manual 或 launchd" >&2
  exit 64
fi

mkdir -p logs
LOG="logs/postseason-evening-$(date +%Y%m%d).log"
note() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
py() { "$UV" run python -m cpbl.ingest.postseason_evening "$@" 2>>"$LOG"; }

# 1. plan：不取鎖（讀 stats 與本機 DB；只寫本機異動訊號表，不碰賽程表）。
ACTION="$(py plan)" || { note "FATAL: plan 失敗（狀態檔可能未寫）"; exit 70; }
note "plan → ${ACTION}"
case "$ACTION" in
  idle|halted) exit 0 ;;
  scrape|sync) ;;
  *) note "FATAL: 未知 plan 結果：${ACTION}"; exit 70 ;;
esac

# 2. 取鎖：公告 owner 持有時有界等待（比照 scrape-daily.sh）；其餘一律 exit 75，
#    ⛔ 不刪鎖、不搶鎖——即使 pid 已死，owner 也可能是我們不知道的程序。
release_lock() {
  if [ -f "$LOCK_DIR/pid" ] && [ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" = "$$" ]; then
    rm -f "$LOCK_DIR/pid" "$LOCK_DIR/kind"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
if [ "$(cat "$LOCK_DIR/kind" 2>/dev/null || true)" = "lineup-announcements" ]; then
  waited=0
  while [ -d "$LOCK_DIR" ] && [ "$waited" -lt 240 ]; do
    owner_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    [ -n "$owner_pid" ] && kill -0 "$owner_pid" 2>/dev/null || break
    sleep 1
    waited=$((waited + 1))
  done
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  note "refresh lock busy（owner pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || echo '?')）：不刪不搶，等下次喚醒"
  exit 75
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
printf '%s\n' "postseason-evening" > "$LOCK_DIR/kind"
trap release_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

# 3. www（只在 plan=scrape）。爬蟲需 playwright（--group scrape）。
SYNC_NEEDED=0
if [ "$ACTION" = "scrape" ]; then
  OUTCOME="$("$UV" run --group scrape python -m cpbl.ingest.postseason_evening scrape 2>>"$LOG")" \
    || OUTCOME="failed"
  note "scrape → ${OUTCOME}"
  [ "$OUTCOME" = "changed" ] && SYNC_NEEDED=1
  # B1：三表沒變或 www 失敗，但本機異動訊號表已變 → 仍走一次已驗證備份→同步→對帳（僅訊號變動）。
  if [ "$SYNC_NEEDED" -eq 0 ] && [ "$(py sync-due || echo no)" = "signals" ]; then
    note "sync-due → signals（僅訊號變動）"
    SYNC_NEEDED=1
  fi
else
  SYNC_NEEDED=1   # plan=sync：前次本機已變化但未同步，或僅訊號變動（plan 理由 signals_only）
fi

# 4. 同步（只三表＋異動訊號表；獨立備份目錄；不訓練、不 migration、不寫 prod 標記）。
EXIT_CODE=0
if [ "$SYNC_NEEDED" -eq 1 ]; then
  note "sync → POSTSEASON_RESULTS_ONLY=1 SKIP_SCRAPE=1 BACKUP_DIR=${BACKUP_DIR_EVENING}"
  POSTSEASON_RESULTS_ONLY=1 SKIP_SCRAPE=1 \
    BACKUP_DIR="$BACKUP_DIR_EVENING" BACKUP_KEEP="$BACKUP_KEEP_EVENING" \
    bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh" >>"$LOG" 2>&1
  SYNC_CODE=$?
  note "sync exit=${SYNC_CODE}"
  RECORDED="$(py record-sync --code "$SYNC_CODE")" || RECORDED="halted"
  # 68＝data-only 對帳不等：停止當晚（不 bootout）；其餘非零＝halt（立即停、bootout、交人工）。
  if [ "$RECORDED" = "blocked" ]; then
    EXIT_CODE=68
  elif [ "$SYNC_CODE" -ne 0 ] || [ "$RECORDED" = "halted" ]; then
    EXIT_CODE=69
  fi
fi

py finish >/dev/null || { note "FATAL: finish 狀態寫入失敗"; EXIT_CODE=70; }
release_lock
trap - EXIT

# 錯誤即停：同步失敗後由排程自身 bootout（狀態檔已記 halted，即使 bootout 失敗下次也只會退出）。
if [ "$EXIT_CODE" -eq 69 ] && [ "$TRIGGER" = "launchd" ]; then
  note "halted：launchctl bootout gui/$(id -u)/${LABEL}"
  launchctl bootout "gui/$(id -u)/${LABEL}" >>"$LOG" 2>&1 || note "bootout 失敗（狀態檔 halted 仍會擋下後續喚醒）"
fi
exit "$EXIT_CODE"
