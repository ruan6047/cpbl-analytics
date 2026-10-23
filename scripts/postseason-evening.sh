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
     #292 先發查核時點（旗標檔存在才開）：開賽前 1h／0.5h、終場後 1h 到點也走第 2 步（同一組閘門）。
  2. 有事件且允許（每事件 ≤3 次、間隔 ≥20 分鐘、挑戰類失敗兩次即停當晚、讓位 10:10）：
     取 refresh lock，跑既有 _postseason_games_step（www getgamedatas，E／C）。
  3. 本機 E／C 有變化（或前次已變化未同步），或只有本機異動訊號表變了（www／同步失敗時亦然）：
     POSTSEASON_RESULTS_ONLY=1 SKIP_SCRAPE=1 scripts/refresh-cpbl-prod.sh
     ＝獨立 BACKUP_DIR 已驗證備份 → 只同步 games／game_schedule_status_revisions／
       game_source_revisions／official_change_signals → /api/info data-only 對帳。
  4. #293 目標場 box／PA 階段（結果同步之後；沒有結果事件時也會看）：
     本機已完賽、box 或 PA 尚未送達 production 的今晚目標場 →
     a. 本機 box 核心表仍缺：既有 _postseason_detail_step（www；每場每晚 ≤3 次、間隔 ≥20 分鐘、
        挑戰類失敗與結果鏈共用「當晚兩次即停」、讓位 10:10）；
     b. 本機到齊：既有 PA build → POSTSEASON_BOXPA_ONLY=1 SKIP_SCRAPE=1 scripts/refresh-cpbl-prod.sh
        ＝已驗證備份 → box 七表目標鍵 upsert → PA 五表目標鍵單交易替換 → 逐表逐場對帳
        （同來源 1 次＋1 次重送；不 TRUNCATE、不 CASCADE、不 migrate、不呼叫 prod_cpbl_api）。
     c. box 已送達但逐球晚到（既有逐球覆蓋判準：設備球場、覆蓋 < 85%）：狀態記待更新、不判送達；
        每 20 分鐘只向 stats 重抓逐球（不連 www）→ PA build → 同一次送 box＋PA（仍以場計 ≤2 次）。
  5. 寫狀態檔與（有嘗試時）本機 refresh_log（scope postseason-evening）。
  #293 r3：本鏈每次官網 www 導頁在 log 留一行 `WWW_REQ card=293 kind=… src=<292|293> at=… game=… status=…`
  （同頁 POST 不記＝導頁次數下限），另以 Playwright 導頁事件寫 `WWW_NAV card=293 …` 供獨立對帳；
  每日鏈不寫。計數：grep -h 'WWW_REQ card=293' logs/postseason-evening-*.log
  沒有鐘點截止：跨過 24:00 照常處理；T1–T3 以實際日期時刻記錄。

會寫什麼（⚠️ 有事件時高後果）
  · 本機 PostgreSQL：scrape_games 的 E／C 寫入；refresh_log 一列；official_change_signals（異動訊號）
  · production PostgreSQL：上述四表非破壞性 upsert（只在本機三表或訊號表有變化時）；
    #293：今晚目標場的 box 七表 upsert、PA 五表目標鍵替換（只動目標場鍵）
  · 本機 PostgreSQL（#293）：目標場明細（gamelog 四類、game_detail、pitching_game_flags、pitch_tracking、
    game_source_revisions）與 PA 五表（既有 builder）
  · 本機檔案：POSTSEASON_BACKUP_DIR 下的備份（只留 POSTSEASON_BACKUP_KEEP 份）、
    logs/postseason-evening-state.json、logs/last-postseason-evening.json、logs/postseason-evening-*.log
  不寫：prod refresh 標記、game_features、模型、migration；非目標場的明細／打席列。

怎麼呼叫（不接受位置參數，設定一律走環境變數）
  launchd：ops/launchd/com.cpbl.postseason-evening.plist（StartInterval 300；安裝屬 P1，需另行核定）
  手動單次：REFRESH_TRIGGER=manual bash scripts/postseason-evening.sh
  只跑 box／PA 階段（手動單次）：POSTSEASON_EVENING_STAGE=boxpa REFRESH_TRIGGER=manual bash scripts/postseason-evening.sh
  查看狀態：cat logs/last-postseason-evening.json
  （POSTSEASON_EVENING_STAGE=boxpa 時 log 另寫 logs/postseason-evening-boxpa-manual-YYYYMMDD.log）

環境變數
  REFRESH_TRIGGER          manual（預設）或 launchd；其他值 exit 64
  REFRESH_LOCK_DIR         與每日／每週排程共用的鎖（預設 /private/tmp/cpbl-analytics-refresh.lock）
  POSTSEASON_BACKUP_DIR    晚間鏈專用備份目錄（預設與 10:10 的目錄不同，不輪替掉那 7 份）
  POSTSEASON_BACKUP_KEEP   晚間鏈備份保留份數（預設 3）
  POSTSEASON_LAUNCHD_LABEL bootout 用的 label（預設 com.cpbl.postseason-evening）
  POSTSEASON_STARTER_FLAG  #292 先發查核時點旗標檔（預設 logs/postseason-starter-checkpoints.enabled；
                           存在＝開，touch／rm 下次喚醒生效；預覽：uv run python -m cpbl.ingest.postseason_evening plan --dry）
  POSTSEASON_EVENING_STAGE all（預設：結果鏈＋box／PA 階段）或 boxpa（只跑 box／PA 階段）；其他值 exit 64

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

STAGE="${POSTSEASON_EVENING_STAGE:-all}"

if [ "$TRIGGER" != "manual" ] && [ "$TRIGGER" != "launchd" ]; then
  echo "REFRESH_TRIGGER 必須是 manual 或 launchd" >&2
  exit 64
fi
if [ "$STAGE" != "all" ] && [ "$STAGE" != "boxpa" ]; then
  echo "POSTSEASON_EVENING_STAGE 必須是 all 或 boxpa" >&2
  exit 64
fi

mkdir -p logs
LOG="logs/postseason-evening-$(date +%Y%m%d).log"
# #293 r3：手動只跑 box／PA 階段（WP5）時另寫一檔，標記與 launchd 的晚間 log 分開計數。
[ "$STAGE" = "boxpa" ] && LOG="logs/postseason-evening-boxpa-manual-$(date +%Y%m%d).log"
note() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
py() { "$UV" run python -m cpbl.ingest.postseason_evening "$@" 2>>"$LOG"; }

# 1. plan：不取鎖（讀 stats 與本機 DB；只寫本機異動訊號表，不碰賽程表）。STAGE=boxpa 時不跑結果鏈。
ACTION="idle"
if [ "$STAGE" = "all" ]; then
  ACTION="$(py plan)" || { note "FATAL: plan 失敗（狀態檔可能未寫）"; exit 70; }
  note "plan → ${ACTION}"
  case "$ACTION" in
    quiet|idle|halted|scrape|sync) ;;
    *) note "FATAL: 未知 plan 結果：${ACTION}"; exit 70 ;;
  esac
  # #365 動作條件：今晚沒有排定的晚間賽別、也沒有待辦 → plan 未寫狀態檔、未連 DB／stats；
  # 這裡連 boxpa-plan --dry（會連 DB）都不跑、不取鎖，直接結束。休賽季每次喚醒只留這一行 log。
  [ "$ACTION" = "quiet" ] && exit 0
fi
# 1b. #293 box／PA 預檢：不取鎖、不寫狀態檔、不連 www（只讀本機 DB 與狀態檔）。
#     結果鏈沒事、box／PA 也沒事 → 直接結束（與原本「無事件不取鎖」相同）。
BOXPA_PRE="$(py boxpa-plan --dry)" || BOXPA_PRE="error"
note "boxpa-plan --dry → ${BOXPA_PRE}"
if [ "$ACTION" = "idle" ] || [ "$ACTION" = "halted" ]; then
  # build 也要進來（#293 fix-4 B1）：已送達或額度用完後來源才更新時，只跑本機 PA builder、不同步。
  # tracking 也要進來（#293 fix-5）：box 已送達但逐球晚到，只向 stats 重抓逐球（不連 www）。
  case "$BOXPA_PRE" in
    detail*|sync*|tracking*|build*) ;;
    *) exit 0 ;;
  esac
fi

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
elif [ "$ACTION" = "sync" ]; then
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

# 5. #293 目標場 box／PA 階段（結果鏈已 halt 時不做；boxpa-plan 也會因 halted 回 idle）。
#    每次喚醒最多一次明細 www＋一次 PA build＋一次 scoped 同步；失敗語意見 postseason_evening.boxpa_record_sync。
boxpa_split() {  # "$1"＝boxpa-plan 輸出（"sync 2026-C-2 box,pa"）→ BOXPA_ACT／BOXPA_GAMES／BOXPA_PARTS
  BOXPA_ACT="" BOXPA_GAMES="" BOXPA_PARTS=""
  read -r BOXPA_ACT BOXPA_GAMES BOXPA_PARTS <<< "$1"
  return 0
}
if [ "$EXIT_CODE" -ne 69 ]; then
  BOXPA_PLAN="$(py boxpa-plan)" || BOXPA_PLAN="error"
  note "boxpa-plan → ${BOXPA_PLAN}"
  boxpa_split "$BOXPA_PLAN"
  if [ "$BOXPA_ACT" = "detail" ]; then
    BOXPA_OUT="$("$UV" run --group scrape python -m cpbl.ingest.postseason_evening boxpa-detail \
      --games "$BOXPA_GAMES" 2>>"$LOG")" || BOXPA_OUT="failed"
    note "boxpa-detail ${BOXPA_GAMES} → ${BOXPA_OUT}"
  fi
  # #293 fix-5：逐球晚到 → 只打 stats（httpx，不需 --group scrape、不連 www）；之後照常 PA build → plan → sync。
  if [ "$BOXPA_ACT" = "tracking" ]; then
    BOXPA_OUT="$(py boxpa-tracking --games "$BOXPA_GAMES")" || BOXPA_OUT="failed"
    note "boxpa-tracking ${BOXPA_GAMES} → ${BOXPA_OUT}"
  fi
  # #293 再審 R1：先 PA build，再決定這次送哪些來源——剛 build 出的 PA 與 box 在同一次同步送出。
  if [ "$BOXPA_ACT" = "detail" ] || [ "$BOXPA_ACT" = "tracking" ] || [ "$BOXPA_ACT" = "build" ] \
     || [ "$BOXPA_ACT" = "sync" ]; then
    BOXPA_OUT="$(py boxpa-prepare)" || BOXPA_OUT="prepare_failed"
    note "boxpa-prepare → ${BOXPA_OUT}"
    BOXPA_PLAN="$(py boxpa-plan)" || BOXPA_PLAN="error"
    note "boxpa-plan → ${BOXPA_PLAN}"
    boxpa_split "$BOXPA_PLAN"
  fi
  # BOXPA_PARTS＝這次真的要送的來源（審核席 1 F3：已送達的來源不隨整組同步再送；額度以場計）。
  if [ "$BOXPA_ACT" = "sync" ] && [ -n "$BOXPA_GAMES" ] && [ -n "$BOXPA_PARTS" ]; then
    BOXPA_MANIFEST_PATH="$REPO_DIR/logs/postseason-boxpa-manifest-$(date +%Y%m%d-%H%M%S).json"
    note "boxpa sync → POSTSEASON_BOXPA_ONLY=1 SKIP_SCRAPE=1 POSTSEASON_BOXPA_GAMES=${BOXPA_GAMES} POSTSEASON_BOXPA_PARTS=${BOXPA_PARTS} BACKUP_DIR=${BACKUP_DIR_EVENING}"
    BOXPA_STARTED="$(date +%s)"
    POSTSEASON_BOXPA_ONLY=1 SKIP_SCRAPE=1 POSTSEASON_BOXPA_GAMES="$BOXPA_GAMES" POSTSEASON_BOXPA_PARTS="$BOXPA_PARTS" \
      BACKUP_DIR="$BACKUP_DIR_EVENING" BACKUP_KEEP="$BACKUP_KEEP_EVENING" BOXPA_MANIFEST="$BOXPA_MANIFEST_PATH" \
      bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh" >>"$LOG" 2>&1
    BOXPA_CODE=$?
    BOXPA_ELAPSED=$(( $(date +%s) - BOXPA_STARTED ))
    note "boxpa sync exit=${BOXPA_CODE} elapsed=${BOXPA_ELAPSED}s"
    BOXPA_RECORDED="$(py boxpa-record --games "$BOXPA_GAMES" --code "$BOXPA_CODE" \
      --manifest "$BOXPA_MANIFEST_PATH" --elapsed "$BOXPA_ELAPSED" --parts "$BOXPA_PARTS")" || BOXPA_RECORDED="halted"
    note "boxpa-record → ${BOXPA_RECORDED}"
    [ "$BOXPA_RECORDED" = "halted" ] && EXIT_CODE=69
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
