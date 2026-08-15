#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
# 每週一次的逐球全季重跑（INGEST-GAME-TM-REFACTOR1-G4 Phase A）。
#
# 為什麼要這一支：單場 API 是「當下」的官方值，官方可在任何時點做賽後修正（實測到
# content 敘述改寫、TrackMan 重算）。每日增量只涵蓋近幾天的窗口，早季場次一旦被改就
# 永遠不會回頭對齊。每週把全季完成場重跑一次，使任何時點的事後修正**最遲七天內收斂**。
#
# 紅線：**排程失敗不得中斷既有每日 refresh**（卡面驗收條件）。落地方式有三層：
#   1. 獨立 launchd job、獨立 log 與狀態檔——每日鏈（scrape-daily.sh / refresh_status.py）
#      完全不讀本檔任何產物，故本檔失敗在每日鏈上不可觀測。
#   2. 共用同一把 refresh lock，且**忙碌即跳過**（不等待、不搶佔）：兩者都寫
#      cpbl.pitch_tracking，必須互斥；但本檔絕不因為想跑而卡住每日鏈。
#   3. 排在週一（中職固定休兵、無新完成場）且遠離每日 10:10 觸發點，讓重疊在時間上
#      也不成立——即使 Mac 睡醒後 launchd 補跑錯過的每日 job，本檔也會因忙碌而跳過。
#
# 產物：logs/weekly-game-pitches-YYYYMMDD-HHMM.log、logs/last-weekly-pitches.json
#
# 用法：scripts/weekly-game-pitches.sh --help     # 只印用法，不碰任何東西
#       scripts/weekly-game-pitches.sh            # 全季 A + D
#       YEAR=2026 scripts/weekly-game-pitches.sh  # 指定年份
set -uo pipefail

# ============================================================== argv 守衛
# 這一段必須留在檔案最前面、任何副作用之前——往下移就等於沒有（下方第一個副作用是
# `mkdir -p logs`，再往下就是全季逐球重抓）。
#
# 沒有守衛時 `--help` 不會被任何人接住，直接開始對 stats.cpbl 打整季請求並寫
# cpbl.pitch_tracking。想知道它在做什麼的人應該拿到答案（exit 0），誤打的參數
# 則要被拒絕（exit 64＝EX_USAGE，與同目錄其他排程腳本同碼）而不是被忽略。
usage() {
  cat <<'EOF'
scripts/weekly-game-pitches.sh — 每週一次的全季逐球重跑（launchd 週一 13:10）

在做什麼
  1. 忙碌即跳過：拿不到 refresh lock 就直接 exit 0（每日鏈優先，絕不等待、不搶佔）
  2. 確認本機 DB 容器在
  3. 對 kind A 與 D 各跑一次 cpbl-scrape-game-pitches <YEAR> <KIND>
     （單一 kind 失敗不中止另一 kind，整體仍記為失敗）

為什麼要重跑整季：單場 API 是「當下」的官方值，官方可在任何時點做賽後修正。
每日增量只涵蓋近幾天，早季場次一旦被改就再也不會回頭對齊；每週全季重跑一次，
使任何時點的事後修正最遲七天內收斂。

會寫什麼（⚠️ 高後果，且沒有 dry-run）
  · 本機 PostgreSQL：cpbl-scrape-game-pitches 對逐球資料的寫入
  · 本機檔案系統：logs/weekly-game-pitches-YYYYMMDD-HHMMSS.log（只留最近 12 份）、
    logs/last-weekly-pitches.json
  · 對 stats.cpbl.com.tw 發出整季份量的請求

怎麼呼叫（不接受位置參數，設定一律走環境變數）
  scripts/weekly-game-pitches.sh              # 全季 A + D，年份取今年
  YEAR=2026 scripts/weekly-game-pitches.sh    # 指定年份

環境變數
  YEAR              要重跑的年份（預設 date +%Y）
  REFRESH_LOCK_DIR  互斥鎖目錄（預設 /private/tmp/cpbl-analytics-refresh.lock）

離開碼
  0 成功或忙碌跳過 · 64 參數錯 · 127 本機 DB 容器沒開 · 其餘＝爬取的原始離開碼

背景：docs/AI_RUNBOOK.md（每週全季重跑）
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

# 位置參數契約（逐支不同，刻意不與守衛共用）：本腳本一個位置參數都不收，
# 而補救方式是 `YEAR=` 而不是別的環境變數——這一句必須逐支為真，不可共用。
if [ "$#" -gt 0 ]; then
  printf '未知參數：%s\n' "$1" >&2
  printf '本腳本不接受位置參數，年份請用 YEAR=；用法請打 --help。\n' >&2
  exit 64
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
YEAR="${YEAR:-$(date +%Y)}"
LOCK_DIR="${REFRESH_LOCK_DIR:-/private/tmp/cpbl-analytics-refresh.lock}"
STARTED_AT="$(date '+%Y-%m-%dT%H:%M:%S%z')"

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
LOG="logs/weekly-game-pitches-${TS}.log"
STATUS="logs/last-weekly-pitches.json"

write_status() {  # $1=result $2=exit_code $3=note
  cat > "$STATUS" <<EOJ
{"result":"$1","exit_code":$2,"note":"$3","year":$YEAR,
 "started_at":"$STARTED_AT","finished_at":"$(date '+%Y-%m-%dT%H:%M:%S%z')","log":"$LOG"}
EOJ
}

# 忙碌即跳過：每日 refresh 優先，本檔絕不等待、絕不搶佔既有 lock。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$(date '+%F %T')] 每日 refresh 進行中，本週重跑跳過（下週再收斂）" | tee "$LOG"
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

echo "[$(date '+%F %T')] start: 全季逐球重跑 year=${YEAR} kinds=A,D" | tee "$LOG"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q cpbl-analytics-db; then
  echo "[$(date '+%F %T')] FATAL: 本機 DB 容器未啟動（OrbStack 沒開？）" | tee -a "$LOG"
  write_status "failed" 127 "local DB container not running"
  exit 127
fi

CODE=0
for KIND in A D; do
  echo "[$(date '+%F %T')] kind=${KIND}" | tee -a "$LOG"
  # stats.cpbl 無反爬（httpx 直連），不需 playwright/scrape group。
  "$UV" run cpbl-scrape-game-pitches "$YEAR" "$KIND" >>"$LOG" 2>&1
  RC=$?
  echo "[$(date '+%F %T')] kind=${KIND} exit=${RC}" | tee -a "$LOG"
  [ "$RC" -ne 0 ] && CODE="$RC"   # 單一 kind 失敗不中止另一 kind，但整體記為失敗
done

echo "[$(date '+%F %T')] overall exit=${CODE}" | tee -a "$LOG"
ls -1t logs/weekly-game-pitches-*.log 2>/dev/null | tail -n +13 | xargs -I{} rm -f {} 2>/dev/null || true
[ "$CODE" -eq 0 ] && write_status "ok" 0 "" || write_status "failed" "$CODE" "see log"
exit "$CODE"
