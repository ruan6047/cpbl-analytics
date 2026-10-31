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
  2. 跑 cpbl-refresh-recent 做增量爬取；成功後重建隊伍比較背景摘要（來源未變＝no-op；失敗不擋）
  3. 爬取成功且 SYNC_PROD≠0 時，以 SKIP_SCRAPE=1 WITH_DETAIL=1 呼叫
     scripts/refresh-cpbl-prod.sh 同步到 production
  4. 把分相結果寫進狀態檔，供 AI／人接手診斷

會寫什麼（⚠️ 高後果，且沒有 dry-run）
  · 本機 PostgreSQL：cpbl-refresh-recent 的增量寫入、team_comparison_* 摘要三表
  · production PostgreSQL：由步驟 3 的同步鏈寫入（SYNC_PROD=0 可關閉）
  · 本機檔案系統：logs/refresh-YYYYMMDD-HHMMSS.log（只留最近 30 份）、
    logs/last-status.json、logs/last-launchd-status.json
  · 正式站 HTTP 檢查＋可用性 ping（#398）：沒走到同步收尾哨兵的執行（甲型 skip、爬取失敗、
    DB 容器沒開、SYNC_PROD=0 等）結束前，以 scripts/prod_availability.py sentinel 對正式站量約
    2 分鐘，寫 logs/availability-sentinel-*.tsv，依結果對 .env 的 CPBL_AVAILABILITY_PING_URL 送
    成功 ping 或告警；同步日由 refresh-cpbl-prod.sh 的哨兵送，同一次執行只送一個。不影響離開碼

怎麼呼叫
  scripts/scrape-daily.sh          # 完整增量（games+累計+對戰+分項+逐球…）
  scripts/scrape-daily.sh fast     # 只更新 games+累計，跳過耗時細項
  SYNC_PROD=0 scripts/scrape-daily.sh   # 只爬本機，不同步 production
  位置參數只接受 fast；其餘一律 exit 64。launchd 以無參數呼叫。

日型閘門（#364；PLAN-r2 §3.2，判定在 src/cpbl/ingest/daily_gate.py）
  取鎖後先判日型（只讀本機 games＋狀態檔；甲型候選另唯讀查 stats 賽程）：
    有賽型 full      昨天有 A／D／E／C 排定場 → 完整鏈（4/4 套訓練閘門）
    乙型   light     昨天無、今天有／上次失敗／探測有新場 → 爬取＋同步；衍生依來源變動訊號
    甲型   sync_only 昨今皆無但本機有未同步寫入 → 不爬；衍生依來源訊號（J3／J4）＋同步，不訓練
    甲型   skip      其餘 → 不爬、不備份、不同步；狀態寫成功＋skipped=true
  判定程式本身失敗 → 完整鏈（現況）。每次都寫今日賽程檔 logs/daily-schedule-today.json。
  `cpbl-refresh-recent --plan` 可先看今天會跑哪些步驟（唯讀）。
  聯盟收官（#391，判定在 src/cpbl/season_close.py）：總冠軍確定後該軍收官 → 日型不看該軍賽別、
    cpbl-refresh-recent 略過該軍爬蟲（DAILY_CLOSED_LEAGUES）；兩軍皆收官 → 不探測、不重試，只依
    未同步寫入走 sync_only／skip。休賽期人工指示更新：DAILY_FORCE_FULL=1（不判日型、不帶收官）。

環境變數
  REFRESH_TRIGGER   manual（預設）或 launchd；其他值一律 exit 64
  SYNC_PROD         0＝爬完不同步 production（預設 1）
  REFRESH_LOCK_DIR  互斥鎖目錄（預設 /private/tmp/cpbl-analytics-refresh.lock）
  DAILY_FORCE_FULL  1＝不判日型、強制完整鏈且不套訓練閘門（逃生閥，不需 revert）

離開碼
  0 成功 · 64 參數錯 · 69 有部分步驟失敗但其餘完成（仍會同步 production）
     69 有四個來源，看 refresh_log 的 note 分辨：逐場 gamelog 失敗（列出場號）／
     官方球隊戰績對帳失敗（列出 sc=N(kind)，該幾列已拒寫）／
     球種推算失敗（列出 kind/階段，該段保留上一輪標籤）／
     當季衍生重建失敗（列出 builder，如 team_der／re24；該表保留上一輪值）／
     livelog 同號檢查未過（#357；列出本次寫入的場次與原因）
  70 狀態檔寫入失敗 · 75 鎖被佔用 · 127 本機 DB 容器沒開
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

# 常設公告owner持有同一把鎖時，正常自然daily先有界排隊；不kickstart或搶鎖。
# 未知／已死owner維持原fail-closed，不刪kind marker來猜remote已停止。
if [ "$(cat "$LOCK_DIR/kind" 2>/dev/null || true)" = "lineup-announcements" ]; then
  waited=0
  while [ -d "$LOCK_DIR" ] && [ "$waited" -lt 1355 ]; do
    owner_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    [ -n "$owner_pid" ] && kill -0 "$owner_pid" 2>/dev/null || break
    sleep 1
    waited=$((waited + 1))
  done
fi

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

# —— #398 非同步日的可用性補位 ——
# 正式站可用性 check（healthchecks `cpbl-prod-availability`，週期 1 天）原本只由同步收尾哨兵
# （refresh-cpbl-prod.sh 的 start_availability_sentinel，#353 WP4a）回報。凡是鏈有跑、卻沒走到那一步
# 的日子（甲型 skip、本機 DB 容器沒開 127、爬取失敗、SYNC_PROD=0、已嘗試同步但 refresh 在啟動哨兵前
# 就結束、start 狀態寫入失敗 70、可攔到的訊號中斷），check 收不到任何結果：休季時正常站台被誤報 DOWN，
# 而真停機也被一個停在 DOWN 的 check 蓋掉（#398 需求）。
# 做法：refresh 在**哨兵已啟動**時寫下 marker（路徑由這裡經 DAILY_SENTINEL_MARKER 傳入）；EXIT trap
# 看不到 marker 就以**同一支** prod_availability.py sentinel 同步跑一次（停止檔預先建好＝取樣一輪後再量
# 120 秒，約 2 分鐘）。⛔ 刻意不另寫判準或改用 probe：判準、端點、送法必須與同步日的哨兵逐字相同，
# 否則就是第二套監測（#398 限制）。⛔ 刻意不看 SYNC_ATTEMPTED：已嘗試同步但沒到哨兵的出口也要補。
# 刻意走系統 python3（同 refresh_status.py）：DB 容器沒開或 uv 起不來的日子也要能量。
# ⛔ 補位的任何結果都不改本腳本的離開碼與狀態檔（狀態檔在補位之前就已寫完，daily check 的 ping 不延後）。
# 鎖取不到（75）、參數錯（64）、--help 都在這之前結束、不補位：屬「鏈本身沒執行」（#398 D1 裁定）。
# 停用＝把 EXIT trap 改回只呼叫 release_lock（#398 規劃 §5 回復方式＝revert）。
DAILY_SENTINEL_MARKER="${TMPDIR:-/tmp}/cpbl-daily-sentinel-started.$$"
rm -f "$DAILY_SENTINEL_MARKER" 2>/dev/null || true
export DAILY_SENTINEL_MARKER
availability_fallback() {  # $1＝本腳本即將使用的離開碼（只寫進 log，不改它）
  local rc="$1" out="${LOG:-/dev/stderr}" stop
  if [ -e "$DAILY_SENTINEL_MARKER" ]; then
    rm -f "$DAILY_SENTINEL_MARKER" 2>/dev/null || true
    return 0
  fi
  stop="${TMPDIR:-/tmp}/cpbl-daily-sentinel-stop.$$"
  touch "$stop" 2>/dev/null || true
  local api_info_url="${API_INFO_URL:-https://cpbl.ruan-ruan.com/api/info}"
  {
    echo "[$(date '+%F %T')] 可用性補位：本次未啟動同步收尾哨兵（day_type=${DAY_TYPE:-未判定} scrape_code=${CODE:-未執行} sync_attempted=${SYNC_ATTEMPTED:-0} exit=${rc}）→ 單獨跑一次 prod_availability sentinel（約 2 分鐘）"
    python3 "$REPO_DIR/scripts/prod_availability.py" sentinel --stop-file "$stop" \
      --base-url "${api_info_url%/api/info}" --env-file "$REPO_DIR/.env" \
      --out "$REPO_DIR/logs/availability-sentinel-$(date +%Y%m%d-%H%M%S).tsv" </dev/null \
      || echo "[$(date '+%F %T')] ⚠ 可用性補位 exit=$?（不影響本次離開碼）"
  } >>"$out" 2>&1
  rm -f "$stop" "$DAILY_SENTINEL_MARKER" 2>/dev/null || true
}
# 單一 EXIT trap（bash 一個訊號只有一個 trap）：先補位、再放鎖，最後照原碼離開。
# 補位期間（約 2 分鐘）若收到 INT／TERM／HUP，原本的 `exit 130/143` trap 會在 EXIT trap 裡直接結束、
# 跳過 release_lock，留下待下次回收的 stale lock；所以這裡改成「放鎖後照原碼離開」——狀態檔與離開碼
# 在補位前就已定案，中斷只影響補位本身（哨兵被 SIGTERM 時自己會以偵測器失敗告警，fail-closed）。
on_exit() {
  local rc=$?
  trap 'rm -f "${TMPDIR:-/tmp}/cpbl-daily-sentinel-stop.$$" "$DAILY_SENTINEL_MARKER" 2>/dev/null; release_lock; exit "$rc"' INT TERM HUP
  availability_fallback "$rc" || true
  release_lock
  exit "$rc"
}
trap on_exit EXIT
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

# 日型（#364）：預設 full＝現況。判定讀不到／判定程式失敗一律退回 full（fail closed＝多跑）。
DAY_TYPE=full
DAY_REASON="未判定"
# #391 聯盟收官：decide 印的 CLOSED_LEAGUES（major,farm）；判定失敗／逃生閥＝空（照常爬，fail open）。
CLOSED_LEAGUES=""
SYNC_MARKER="logs/daily-sync-marker.json"
TODAY_FILE="logs/daily-schedule-today.json"

# 前置檢查：本機 DB（OrbStack/Docker 上的 5433）必須在
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q cpbl-analytics-db; then
  echo "[$(date '+%F %T')] FATAL: 本機 DB 容器未啟動（OrbStack 沒開？）" | tee -a "$LOG"
  CODE=127
else
  if [ "${DAILY_FORCE_FULL:-0}" = "1" ]; then
    DAY_REASON="DAILY_FORCE_FULL=1：強制完整鏈（逃生閥）"
  else
    # 只讀本機 games＋歷史＋同步標記；甲型候選才唯讀查 stats（不連 www）。順手寫今日賽程檔。
    GATE_OUT="$("$UV" run python -m cpbl.ingest.daily_gate decide \
      --history "logs/schedule-history/com.cpbl.scrape-daily.jsonl" \
      --sync-marker "$SYNC_MARKER" --today-file "$TODAY_FILE" \
      --started-at "$STARTED_AT" 2>>"$LOG")"
    GATE_CODE=$?
    printf '%s\n' "$GATE_OUT" >>"$LOG"
    GATE_TYPE="$(printf '%s\n' "$GATE_OUT" | sed -n 's/^DAY_TYPE=//p' | tail -n 1)"
    case "$GATE_CODE:$GATE_TYPE" in
      0:full|0:light|0:sync_only|0:skip)
        DAY_TYPE="$GATE_TYPE"
        DAY_REASON="$(printf '%s\n' "$GATE_OUT" | sed -n 's/^REASON=//p' | tr '\n' ';' | sed 's/;$//')"
        CLOSED_LEAGUES="$(printf '%s\n' "$GATE_OUT" | sed -n 's/^CLOSED_LEAGUES=//p' | tail -n 1)"
        ;;
      *)
        # 判定失敗時 decide 沒能保證今日賽程檔是這次寫的；刪掉，免得同日稍早的舊檔被當成有效（F4）。
        rm -f "$TODAY_FILE"
        DAY_REASON="日型判定失敗（exit=${GATE_CODE}，輸出無合法 DAY_TYPE）→ 完整鏈（fail closed）"
        ;;
    esac
  fi
  echo "[$(date '+%F %T')] day type=${DAY_TYPE}（${DAY_REASON}）closed_leagues=${CLOSED_LEAGUES:-none}" | tee -a "$LOG"

  case "$DAY_TYPE" in
    skip)
      # 甲型：不爬、不做衍生、不同步（PLAN-r5 §3.2）。
      echo "[$(date '+%F %T')] 甲型：略過 cpbl-refresh-recent（不爬 www）" | tee -a "$LOG"
      CODE=0
      ;;
    *)
      # full／light／sync_only 都進 cpbl-refresh-recent：sync_only 在程式內不爬，只依 §3.2.3
      # 來源訊號（J3／J4 週回補）跑衍生；light 爬取後同樣依訊號決定衍生（⛔ 不依日型直接略過）。
      # --group scrape：官網爬蟲需 playwright（scrape group）。uv run 為 inexact sync
      # 不會主動剪套件，但顯式帶 group 可防有人跑過 `uv sync`（exact）剪掉後靜默失敗。
      # #391：DAILY_CLOSED_LEAGUES 讓 cpbl-refresh-recent 略過已收官軍的 www／stats 爬取（非爬蟲步驟照跑）。
      if [ -n "$ARGS" ]; then
        DAILY_DAY_TYPE="$DAY_TYPE" DAILY_CLOSED_LEAGUES="$CLOSED_LEAGUES" "$UV" run --group scrape cpbl-refresh-recent "$ARGS" >>"$LOG" 2>&1
      else
        DAILY_DAY_TYPE="$DAY_TYPE" DAILY_CLOSED_LEAGUES="$CLOSED_LEAGUES" "$UV" run --group scrape cpbl-refresh-recent >>"$LOG" 2>&1
      fi
      CODE=$?
      if [ "$DAY_TYPE" != sync_only ]; then
        # 賽程可能剛更新（即使 refresh 非零退出，前段的 scrape_games 也可能已寫入）：一律覆寫今日
        # 賽程檔（stage=after_scrape）。⛔ 覆寫失敗不得留下 decide 階段的同日舊檔——它的 date 也是
        # 今天，消費端（#365）會照單全收、把剛補進的場判成沒有（#364 審核 F4）。失敗就刪檔，
        # 讓消費端退回 DB。Python 端失敗時自己也會刪；這裡再刪一次是給「uv／python 起不來」的情形。
        if ! "$UV" run python -m cpbl.ingest.daily_gate today-schedule --out "$TODAY_FILE" \
             --day-type "$DAY_TYPE" >>"$LOG" 2>&1; then
          rm -f "$TODAY_FILE"
          echo "[$(date '+%F %T')] WARN 今日賽程檔覆寫失敗，已刪檔（消費端退回 DB；不影響 overall）" | tee -a "$LOG"
        fi
      fi
      ;;
  esac
fi
echo "[$(date '+%F %T')] scrape exit=${CODE}" | tee -a "$LOG"

# 隊伍比較背景摘要 builder（#287 S06 WP4b；PLAN r2 §2.3）：爬取成功（含 69 部分失敗）後、同步前，
# 以本機已完成 A 場重算 source_hash；同源同版＝no-op exit 0，來源更正才建新 build 並切 current。
# ⛔ 失敗不擋每日鏈：退出碼只記在 log、不併入 overall；失敗時 --record-failure 在**本機** refresh_log
#    記一列 scope=team-comparison-build，舊摘要保留並標待更新。摘要表尚未 migrate 時為 exit 6（只記 log）。
# 寫入對象只有本機 team_comparison_* 三表；同步到 production 在 refresh-cpbl-prod.sh 的 gamelog 之後。
TC_BUILD_CODE=skip
if { [ "$CODE" -eq 0 ] || [ "$CODE" -eq 69 ]; } && [ "$DAY_TYPE" != skip ]; then
  "$UV" run cpbl-build-team-comparison --year "$(date +%Y)" --record-failure >>"$LOG" 2>&1
  TC_BUILD_CODE=$?
fi
echo "[$(date '+%F %T')] team-comparison build exit=${TC_BUILD_CODE}（不影響 overall）" | tee -a "$LOG"

# 本機爬成功後自動同步生產（SKIP_SCRAPE：資料已在本機，只 upsert 到 prod + VPS 重建特徵）。
# 關閉：SYNC_PROD=0 scripts/scrape-daily.sh
#
# 69＝`cpbl-refresh-recent` 的「有部分步驟失敗、其餘步驟照常完成」
# （`src/cpbl/ingest/cpbl_gamelog.py::EXIT_INCOMPLETE_SCRAPE`；shell 讀不到 Python 常數，
# 這裡是字面複本，一致性由 tests/test_gamelog_reconcile.py 機械比對）。
# ⚠️ 這個碼有**四個來源**，值班判讀要看 refresh_log 的 note 才分得出來：
#   1. 逐場 gamelog 有失敗 → note 列出失敗場號。
#   2. 官方球隊戰績對帳失敗（拿到別的球季／空表，已拒寫）→ note 列出 sc=N(kind)
#      （DATA-STANDINGS-YEAR-IGNORED1 岔路 1 裁定沿用同一語意與同一個碼）。
#   3. 球種推算失敗 → note 列出 kind/階段。
#   4. 當季衍生重建失敗（#222：DER／wSB／守備局數／捕手失分／特性／RE24）→ note 列出 builder。
#
# 為什麼 69 仍要同步（DATA-BOX-DEEP-SILENT-FAIL1 Q3 裁定＝甲-2）：擋同步只是把「靜默
# 失敗」換成「生產靜默落後」，兩者一樣沒人在看，而且那天其餘所有更新（賽程/累計/分項/
# PA build）都是好的。專案在 PA build 已對同一形狀裁過不擋。失敗本身不會因此消失：
# 退出碼是 69 不是 0，狀態檔記 state=failed／failed_phase=scrape／exit_code=69，
# refresh_log 記 ok=false 並在 note 列出失敗場號／未寫入的 season_code。
SYNC_ATTEMPTED=0
SYNC_CODE=0
SKIPPED=0
if [ "$DAY_TYPE" = skip ]; then
  # 甲型（#364 §3.2.2）：不備份、不同步；狀態寫「成功、skipped=true、reason」並 append 歷史，
  # schedule_watch.py 才不會把刻意略過判成 MISSING／SKIPPED_CONSECUTIVE。
  SKIPPED=1
  echo "[$(date '+%F %T')] 甲型：略過備份與同步（skipped=true）" | tee -a "$LOG"
elif { [ "$CODE" -eq 0 ] || [ "$CODE" -eq 69 ]; } && [ "$SYNC_ENABLED" -eq 1 ]; then
  SYNC_ATTEMPTED=1
  echo "[$(date '+%F %T')] sync prod (SKIP_SCRAPE=1 WITH_DETAIL=1 DAILY_DAY_TYPE=${DAY_TYPE})" | tee -a "$LOG"
  # DAILY_DAY_TYPE 讓 refresh-cpbl-prod.sh 套 §3.5 訓練閘門（乙型／只同步不訓練）；同步與備份路徑不變。
  # 呼叫行刻意維持原字面（tests/test_shell_help_guard.py 釘住），日型改由 export 帶入。
  export DAILY_DAY_TYPE="$DAY_TYPE"
  SKIP_SCRAPE=1 WITH_DETAIL=1 bash "$REPO_DIR/scripts/refresh-cpbl-prod.sh" >>"$LOG" 2>&1
  SYNC_CODE=$?
  if [ "$SYNC_CODE" -eq 0 ]; then
    echo "[$(date '+%F %T')] sync prod ok" | tee -a "$LOG"
    # 記下本機寫入計數器：之後的甲型日據此判「自上次同步後本機有沒有新寫入」。失敗只記 log——
    # 標記缺／舊的代價是下一個甲型日多同步一次（fail closed 方向）。
    "$UV" run python -m cpbl.ingest.daily_gate mark-synced --sync-marker "$SYNC_MARKER" >>"$LOG" 2>&1 \
      || echo "[$(date '+%F %T')] WARN 同步標記寫入失敗（下一個甲型日會改為只同步）" | tee -a "$LOG"
  else
    echo "[$(date '+%F %T')] sync prod FAILED exit=${SYNC_CODE} (見 log)" | tee -a "$LOG"
  fi
fi

# CODE=69 時 overall 維持 69（不被 SYNC_CODE 覆寫）：狀態檔的 exit_code 由
# refresh_status.py 依 --scrape-code 判為 69／failed_phase=scrape，overall 跟著它才不會
# 出現「離開碼說 A、狀態檔說 B」。同步若也失敗，其碼記在狀態檔 sync_exit_code 與 log；
# 兩種情況 launchd 看到的都是非零。
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
  --day-type "$DAY_TYPE" --skipped "$SKIPPED"
)
if [ "$SKIPPED" -eq 1 ]; then
  FINISH_ARGS+=(--skip-reason "$DAY_REASON")
fi
if [ "$SYNC_ATTEMPTED" -eq 1 ]; then
  FINISH_ARGS+=(--sync-code "$SYNC_CODE")
fi
if ! python3 "$REPO_DIR/scripts/refresh_status.py" "${FINISH_ARGS[@]}"; then
  echo "[$(date '+%F %T')] FATAL: 無法寫入 refresh final 狀態" | tee -a "$LOG"
  exit 70
fi

exit "$OVERALL_CODE"
