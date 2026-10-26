#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
# CPBL 線上資料手動更新（不掛 cron，避免浪費資源；要更新時自己跑）。
#
# 為什麼要在本機跑：CPBL 官網（HiNetCDN）對海外 IP 封鎖資料路徑，VPS 爬不到，
# 只有台灣 IP（你的 Mac）能爬。故流程＝本機爬 → 非破壞性 upsert 同步到 prod →
# VPS 重建賽果特徵（build-features 只讀 DB，VPS 可跑）。
#
# 用法：./scripts/refresh-cpbl-prod.sh --help                        # 只印用法，不碰任何東西
#       ./scripts/refresh-cpbl-prod.sh
#       WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh                 # 連同選手細項（耗時逾 1 小時）
#       SKIP_SCRAPE=1 WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh   # 本機已最新：只同步不重爬
#
# 可用環境變數覆蓋：LOCAL_DB / VPS / DEPLOY_PATH / WITH_DETAIL / SKIP_SCRAPE
set -euo pipefail

# ============================================================== argv 守衛
# 這一段必須留在檔案最前面、任何副作用之前——往下移就等於沒有。
#
# 為什麼：本腳本「探索動作即造成損害」。沒有守衛時 `--help` 不會被任何人接住，
# 直接落進下方主流程：爬官網 → 備份並 upsert **production** 資料庫 → VPS 重跑訓練。
# 同一類事故 2026-08-05 已經發生過一次（`cpbl-scrape-pitches --help` 觸發真實爬蟲
# 並寫進 DB，見 tests/test_cli_help_guard.py 檔頭），那次修的是 Python CLI 這一面；
# 這一支的破壞半徑更大——那邊是一支爬蟲，這邊是整條生產同步鏈。
#
# 想知道它在做什麼的人應該拿到答案，所以 `--help` 印用法並 exit 0，不是 exit 1。
# 未知參數則拒絕（exit 64＝EX_USAGE，與 scrape-daily.sh／backup-prod-db.sh 同碼）：
# 本腳本從不吃位置參數，收到就代表呼叫端誤會了介面，靜默忽略只會讓誤會延續。
usage() {
  cat <<'EOF'
scripts/refresh-cpbl-prod.sh — 把本機 CPBL 資料同步到 production（四步鏈）

在做什麼
  1/4  本機（台灣 IP）爬官網最新資料，然後重建賽事預測特徵 game_features
  2/4  備份 production 整庫（cpbl schema ＋ 主站 public）；備份驗證不過即中止
  3/4  對 production 套 migration，再逐表非破壞性 upsert 同步
       （WITH_DETAIL 時於 gamelog 之後另做隊伍比較摘要 insert-only 同步；失敗只記錄、不擋其他同步）
  4/4  VPS 重跑賽事預測回測與 serving 模型，最後驗證線上 /api/info freshness

會寫什麼（⚠️ 高後果，且沒有 dry-run）
  · production PostgreSQL：逐表 upsert；game_features 為整表重建；PA build 家族逐場替換＋全族對帳
  · production 主機檔案系統：資料庫備份檔、模型 artifact
  · 本機 PostgreSQL：cpbl-scrape-* 與 cpbl-build-features 的寫入
  · 完整鏈另起可用性哨兵（#353）：logs/availability-sentinel-*.tsv；正式站任一筆 000／≥5s 或 0 樣本
    即對 .env 的 CPBL_AVAILABILITY_PING_URL 送告警。哨兵結果不影響本腳本成敗
  不要拿這一支來「跑跑看會發生什麼」——它沒有唯讀模式。

怎麼呼叫（不接受位置參數，設定一律走環境變數）
  ./scripts/refresh-cpbl-prod.sh                              # 完整鏈：爬 → 同步 → 回測
  WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh                # 連同選手細項（耗時逾 1 小時）
  SKIP_SCRAPE=1 WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh  # 本機已最新：只同步不重爬
                                                              # ↑ 每日鏈 scrape-daily.sh 走這條
  LINEUP_ONLY=1 SKIP_SCRAPE=1 ./scripts/refresh-cpbl-prod.sh # 有限公告；不爬、不訓練、不檢查整鏈 freshness
  ROSTER_ONLY=1 SKIP_SCRAPE=1 BACKUP_DIR=<獨立目錄> ./scripts/refresh-cpbl-prod.sh
                                                              # 季後 32 人名單三表 insert-only 同步（手動、需授權）
  POSTSEASON_BOXPA_ONLY=1 SKIP_SCRAPE=1 POSTSEASON_BOXPA_GAMES=2026-C-2 BACKUP_DIR=<獨立目錄> \
    BOXPA_MANIFEST=<絕對路徑> ./scripts/refresh-cpbl-prod.sh   # 季後目標場 box 七表＋PA 五表 scoped 同步
  TEAM_COMPARISON_ONLY=1 SKIP_SCRAPE=1 BACKUP_DIR=<獨立目錄> ./scripts/refresh-cpbl-prod.sh
                                                              # 隊伍比較摘要三表 insert-only 同步（手動、需授權）

環境變數
  LOCAL_DB      本機 PostgreSQL 容器名（預設 cpbl-analytics-db-1）
  VPS           production 主機的 ssh 目標
  DEPLOY_PATH   production 主機上的部署目錄
  API_INFO_URL  freshness 驗證要打的端點
  WITH_DETAIL   非空＝連同選手細項（投打對決 / 對戰各隊 / 分項）
  SKIP_SCRAPE   非空＝跳過爬取，直接同步本機現有資料
  LINEUP_ONLY   1＝搭配 SKIP_SCRAPE=1，只驗證備份、套 schema、同步有限公告表
  ROSTER_ONLY   1＝搭配 SKIP_SCRAPE=1 與獨立 BACKUP_DIR，只做名單三表 insert-only 同步
                （唯讀比對；無變更不備份不寫；有待插入才備份＋單交易插入＋事後對帳；
                 不 migrate、不爬、不訓練、不寫 refresh 標記、不碰其他表）
  REUSE_VERIFIED_BACKUP／REUSE_VERIFIED_BACKUP_SHA256／BACKUP_RECORD
                只用於 POSTSEASON_RESULTS_ONLY／POSTSEASON_BOXPA_ONLY（晚間鏈每晚首次同步前備份一次，#365）：
                帶入當晚已驗證備份的路徑與 sha256；本行程重驗存在／位於 BACKUP_DIR／sha256 才略過備份，
                不符即照常重備。BACKUP_RECORD＝寫入 `new|reuse <sha256> <path>` 的檔案（晚間狀態檔入帳）
  POSTSEASON_BOXPA_ONLY 1＝搭配 SKIP_SCRAPE=1、POSTSEASON_BOXPA_GAMES、獨立 BACKUP_DIR、BOXPA_MANIFEST：
                只對目標場鍵 upsert box 七表、單交易替換 PA 五表，逐表逐場對帳；
                POSTSEASON_BOXPA_PARTS＝box／pa／box,pa（預設 box,pa）限定這次送哪些來源
                （不 TRUNCATE／CASCADE、不 migrate、不訓練、不寫 refresh 標記、不呼叫 prod_cpbl_api）
  TEAM_COMPARISON_ONLY
                1＝搭配 SKIP_SCRAPE=1 與獨立 BACKUP_DIR，只做隊伍比較摘要三表 insert-only 同步
                （與 ROSTER_ONLY 同形：唯讀比對；無變更不備份不寫；有待寫才備份＋單交易寫入＋事後對帳）
  DAILY_DAY_TYPE
                每日鏈（scrape-daily.sh）帶入的日型（#364）；未設定＝手動直呼，行為同現況（不套閘門）。
                full：§3.5 訓練閘門——本機一軍完成場自正式站上次 model_versions(task='outcome') 後
                      有新增，才跑 cpbl-build-features、game_features 全鏡像、cpbl-train-outcome；
                      正式站 artifact 訓練上界季 < 今年−1 才跑 cpbl-train-outcome-simple。
                      正式站讀不到（ssh／psql 失敗、無列）一律照跑。
                light／sync_only：上述四步一律略過（乙型／甲型只同步）。同步與備份路徑不變。
  DAILY_FORCE_FULL
                1＝不套 §3.5 閘門，四步照跑（逃生閥）
  PA_FULL_RESYNC
                1＝PA 五表改跑全量模式（全部場 DELETE＋重灌，不 TRUNCATE；需 WITH_DETAIL）。
                只在全族對帳不等、經需求方個案授權時人工指定（#353 D5）；帶 DAILY_DAY_TYPE 一律拒絕

離開碼
  0 成功 · 64 參數錯 · 65 取不到本機 freshness 基準 · 67 同步 payload 驗證失敗
  完整鏈 PA 五表（#353）：67 簽章／payload 守衛不過（未送） · 68 全族對帳不等 · 72 ssh 失敗 · 74 prod psql 錯誤
  68 POSTSEASON_RESULTS_ONLY 的 data-only 對帳不等（季後晚間鏈：停止當晚）
  ROSTER_ONLY：67 本機名單自檢失敗 · 69 production 尚無名單表（待部署窗口）
               70 同 scope 內容不同拒絕（不寫、不重試） · 71 事後對帳不等 · 72 目標 psql／ssh 失敗
  POSTSEASON_BOXPA_ONLY：67 本機自檢／payload 守衛不過（未送） · 68 對帳不等 · 72 ssh 連線失敗
               73 production 尚未完賽（等下一次） · 74 production psql 錯誤
  TEAM_COMPARISON_ONLY：67 本機自檢／欄位漂移 · 69 production 尚無摘要表（待部署窗口）
               70 同 build_id 內容不同或目標有本機沒有的 build（不寫、不重試） · 71 事後對帳不等
               72 目標 psql／ssh 失敗

背景：docs/AI_RUNBOOK.md（本機爬 → 同步生產）
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

# SYNC_SCOPE_KEYS_SQL 是本腳本的內部變數（只由 POSTSEASON_BOXPA_ONLY 段從自檢結果設定）。⛔ 不接受外部
# 環境帶進來：否則整鏈的 sync_table 會被悄悄縮成目標場鍵（#293 審核席 2 O5）。故在任何模式之前清掉。
unset SYNC_SCOPE_KEYS_SQL

LOCAL_DB="${LOCAL_DB:-cpbl-analytics-db-1}"
VPS="${VPS:-root@45.76.100.29}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/personal-website}"
API_INFO_URL="${API_INFO_URL:-https://cpbl.ruan-ruan.com/api/info}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
YEAR="$(date +%Y)"
PREV="$((YEAR - 1))"

# #353 WP3：/api/info 改為 TTL 60 秒的行程內快取（api/routers/info.py）。下方 freshness 檢查必須讀到
# 「同步（或 marker）之後才算出」的快取，否則比到的是舊值、資料明明對卻判失敗。這裡只**等快取換代**
# （讀回應標頭 X-Cpbl-Info-Computed-At，epoch 秒），⛔ 不重試內容比對：換代後的快取仍不符，照樣讓
# 同步失敗（同 fetch_api_info 的紅線）。標頭不存在（API 尚未部署 WP3、或取不到）＝沒有快取可等，
# 直接往下。最長約 12×10 秒。
# ⚠️ 比的是 Mac 的 `date +%s` 與 VPS 的 time.time()：兩邊都走 NTP，若 VPS 慢 N 秒只會多等一輪；
# 若快 N 秒，最壞讀到同步結束前 N 秒內算出的快取（未量測時鐘差）。
wait_api_info_cache_since() {  # $1＝epoch 秒
  local since="$1" at="" i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    at="$(curl -sS -o /dev/null -D - --max-time 20 "$API_INFO_URL" 2>/dev/null \
      | awk 'tolower($1) == "x-cpbl-info-computed-at:" { gsub(/\r/, "", $2); print $2 }' \
      | tail -n 1 || true)"
    [[ "$at" =~ ^[0-9]+$ ]] || return 0
    [ "$at" -ge "$since" ] && return 0
    sleep 10
  done
  echo "    ⚠ /api/info 快取 ${i} 輪內未換代（computed_at=${at} < ${since}）；照常比對，不符即失敗" >&2
}

# —— #353 WP4a 每日鏈可用性哨兵（scripts/prod_availability.py sentinel）——
# 完整鏈在開始碰 production（2/4 備份）前啟動，第 4 步結束後再量 120 秒才判定；任一筆 http=000 或
# ≥5s、或 0 樣本 ⇒ 告警（#358 同一收件處）。⛔ 哨兵的任何結果都不改變本腳本的成敗：背景執行、
# 輸出只進 log，wait 的退出碼被丟棄；EXIT trap 保留本腳本原本的退出碼。
# 停用＝移除下方 start_availability_sentinel 那一行呼叫（規劃 r2 §8 回復方式）。
SENTINEL_PID=""
SENTINEL_STOP=""
# 啟動準備的每一步都隔離錯誤（#353 審核 1 第 3 項）：本函式在 set -e 下同步執行，任何一步失敗
# 若外洩，就會讓每日鏈以該碼結束。log 目錄建不起來就改寫 TMPDIR；呼叫端再以 `|| …` 兜底。
start_availability_sentinel() {
  local out_dir="$REPO_DIR/logs"
  SENTINEL_STOP="${TMPDIR:-/tmp}/cpbl-sentinel-stop.$$"
  rm -f "$SENTINEL_STOP" 2>/dev/null || true
  if ! mkdir -p "$out_dir" 2>/dev/null; then
    out_dir="${TMPDIR:-/tmp}"
    echo "    ⚠ 可用性哨兵：logs 目錄建立失敗，紀錄改寫到 ${out_dir}" >&2
  fi
  uv run python "$REPO_DIR/scripts/prod_availability.py" sentinel --stop-file "$SENTINEL_STOP" \
    --base-url "${API_INFO_URL%/api/info}" --env-file "$REPO_DIR/.env" \
    --out "${out_dir}/availability-sentinel-$(date +%Y%m%d-%H%M%S).tsv" </dev/null &
  SENTINEL_PID=$!
  echo "    ⓘ 可用性哨兵已啟動（每 15 秒；結束後再量 120 秒）"
}
# 等待有上限（#353 審核 1 第 1 項）：哨兵停止後最長＝tail 120s＋一輪取樣 3×(10+5)s＝165s；
# 給到 240s，逾時就送 SIGTERM（哨兵收到後以「偵測器自身失敗」告警），⛔ 每日鏈不得被哨兵卡住。
SENTINEL_WAIT_MAX=240
stop_availability_sentinel() {
  [ -n "$SENTINEL_PID" ] || return 0
  local waited=0
  echo "    ⓘ 可用性哨兵：收尾量測 120 秒後判定"
  touch "$SENTINEL_STOP" 2>/dev/null || true
  while kill -0 "$SENTINEL_PID" 2>/dev/null && [ "$waited" -lt "$SENTINEL_WAIT_MAX" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "$SENTINEL_PID" 2>/dev/null; then
    echo "    ⚠ 可用性哨兵 ${SENTINEL_WAIT_MAX} 秒內未結束，已送 SIGTERM（哨兵以自身失敗告警）" >&2
    kill "$SENTINEL_PID" 2>/dev/null || true
  fi
  wait "$SENTINEL_PID" 2>/dev/null || true
  SENTINEL_PID=""
  rm -f "$SENTINEL_STOP" 2>/dev/null || true
}
# 單一 EXIT trap（bash 一個訊號只有一個 trap，後設的會蓋掉先設的）：公告暫存清理＋哨兵收尾。
_on_exit() {
  local rc=$?
  rm -rf "${LINEUP_TMP:-}"
  stop_availability_sentinel || true
  exit "$rc"
}

# 原有限投影與自然鍵guard共用於正常/full及LINEUP_ONLY。
prepare_lineup_copy() {
  LINEUP_TMP="$(mktemp -d)"
  trap _on_exit EXIT
  docker exec "$LOCAL_DB" pg_dump -U cpbl -d cpbl --data-only \
    -t cpbl.game_lineup_announcement_revisions > "$LINEUP_TMP/input.sql"
  # pg_dump 的控制指令不得隨 COPY 資料進 production；只放行固定欄位的單一 COPY。
  python3 - "$LINEUP_TMP/input.sql" "$LINEUP_TMP/copy.sql" <<'PY_VALIDATE' || exit 67
import pathlib
import re
import sys

columns = "year, kind_code, game_sno, source_type, source_url, fetched_at, content_hash, raw_status, raw_payload, last_seen_at"
header = f"COPY cpbl.game_lineup_announcement_revisions ({columns}) FROM stdin;"
lines = pathlib.Path(sys.argv[1]).read_text().splitlines(keepends=True)
copy = []
in_copy = False
complete = False
for line in lines:
    text = line.rstrip("\r\n")
    if in_copy:
        copy.append(line)
        if text == r"\.":
            in_copy = False
            complete = True
        continue
    if text == header and not copy:
        copy.append(line.replace("COPY cpbl.game_lineup_announcement_revisions ", "COPY _lineup_stg ", 1))
        in_copy = True
    elif not text or text.startswith("--") or re.fullmatch(r"\\(?:un)?restrict [A-Za-z0-9]+", text):
        continue
    elif re.fullmatch(r"SET [a-z_]+ = (?:'[A-Za-z0-9_ /,.-]*'|[a-z0-9]+);", text):
        continue
    elif text == "SELECT pg_catalog.set_config('search_path', '', false);":
        continue
    else:
        raise SystemExit("FATAL: 公告 dump 含未核定 SQL 或第二個 COPY")
if not complete or in_copy:
    raise SystemExit("FATAL: 公告 COPY 不完整")
pathlib.Path(sys.argv[2]).write_text("".join(copy))
PY_VALIDATE
}

sync_lineup_announcements() {
  {
    cat <<'SQL_BEGIN'
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
CREATE TEMP TABLE _lineup_stg
  (LIKE cpbl.game_lineup_announcement_revisions INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
  ON COMMIT DROP;
SQL_BEGIN
    cat "$LINEUP_TMP/copy.sql"
    cat <<'SQL_END'
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM _lineup_stg WHERE year <> 2026) THEN
    RAISE EXCEPTION 'announcement scope mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM _lineup_stg
    GROUP BY year,kind_code,game_sno,source_type,fetched_at HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'duplicate announcement natural key';
  END IF;
  IF EXISTS (
    SELECT 1 FROM _lineup_stg s
    JOIN cpbl.game_lineup_announcement_revisions t
      USING (year,kind_code,game_sno,source_type,fetched_at)
    WHERE ROW(t.source_url,t.content_hash,t.raw_status,t.raw_payload)
      IS DISTINCT FROM ROW(s.source_url,s.content_hash,s.raw_status,s.raw_payload)
  ) THEN
    RAISE EXCEPTION 'immutable announcement evidence conflict';
  END IF;
END $$;
INSERT INTO cpbl.game_lineup_announcement_revisions AS tgt
  (year,kind_code,game_sno,source_type,source_url,fetched_at,content_hash,raw_status,raw_payload,last_seen_at)
SELECT year,kind_code,game_sno,source_type,source_url,fetched_at,content_hash,raw_status,raw_payload,last_seen_at
FROM _lineup_stg
ON CONFLICT (year,kind_code,game_sno,source_type,fetched_at) DO UPDATE
SET last_seen_at=GREATEST(tgt.last_seen_at,EXCLUDED.last_seen_at)
WHERE tgt.last_seen_at < EXCLUDED.last_seen_at;
SQL_END
  } > "$LINEUP_TMP/payload.sql"
  ssh -o BatchMode=yes "$VPS" \
    "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
      -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\"" < "$LINEUP_TMP/payload.sql"
  echo '    ✓ 公告單表同步完成（不代表完整更新鏈成功）'
}

# #293 S12 目標場 box／PA 模式的互斥檢查放在所有早退模式之前：任何其他模式旗標同時存在就拒跑，
# 免得先被下面的 ROSTER／LINEUP／RESULTS 分支接走而沒人發現（實際流程見 POSTSEASON_BOXPA_ONLY 段）。
if [ -n "${POSTSEASON_BOXPA_ONLY:-}" ]; then
  if [ "$POSTSEASON_BOXPA_ONLY" != 1 ] || [ "${SKIP_SCRAPE:-}" != 1 ] || [ -n "${WITH_DETAIL:-}" ] \
     || [ -n "${LINEUP_ONLY:-}" ] || [ -n "${ROSTER_ONLY:-}" ] || [ -n "${POSTSEASON_RESULTS_ONLY:-}" ] \
     || [ -n "${TEAM_COMPARISON_ONLY:-}" ]; then
    echo 'FATAL: POSTSEASON_BOXPA_ONLY=1 必須搭配 SKIP_SCRAPE=1，且不得與 WITH_DETAIL／LINEUP_ONLY／ROSTER_ONLY／POSTSEASON_RESULTS_ONLY／TEAM_COMPARISON_ONLY 併用' >&2
    exit 64
  fi
fi

# 隊伍比較摘要三表（#287 S06 WP4b；PLAN r2 §7）：比照 ROSTER_ONLY 早退的獨立 insert-only 步驟。
# 比對／payload／對帳全在 cpbl.playoffs.team_comparison.sync（Python）；本段只做參數守衛、備份與 psql 管道。
#   ⛔ 不爬（必須 SKIP_SCRAPE=1）、不 build-features、不跑 migration（schema 只隨部署窗口）、不訓練、
#   ⛔ 不寫 refresh 標記、不同步其他表、⛔ 不進 sync_table 清單（三表有不可變觸發器）。
#   ⛔ build／列無 UPDATE／DELETE：同 build_id 內容不同一律 exit 70 拒絕、不重試；無變更時不備份、不寫入。
#   放在 ROSTER_ONLY 之前：兩個早退模式同時設定時由本段拒絕，不讓任一個被靜默略過。
# BACKUP_DIR 規則與 ROSTER_ONLY 相同（絕對路徑、realpath 不得等於每日鏈輪替目錄）。
team_comparison_sync() {  # $1=action（plan／apply）；本機唯讀、目標＝production
  uv run python -m cpbl.playoffs.team_comparison.sync "$1" \
    --local-psql "docker exec -i ${LOCAL_DB} psql -U cpbl -d cpbl" \
    --target-psql "ssh -o BatchMode=yes ${VPS} 'cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -U \"\$DB_USER\" -d \"\$DB_NAME\"'"
}
if [ -n "${TEAM_COMPARISON_ONLY:-}" ]; then
  if [ "$TEAM_COMPARISON_ONLY" != 1 ] || [ "${SKIP_SCRAPE:-}" != 1 ] || [ -n "${WITH_DETAIL:-}" ] \
     || [ -n "${LINEUP_ONLY:-}" ] || [ -n "${ROSTER_ONLY:-}" ] || [ -n "${POSTSEASON_RESULTS_ONLY:-}" ]; then
    echo 'FATAL: TEAM_COMPARISON_ONLY=1 必須搭配 SKIP_SCRAPE=1，且不得與 WITH_DETAIL／LINEUP_ONLY／ROSTER_ONLY／POSTSEASON_RESULTS_ONLY 併用' >&2
    exit 64
  fi
  if [ -z "${BACKUP_DIR:-}" ] || [ "${BACKUP_DIR#/}" = "$BACKUP_DIR" ]; then
    echo 'FATAL: TEAM_COMPARISON_ONLY 需明示獨立的 BACKUP_DIR（絕對路徑；不得與每日鏈共用輪替視窗）' >&2
    exit 64
  fi
  TC_BACKUP_DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$BACKUP_DIR")"
  TC_DAILY_BACKUP_DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' \
    "$HOME/Library/Application Support/cpbl-analytics/backups")"
  if [ -z "$TC_BACKUP_DIR" ] || [ "$TC_BACKUP_DIR" = "$TC_DAILY_BACKUP_DIR" ]; then
    echo 'FATAL: TEAM_COMPARISON_ONLY 的 BACKUP_DIR 與每日鏈備份目錄是同一個目錄（不得共用輪替視窗）' >&2
    exit 64
  fi
  cd "$REPO_DIR"
  echo '==> 隊伍比較摘要：唯讀比對本機與 production（insert-only）'
  # 非零（67／69／70／72）在 set -e 下原碼結束：拒絕不重試、不備份、不寫。
  TC_PLAN="$(team_comparison_sync plan)"
  echo "$TC_PLAN"
  case "$TC_PLAN" in
    *TEAM_COMPARISON_SYNC_PLAN=no-change*)
      echo '==> 隊伍比較摘要：無變更（未備份、未寫入）'
      exit 0
      ;;
    *TEAM_COMPARISON_SYNC_PLAN=insert-pending*) ;;
    *)
      echo 'FATAL: 隊伍比較摘要比對結果無法辨識，停止（不備份、不寫入）' >&2
      exit 67
      ;;
  esac
  echo '==> 隊伍比較摘要：獨立目錄備份 production（整庫）；驗證不過即中止'
  BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" BACKUP_DIR="$TC_BACKUP_DIR" \
    BACKUP_KEEP="${BACKUP_KEEP:-3}" "$REPO_DIR/scripts/backup-prod-db.sh")"
  echo "    ✓ 已驗證備份：${BACKUP_PATH}"
  echo '==> 隊伍比較摘要：單交易 insert-only 寫入＋事後對帳'
  team_comparison_sync apply
  echo '==> 隊伍比較摘要：完成（只代表摘要三表同步與對帳，不代表整鏈刷新）'
  exit 0
fi

# 有限公告同步在完整鏈之前退出，不碰 freshness／特徵／訓練。
# 季後 32 人名單三表（#284 S03；Q3 裁定 A＋T2 裁定 A）：比照 LINEUP_ONLY 早退的獨立 insert-only 步驟。
# 比對／payload／對帳全在 cpbl.rosters.sync（Python）；本段只做參數守衛、備份與 psql 管道。
#   ⛔ 不爬（必須 SKIP_SCRAPE=1）、不 build-features、不跑 migration（schema 只隨部署窗口）、不訓練、
#   ⛔ 不寫 refresh 標記、不同步其他表、⛔ 不進 sync_table 清單、⛔ 不在完整鏈與 scrape-daily.sh 呼叫。
#   ⛔ 無 UPDATE／DELETE：同 scope 內容不同一律 exit 70 拒絕、不重試；無變更時不備份、不寫入。
# BACKUP_DIR 必須明示且不得是每日鏈預設目錄（不輪替掉 10:10 的 7 份歷史深度）。
if [ -n "${ROSTER_ONLY:-}" ]; then
  if [ "$ROSTER_ONLY" != 1 ] || [ "${SKIP_SCRAPE:-}" != 1 ] || [ -n "${WITH_DETAIL:-}" ] \
     || [ -n "${LINEUP_ONLY:-}" ] || [ -n "${POSTSEASON_RESULTS_ONLY:-}" ]; then
    echo 'FATAL: ROSTER_ONLY=1 必須搭配 SKIP_SCRAPE=1，且不得與 WITH_DETAIL／LINEUP_ONLY／POSTSEASON_RESULTS_ONLY 併用' >&2
    exit 64
  fi
  if [ -n "${ROSTER_SCOPES:-}" ]; then
    IFS=, read -r -a ROSTER_SCOPE_VALUES <<< "$ROSTER_SCOPES"
    if [ "${#ROSTER_SCOPE_VALUES[@]}" != 2 ] \
       || [ "$ROSTER_SCOPES" != "${ROSTER_SCOPE_VALUES[0]},${ROSTER_SCOPE_VALUES[1]}" ] \
       || [ "${ROSTER_SCOPE_VALUES[0]}" = "${ROSTER_SCOPE_VALUES[1]}" ]; then
      echo 'FATAL: ROSTER_SCOPES 必須為兩個不同scope，以單一逗號分隔' >&2
      exit 64
    fi
    for ROSTER_SCOPE in "${ROSTER_SCOPE_VALUES[@]}"; do
      if [[ ! "$ROSTER_SCOPE" =~ ^(19|20)[0-9]{2}:[EC]:[A-Z0-9]{6}$ ]]; then
        echo 'FATAL: ROSTER_SCOPES 格式須為 YEAR:E或C:TEAM，不能含空白或額外字元' >&2
        exit 64
      fi
    done
  fi
  # 比的是「實際目錄」不是字串（#284 R1 F1）：尾端 /、/.、..、symlink 都可能指回每日鏈目錄，
  # 而 backup-prod-db.sh 會在該目錄輪替刪檔。故只收絕對路徑，雙方以 realpath 正規化後比較，
  # 並把正規化後的同一個值交給備份腳本（檢查的與使用的是同一個目錄）。
  if [ -z "${BACKUP_DIR:-}" ] || [ "${BACKUP_DIR#/}" = "$BACKUP_DIR" ]; then
    echo 'FATAL: ROSTER_ONLY 需明示獨立的 BACKUP_DIR（絕對路徑；不得與每日鏈共用輪替視窗）' >&2
    exit 64
  fi
  ROSTER_BACKUP_DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$BACKUP_DIR")"
  ROSTER_DAILY_BACKUP_DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' \
    "$HOME/Library/Application Support/cpbl-analytics/backups")"
  if [ -z "$ROSTER_BACKUP_DIR" ] || [ "$ROSTER_BACKUP_DIR" = "$ROSTER_DAILY_BACKUP_DIR" ]; then
    echo 'FATAL: ROSTER_ONLY 的 BACKUP_DIR 與每日鏈備份目錄是同一個目錄（不得共用輪替視窗）' >&2
    exit 64
  fi
  cd "$REPO_DIR"
  ROSTER_LOCAL_PSQL="docker exec -i ${LOCAL_DB} psql -U cpbl -d cpbl"
  ROSTER_TARGET_PSQL="ssh -o BatchMode=yes ${VPS} 'cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -U \"\$DB_USER\" -d \"\$DB_NAME\"'"
  # Bash 3.2 的 nounset 不能直接展開空陣列；從非空基本參數建立同一命令向量。
  ROSTER_SYNC_ARGS=(--local-psql "$ROSTER_LOCAL_PSQL" --target-psql "$ROSTER_TARGET_PSQL")
  if [ -n "${ROSTER_SCOPES:-}" ]; then
    for ROSTER_SCOPE in "${ROSTER_SCOPE_VALUES[@]}"; do
      ROSTER_SYNC_ARGS+=(--scope "$ROSTER_SCOPE")
    done
  fi
  echo '==> 名單三表：唯讀比對本機與 production（insert-only）'
  # 非零（67／69／70／72）在 set -e 下原碼結束：拒絕不重試、不備份、不寫。
  ROSTER_PLAN="$(uv run python -m cpbl.rosters.sync plan \
    "${ROSTER_SYNC_ARGS[@]}")"
  echo "$ROSTER_PLAN"
  case "$ROSTER_PLAN" in
    *ROSTER_SYNC_PLAN=no-change*)
      echo '==> 名單三表：無變更（未備份、未寫入）'
      exit 0
      ;;
    *ROSTER_SYNC_PLAN=insert-pending*) ;;
    *)
      echo 'FATAL: 名單比對結果無法辨識，停止（不備份、不寫入）' >&2
      exit 67
      ;;
  esac
  echo '==> 名單三表：獨立目錄備份 production（整庫）；驗證不過即中止'
  BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" BACKUP_DIR="$ROSTER_BACKUP_DIR" \
    BACKUP_KEEP="${BACKUP_KEEP:-3}" "$REPO_DIR/scripts/backup-prod-db.sh")"
  echo "    ✓ 已驗證備份：${BACKUP_PATH}"
  echo '==> 名單三表：單交易 insert-only 寫入＋事後對帳'
  uv run python -m cpbl.rosters.sync apply \
    "${ROSTER_SYNC_ARGS[@]}"
  echo '==> 名單三表：完成（只代表名單三表同步與對帳，不代表整鏈刷新）'
  exit 0
fi

if [ -n "${LINEUP_ONLY:-}" ]; then
  if [ "$LINEUP_ONLY" != 1 ] || [ "${SKIP_SCRAPE:-}" != 1 ]; then
    echo 'FATAL: LINEUP_ONLY=1 必須搭配 SKIP_SCRAPE=1' >&2
    exit 64
  fi
  prepare_lineup_copy
  echo '==> 有限公告：驗證備份、schema、單表自然鍵同步'
  BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" "$REPO_DIR/scripts/backup-prod-db.sh")"
  echo "    ✓ 已驗證備份：${BACKUP_PATH}"
  ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api python -c "
from cpbl import db
try:
    print(\"migrated:\", db.migrate())
finally:
    if db._pool is not None:
        db._pool.close()
    print(\"migration pool closed\")"'
  sync_lineup_announcements
  exit 0
fi

# 非破壞性同步一張表（bash 3.2 相容，不用關聯陣列）：$1=表 $2=conflict鍵 其餘=upsert欄位
sync_table() {
  local t="$1" pk="$2"; shift 2
  # ⛔ 欄位清單漂移守衛（2026-09-23）。下面的 upsert 是 `ON CONFLICT DO UPDATE SET <清單>`：
  # 清單外的欄在生產端「只插不更」——新列帶上、既有列永遠停在首次插入值，而同步照樣
  # exit 0、freshness 照樣通過。pitch_tracking 曾因 migration 加欄後沒人補清單漏了 19 欄
  # （本機重跑球種推算、生產仍是 NULL）。故寫入前比對本機 schema：本機有、清單（PK＋
  # 更新欄）沒有的欄 → 大聲失敗、不送任何資料。
  # 查不到欄位（表名打錯／連不上本機 DB）時此處不判：緊接著的 pg_dump 會以非零結束，
  # 在 `set -euo pipefail` 下整條同步中止（2026-09-23 以 bash 3.2.57 實測）。
  local allowed missing
  allowed="$(printf '%s\n' ${pk//,/ } "$@")"
  missing="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -Atc \
      "SELECT column_name FROM information_schema.columns WHERE table_schema='cpbl' AND table_name='${t}' ORDER BY ordinal_position" \
    | grep -vxF -f <(printf '%s\n' "$allowed") || true)"
  if [ -n "$missing" ]; then
    echo "⛔ sync_table ${t}：本機有欄位不在同步清單（生產會只插不更）：$(echo $missing)" >&2
    echo "   補進本檔該表的 sync_table 清單後再跑。" >&2
    return 1
  fi
  local set_clause="" tgt_row="" new_row=""
  local c
  for c in "$@"; do
    set_clause="${set_clause}${c}=EXCLUDED.${c},"
    tgt_row="${tgt_row}tgt.${c},"
    new_row="${new_row}EXCLUDED.${c},"
  done
  set_clause="${set_clause%,}"
  # 只改真的變了的列（2026-09-24）。原本每次同步把送過去的每一列都 UPDATE 一次——
  # 每次約 2,177,577 列（game_livelog 全史 1,392,649 列），生產端 game_livelog 累計
  # n_tup_upd 86,791,479 對 n_tup_ins 68,228、HOT 只佔 7%：幾乎全是「值沒變的重寫」，
  # 每一列都留下 dead tuple、改寫索引、產生 WAL，再觸發 autovacuum，在 1 vCPU／950MB 的
  # VPS 上直接變成大量換頁（見 fetch_api_info 的說明）。
  # 比較範圍＝SET 的欄（PK 由 ON CONFLICT 對齊），與 SET 同一份清單產生，不會各自漂移。
  # IS DISTINCT FROM 把 NULL 對 NULL 視為相同。⛔ 前提：同步表不可有沒有等號運算子的型別
  # （json、幾何型別）——2026-09-24 查過 45 張同步表皆無；新增這類欄位前先改用 jsonb。
  # 最終資料與改前相同（沒變的列本來就是寫回同值），只是不再產生無效寫入。
  if [ -n "${SYNC_SCOPE_KEYS_SQL:-}" ]; then
    _sync_table_scoped "$t" "$pk" "$set_clause" "${tgt_row%,}" "${new_row%,}"
    return
  fi
  {
    echo "CREATE TEMP TABLE _stg (LIKE cpbl.${t} INCLUDING DEFAULTS) ON COMMIT DROP;"
    docker exec "$LOCAL_DB" pg_dump -U cpbl -d cpbl --data-only -t "cpbl.${t}" \
      | sed -e "s/^COPY cpbl\.${t} /COPY _stg /" -e '/^\\restrict /d' -e '/^\\unrestrict /d'
    echo "INSERT INTO cpbl.${t} AS tgt SELECT * FROM _stg ON CONFLICT (${pk}) DO UPDATE SET ${set_clause}" \
      "WHERE ROW(${tgt_row%,}) IS DISTINCT FROM ROW(${new_row%,});"
  } | ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
          -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\""
  echo "    ✓ ${t}"
}

# sync_table 的目標場鍵版本（#293 S12；只由 POSTSEASON_BOXPA_ONLY 設定 SYNC_SCOPE_KEYS_SQL 時走這裡）。
# 與上面同一份 SET／比較清單（由 sync_table 產生後傳入），差別只有三處：
#   1) 資料來源是 `COPY (SELECT * … WHERE <目標鍵>) TO STDOUT`，不是整表 pg_dump（沒有 setval）；
#   2) payload 先落地成檔、斷言只含一個 COPY＋一個 INSERT 且無 DELETE／TRUNCATE／CASCADE 才送出；
#   3) ssh 連線失敗（rc 255）回專屬的 72（暫時性，晚間鏈可重送一次），其他非零照原碼結束。
# 與每日鏈一樣只 upsert、不 DELETE：本機少了的列 production 會留著（同 sync_table 語意）。
_sync_table_scoped() {  # $1=表 $2=PK $3=SET 子句 $4=tgt 列 $5=new 列
  local t="$1" pk="$2" set_clause="$3" tgt_row="$4" new_row="$5" payload rc
  payload="$(mktemp "${TMPDIR:-/tmp}/cpbl-boxpa-${t}.XXXXXX")"
  {
    echo "CREATE TEMP TABLE _stg (LIKE cpbl.${t} INCLUDING DEFAULTS) ON COMMIT DROP;"
    echo "COPY _stg FROM stdin;"
    printf '%s\n' "\\set QUIET on" "\\set ON_ERROR_STOP on" \
      "COPY (SELECT * FROM cpbl.${t} WHERE ${SYNC_SCOPE_KEYS_SQL}) TO STDOUT;" \
      | docker exec -i "$LOCAL_DB" psql -U cpbl -d cpbl -X
    echo '\.'
    echo "INSERT INTO cpbl.${t} AS tgt SELECT * FROM _stg ON CONFLICT (${pk}) DO UPDATE SET ${set_clause}" \
      "WHERE ROW(${tgt_row}) IS DISTINCT FROM ROW(${new_row});"
  } > "$payload"
  # 只檢 COPY 資料段以外的行（資料內容可能含任意文字）；形狀必須恰為 1 個 COPY 段＋1 個 INSERT。
  local why
  why="$(awk '
    in_copy { if ($0 == "\\.") in_copy = 0; next }
    $0 == "COPY _stg FROM stdin;" { copies++; in_copy = 1; next }
    /^INSERT INTO / { inserts++ }
    toupper($0) ~ /^(DELETE|TRUNCATE|DROP|ALTER)([^A-Z_]|$)|(^|[^A-Z_])(CASCADE|SETVAL)([^A-Z_]|$)/ { print "禁止語句：" substr($0, 1, 80) }
    END { if (copies != 1 || inserts != 1 || in_copy) print "形狀不符：COPY=" copies+0 " INSERT=" inserts+0 " 未結束=" in_copy+0 }
  ' "$payload")"
  if [ -n "$why" ]; then
    echo "FATAL: ${t} 的目標場 payload 未通過送出前守衛（未送出；payload 保留於 ${payload}）：${why}" >&2
    exit 67
  fi
  rc=0
  ssh -o BatchMode=yes "$VPS" \
      "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
        -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\"" < "$payload" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "FATAL: ${t} 目標場 upsert 失敗 rc=${rc}" >&2
    [ "$rc" -eq 255 ] && exit 72
    exit "$rc"
  fi
  rm -f "$payload"
  echo "    ✓ ${t}（目標場）"
}

# box 七表的欄位清單（完整鏈 WITH_DETAIL 與 #293 POSTSEASON_BOXPA_ONLY 共用**同一份**；各寫一份會漂，
# sync_table 的「只插不更」教訓見其註解）。完整鏈照原順序逐一呼叫；目標場模式由 sync_box_tables 依序呼叫。
sync_box_game_detail() {
  sync_table game_detail "year,kind_code,game_sno" \
    attendance game_time head_umpire first_umpire second_umpire third_umpire left_umpire right_umpire \
    weather_code weather_desc winning_type attendance_backend updated_at
}
sync_box_game_scoreboard() {
  sync_table game_scoreboard "year,kind_code,game_sno,team_no,inning_seq" \
    visiting_home_type team_name score_cnt hitting_cnt error_cnt
}
sync_box_game_livelog() {
  sync_table game_livelog "year,kind_code,game_sno,main_event_no" \
    inning_seq visiting_home_type batting_order out_cnt ball_cnt strike_cnt pitch_cnt content \
    action_name batting_action_name defend_station_code hitter_acnt hitter_name pitcher_acnt \
    pitcher_name catcher_acnt catcher_name first_base second_base third_base is_strike is_ball \
    is_score is_change_player is_special_event visiting_score home_score
}
sync_box_pitch_tracking() {
  sync_table pitch_tracking "year,kind_code,game_sno,pitcher_acnt,pitch_cnt" \
    pitcher_name hitter_acnt hitter_name inning_seq ball_cnt strike_cnt out_cnt batting_order content \
    pitch_call auto_pitch_type tagged_pitch_type rel_speed spin_rate rel_side rel_height extension \
    zone_speed plate_loc_side plate_loc_height hit_exit_speed hit_launch_angle hit_direction \
    hit_distance hit_hang_time \
    traj_accel_y traj_accel_z zone_time ivb_cm hb_cm pitch_type_pred pitch_type_pred_v2 \
    hit_landing_bearing hit_landing_confidence hit_spin_rate \
    traj_x0 traj_x1 traj_x2 traj_y0 traj_y1 traj_y2 traj_z0 traj_z1 traj_z2
}
sync_box_pitching_game_flags() {
  sync_table pitching_game_flags "year,kind_code,game_sno,pitcher_acnt" \
    is_save_ok is_save_fail role_type relief_point source_fetched_at
}
sync_box_batting_gamelog() {
  sync_table batting_gamelog "year,kind_code,game_sno,hitter_acnt" \
    hitter_name visiting_home_type uniform_no role_type plate_appearances at_bats hits rbi runs \
    singles doubles triples home_runs grand_slam total_bases gidp sac_hit sac_fly bb ibb hbp so sb cs \
    lob errors gw_rbi is_mvp
}
sync_box_pitching_gamelog() {
  sync_table pitching_gamelog "year,kind_code,game_sno,pitcher_acnt" \
    pitcher_name visiting_home_type uniform_no role_type game_result is_complete_game is_shutout \
    inning_pitched_cnt inning_pitched_div3 plate_appearances pitch_cnt strike_cnt ball_cnt hits \
    home_runs sac_hit sac_fly bb ibb hbp so wild_pitch balk runs earned_runs relief_point max_speed is_mvp
}
sync_box_tables() {
  sync_box_game_detail
  sync_box_game_scoreboard
  sync_box_game_livelog
  sync_box_pitch_tracking
  sync_box_pitching_game_flags
  sync_box_batting_gamelog
  sync_box_pitching_gamelog
}

# 進階快照 5 表原子同步（INGEST-ADV-RECONCILE1 後的父子表 + read gating）。
# 為何不能用通用 sync_table：
#   1) advanced_ingest_runs.id 是 GENERATED ALWAYS → INSERT 明確 id 需 OVERRIDING SYSTEM VALUE。
#   2) advanced_stats/pitch_type/league_summary 有 source_run_id → advanced_ingest_runs FK，
#      父表沒先灌就 upsert 子表會 FK 失敗（EXIT 3）。
#   3) 可見性由 gating（source_run_id = snapshot_state.current_run_id）決定；舊 sync_table
#      的 DO UPDATE 未更新 metrics/source_run_id，既有列會被 gating 濾掉。
# 故五表在同一 --single-transaction：先灌 runs、再更新資料列的 source_run_id、最後翻 pointer；
# 全有全無、無可見空窗。本機↔prod 的 run id 語意已對齊（id 6–20 逐列相同），無 serial-PK 碰撞。
_stage() {  # $1=來源表  $2=暫存表名
  echo "CREATE TEMP TABLE $2 (LIKE cpbl.$1 INCLUDING DEFAULTS) ON COMMIT DROP;"
  docker exec "$LOCAL_DB" pg_dump -U cpbl -d cpbl --data-only -t "cpbl.$1" \
    | sed -e "s/^COPY cpbl\.$1 /COPY $2 /" -e '/^\\restrict /d' -e '/^\\unrestrict /d'
}
_excl() { local s="" c; for c in "$@"; do s="${s}${c}=EXCLUDED.${c},"; done; printf '%s' "${s%,}"; }

sync_advanced_snapshot() {
  {
    _stage advanced_ingest_runs _adv_run
    # run log 不可變（append-only）：既有 run 略過、只補新 run；identity 欄需 OVERRIDING SYSTEM VALUE。
    echo "INSERT INTO cpbl.advanced_ingest_runs OVERRIDING SYSTEM VALUE SELECT * FROM _adv_run ON CONFLICT (id) DO NOTHING;"
    _stage advanced_stats _adv_stat
    echo "INSERT INTO cpbl.advanced_stats SELECT * FROM _adv_stat ON CONFLICT (year,kind_code,acnt,role) DO UPDATE SET $(_excl pa woba woba_pr ba ba_pr slg slg_pr iso iso_pr obp obp_pr brl brl_pr brlp brlp_pr ev ev_pr max_ev max_ev_pr hardhitp hardhitp_pr kp kp_pr bbp bbp_pr whiffp whiffp_pr chasep chasep_pr updated_at metrics source_run_id source_fetched_at last_seen_at);"
    _stage advanced_pitch_type_stats _adv_pt
    echo "INSERT INTO cpbl.advanced_pitch_type_stats SELECT * FROM _adv_pt ON CONFLICT (year,kind_code,role,acnt,pitch_type) DO UPDATE SET $(_excl pitches kph kph_max spin_rate spin_rate_max throws source_run_id source_fetched_at last_seen_at source_payload updated_at);"
    _stage advanced_league_summary _adv_ls
    echo "INSERT INTO cpbl.advanced_league_summary SELECT * FROM _adv_ls ON CONFLICT (year,kind_code,category,pitch_type) DO UPDATE SET $(_excl metrics source_run_id source_fetched_at last_seen_at source_payload updated_at);"
    # pointer 最後翻：此時資料列已帶新 source_run_id，gating 立即命中，無可見空窗。
    # current_run_scope 是 GENERATED ALWAYS（'full'）→ 明確列出欄位、排除它（不可 INSERT / SET）。
    _stage advanced_snapshot_state _adv_snap
    echo "INSERT INTO cpbl.advanced_snapshot_state (year,kind_code,dataset,role,current_run_id,row_count,source_fetched_at,promoted_at) SELECT year,kind_code,dataset,role,current_run_id,row_count,source_fetched_at,promoted_at FROM _adv_snap ON CONFLICT (year,kind_code,dataset,role) DO UPDATE SET $(_excl current_run_id row_count source_fetched_at promoted_at);"
  } | ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
          -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\""
  echo "    ✓ advanced snapshot（runs/stats/pitch_type/league_summary/pointer 原子晉升）"
}

# canonical PA build 家族同步（INGEST-PA-DAILY1；migrations/066_game_recap_pa_expand.sql；
# FIX1／Issue #88 改成 TRUNCATE＋全量重灌；#353 WP1 再改成逐場增量替換＋事後全族對帳）。
# 為何不能用通用 sync_table：
#   1) game_recap_source_revisions/game_plate_appearances/game_pa_events/game_pa_pitch_mappings
#      四表 PK 皆 GENERATED ALWAYS AS IDENTITY 代理鍵，INSERT 帶入本機既有值需
#      OVERRIDING SYSTEM VALUE（同 advanced_ingest_runs 前例）；game_recap_builds 的
#      build_id 是 builder 產生的 uuid（非 identity），走一般 INSERT 即可。
#   2) 四表彼此 FK 相依（source_revisions ← builds ← plate_appearances ← pa_events／
#      pitch_mappings；source_revisions 同時被 pitch_mappings 直接參照），寫入必須在同一
#      --single-transaction 內「子→父 DELETE、父→子 INSERT」，否則 FK 失敗。
#
# 不變量（FIX1 起至今不變）：id 值直接鏡像本機、不重新分配。cpbl-refresh-recent 只在本機跑，
# prod 從不獨立寫入這五張表（唯一 writer 是本同步腳本與晚間鏈同形狀的目標場替換），故無 prod
# 自產 identity 與匯入值碰撞風險，與 advanced_ingest_runs「本機↔prod run id 語意已對齊」同一理由。
# payload 不含 setval（prod 對這五表從不自行配號，序列值從不被讀取）。
#
# ⛔ 不得改回以 id 當衝突鍵的 ON CONFLICT upsert（FIX1 根因）：2026-08-03 一次 ad-hoc 手動同步在
# prod 留下「內容相同、id 不同」的 game_recap_source_revisions 舊列；ON CONFLICT (id) 對不到它們、
# 退回一般 INSERT 又撞上 (year,kind_code,game_sno,source_kind,source_sha256) 內容唯一鍵，整個交易
# 回滾。現行做法的衝突處理單位是「場」不是 id：被替換的場先刪掉該場**全部**列再插入，所以那類殘留
# 只要所在的場被替換就一併清掉。
#
# 為何不再 TRUNCATE（#353，研究 2 正式站實測）：TRUNCATE 取 ACCESS EXCLUSIVE、一路持有到 commit，
# 正式站每天約 7 分 20 秒；期間讀 PA 表的 API 請求全部排隊，連線池 8 條被占滿，連 /api/info 都等不到
# 連線（每日鏈期間正式站無回應的主因）。DELETE 只取 ROW EXCLUSIVE，讀者走 MVCC 看到交易前快照。
#
# 現行流程（cpbl.ingest.pa_incremental，與晚間鏈 boxpa_sync 同一個 payload 產生器與守衛）：
#   1) 本機與 prod 各算每場簽章（builds 全列含 state ＋ source_revisions id 集合）；差異場＝簽章不同
#      ∪ 只在一邊。0 場不送。差異場超過上限＝簽章失準，拒絕（67），⛔ 不自動降級成全量。
#   2) 只對差異場送單交易 payload：交易內 lock／statement timeout、prod 端 FK 閉包守衛、子→父 DELETE
#      目標鍵、父→子 OVERRIDING SYSTEM VALUE 插入、寫入後列數自檢；送出前逐行斷言無 TRUNCATE／
#      CASCADE／setval 且 DELETE 只限目標鍵（payload 先落地成檔再斷言，不是管線過濾器）。
#   3) 全族對帳：五表總列數＋各表 max(identity)＋published build 集合，本機與 prod 必須相等；
#      不等 ⇒ 68，整條鏈停在這裡（fail-closed），交需求方決定是否授權全量模式。
#   全量模式 PA_FULL_RESYNC=1：同一產生器、scope＝全部場（WHERE TRUE），不 TRUNCATE、讀者不被擋，
#   但寫入量與 WAL 約為 TRUNCATE 的 1.5 倍、表暫時膨脹約 2 倍（規劃 r2 P1），只能人工指定；每日鏈
#   （帶 DAILY_DAY_TYPE）一律拒絕。跑完建議 VACUUM (ANALYZE) 五表（不取強鎖）。
#
# 刪除的連帶效果：FK 的 ON DELETE CASCADE 因子表先刪而無列可波及；FK 閉包守衛在交易內先擋下任何跨場
# 參照（DELETE 目標場會讓別場列失去參照的情形）。已 grep 全部 migrations：除這 5 表彼此互相參照外，
# 沒有其他表對它們建 FK（INGEST-PA-DAILY1-FIX1 驗證留痕）。
sync_pa_build() {
  local payload rc mode="增量" full_args=() local_psql target_psql
  if [ "${PA_FULL_RESYNC:-0}" = 1 ]; then
    mode="全量（PA_FULL_RESYNC=1，人工指定）"
    full_args=(--full)
  fi
  local_psql="docker exec -i ${LOCAL_DB} psql -X -U cpbl -d cpbl"
  target_psql="ssh -o BatchMode=yes ${VPS} 'cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -X -U \"\$DB_USER\" -d \"\$DB_NAME\"'"
  echo "    ⓘ PA 同步開始 $(date '+%F %T')（${mode}）"
  payload="$(mktemp "${TMPDIR:-/tmp}/cpbl-pa-sync.XXXXXX")"
  # 非零（67 守衛不過／72 ssh／74 prod psql）在 set -e 下原碼結束：未送出任何寫入。
  uv run python -m cpbl.ingest.pa_incremental payload --local-psql "$local_psql" \
    --target-psql "$target_psql" --out "$payload" ${full_args[@]+"${full_args[@]}"}
  if [ -s "$payload" ]; then
    rc=0
    ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
          -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\"" \
        < "$payload" || rc=$?
    if [ "$rc" -ne 0 ]; then
      echo "FATAL: PA 五表替換失敗 rc=${rc}（單交易已回滾；payload 保留於 ${payload}）" >&2
      [ "$rc" -eq 255 ] && exit 72
      exit 74
    fi
  else
    echo "    · PA：本機與 production 每場簽章相同，沒有要替換的場（未送）"
  fi
  rm -f "$payload"
  rc=0
  uv run python -m cpbl.ingest.pa_incremental reconcile --local-psql "$local_psql" \
    --target-psql "$target_psql" || rc=$?
  echo "    ⓘ PA 同步結束 $(date '+%F %T')"
  if [ "$rc" -ne 0 ]; then
    echo "FATAL: PA 五表全族對帳未通過 rc=${rc}（已寫入的場保留；見上方 PA_RECONCILE）。" >&2
    echo "       ⛔ 不自動重跑；交需求方決定是否授權 PA_FULL_RESYNC=1（規劃 r2 D5）。" >&2
    exit "$rc"
  fi
  echo "    ✓ canonical PA build（${mode}：逐場替換＋全族對帳相等）"
}

# 官方狀態觀測軌跡兩表（`game_schedule_status_revisions`／`game_source_revisions`）。
#
# 為何不能用通用 sync_table：兩表的 PK 是 GENERATED ALWAYS identity `id`，而 sync_table
# 的 `SELECT *` 會把本機 id 一起帶過去（identity 欄需 OVERRIDING SYSTEM VALUE，否則直接
# 報錯）；就算補上該關鍵字，id 在本機與 prod 各自獨立編號，拿 id 當衝突鍵等於用一個
# 兩機不共通的值判「是不是同一列」——那正是 game_recap_source_revisions 事故的根因
# （見 sync_pa_build 上方註解）。故這裡**不搬 id**：以顯式欄位清單插入、讓 prod 自己
# 配號，衝突鍵改用各表真正的內容唯一鍵（migration 061 的 UNIQUE CONSTRAINT）。
#
# 為何也不比照 #353 之前的 sync_pa_build 用 TRUNCATE 全量重灌：那五表是可由 livelog 重算的 derived
# 產物，這兩表是「我們在哪個時點觀測到官網說什麼」的軌跡本身（fetched_at 首見、
# last_seen_at 末見、seen_count 觀測次數），且沒有 FK 網要求原子重建。增量 upsert 足夠，
# 不必每天把 prod 的軌跡列整批重寫。
#
# prod 端無獨立 writer：唯二寫入者是 `record_schedule_revisions`／`record_source_revision`，
# 呼叫點全在 ingest（cpbl_site／cpbl_gamelog／run_refresh_recent），而爬蟲只能本機跑
# （VPS IP 被官網擋），故本機值為權威、可整欄鏡像。
#
# 曾被判為「無害」而實際炸掉生產的副作用（OPS-PROD-SYNC-SEQ-COLLISION1，2026-08-14 修）：
# `_stage` 的 `pg_dump --data-only -t` 會一併輸出該表 identity 序列的 `setval`，那一行落在
# **目標端真實序列**上（不是暫存表），且位置在本函式 echo 的 `INSERT` **之前**。因為
# `INSERT` 刻意不帶 id、由 prod 自行配號，prod 每次同步都從「**本機序列的 `last_value`**」
# 開始配號（不是本機 `max(id)`——兩者會差，混淆這點正是本事故的共同認知根源），而
# **prod 既有 id 的上界與本機 `last_value` 之間沒有任何約束關係**。當
# `prod_max > local_last_value`，本次要配出的 id 區間與 prod 既有 id 重疊，重疊寬度
# `prod_max − local_last_value` 即下方遙測印的「地雷區」；批次內每一列都消耗一個 `nextval`
# （含走 `ON CONFLICT DO UPDATE` 的列），但只有真插入的列會實際寫入 id，故失敗條件是
# 「某列真插入，且其落點落在地雷區內」，而落點是 `pg_dump` 的 heap 順序、每日重排 ≈ 隨機。
# 2026-08-14 10:22 即以此撞上 `id=18138`，生產資料自 08-13 起停止更新。
#
# **舊註解的前提為真、推論是 non sequitur**：「prod 對這兩表從不自行 INSERT」查核成立
# （無 cron／timer，API 唯讀，爬蟲在 VPS 被官網 IP 擋），但 prod **每天都在配 id**，配號者
# 就是本函式自己的 INSERT。「沒有其他 writer」與「沒有 id 配發」被當成同一件事，而後者
# 在寫下註解的當下就已經是假的。
#
# **舊自測的盲區是這個缺陷唯一的逃逸路徑，寫在這裡以免重犯**：那次自測驗的是**首灌**
# （scratch 端表為空 → 全部列都是新的 → id 連續無間隙 → 構造上不可能撞）。缺的那一格是
# 「**第二次執行，且期間有新列**」。生產完整複製了這個形狀：08-13 首灌成功、08-14 第二次
# 即炸。日後若有人把第三張同型表（`box_pitching_revisions`，prod 目前 0 列）接上本函式，
# 一樣是第一次必然成功、第二次才炸——連「成功的首次測試誤導作者」都一樣。故下面的不變量
# 寫在函式內、對任何 `$1` 都成立，不逐表打補丁。
#
# 修法四件套，作用域**只限本函式**：
#   1. `_stage_noseq`（非 `_stage`）以 `--exclude-table-data` 排除序列資料 → payload 不再
#      產生任何 `setval`。序列名以 `pg_get_serial_sequence()` 查得、不寫死 pattern；查不到
#      即整條停下。註：`-T`／`--exclude-table` 對此**無效**（實測仍輸出 setval）。
#   2. 自備一行**矯正 `setval`**，位置在暫存之後、`INSERT` 之前，設到 **prod 自己的
#      `max(id)`**（在 prod 端即時算，不靠本機讀值）→ 之後配出的 id 構造上必然高於所有
#      既有 id，地雷區恆為 0。這是構造保證不是機率論證，且序列不隨交易回滾，故即使該次
#      同步失敗也留下修好的序列（無需任何人工 prod 寫入即可自癒）。
#   3. `_assert_revision_payload` fail-closed 守衛：payload **先落地成檔、斷言通過才送出**。
#      不可改寫成管線過濾器——`set -o pipefail` 雖會讓整條回非 0，但那時資料早已流進 ssh、
#      抵達生產，守衛等於沒有。找不到預期形狀（無 `INSERT`／無 COPY 終止符）一律判紅，
#      不接受「沒找到所以沒問題」。
#   4. 每表印一行不變量遙測：`zone_before` 就是舊碼當天會踩到的地雷區大小，讓綠燈自帶
#      差分證據（`zone_before=0` 的那天只是僥倖日，不構成修法有效的證據）。
#
# `sync_advanced_snapshot`／`mirror_table` 續用 `_stage`、**不得**改用 `_stage_noseq`：
# 它們以 `OVERRIDING SYSTEM VALUE` 明確鏡像本機 id，dump 的 setval 在那裡是**對的**。
# `sync_pa_build` 自 #353 起不再經 `_stage`：payload 由 cpbl.ingest.pa_incremental 以
# `COPY (SELECT …) TO STDOUT` 產生，本來就沒有 setval（且送出前斷言不得出現）。

# `sync_revision_table` 專用暫存：與 `_stage` 同形，但排除該表 identity 序列的資料。
_stage_noseq() {  # $1=來源表  $2=暫存表名  $3=該表 id 欄的序列名
  echo "CREATE TEMP TABLE $2 (LIKE cpbl.$1 INCLUDING DEFAULTS) ON COMMIT DROP;"
  docker exec "$LOCAL_DB" pg_dump -U cpbl -d cpbl --data-only -t "cpbl.$1" \
      --exclude-table-data "$3" \
    | sed -e "s/^COPY cpbl\.$1 /COPY $2 /" -e '/^\\restrict /d' -e '/^\\unrestrict /d'
}

_serial_sequence() {  # $1=表；印出 id 欄的序列名，查不到回非 0（呼叫端 fail-closed）
  local seq
  seq="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -At -c \
    "SELECT pg_get_serial_sequence('cpbl.$1', 'id')")"
  [ -n "$seq" ] || return 1
  printf '%s\n' "$seq"
}

# 送出前守衛。四條斷言任一不成立即回非 0，payload 刻意保留供人檢視、且未送出。
_assert_revision_payload() {  # $1=payload 檔  $2=表
  local f="$1" t="$2" why=""
  local n_setval n_native ln_setval ln_copy_end ln_insert
  n_setval="$(grep -c 'setval' "$f" || true)"
  n_native="$(grep -c 'pg_catalog\.setval' "$f" || true)"
  ln_setval="$(grep -n 'setval' "$f" | head -1 | cut -d: -f1 || true)"
  ln_copy_end="$(grep -Fxn '\.' "$f" | tail -1 | cut -d: -f1 || true)"
  ln_insert="$(grep -n "^INSERT INTO cpbl\.${t} " "$f" | head -1 | cut -d: -f1 || true)"

  if [ "$n_setval" -ne 1 ]; then
    why="setval 行數為 ${n_setval}，應恰好 1（本函式自備的矯正 setval）"
  elif [ "$n_native" -ne 0 ]; then
    why="出現 ${n_native} 行 pg_dump 原生 setval（pg_catalog.setval）——排除序列資料已失效"
  elif ! sed -n "${ln_setval}p" "$f" | grep -q 'pg_get_serial_sequence'; then
    why="第 ${ln_setval} 行的 setval 不是矯正形式（缺 pg_get_serial_sequence）"
  elif [ -z "$ln_insert" ]; then
    why="找不到 'INSERT INTO cpbl.${t} '，payload 形狀不符（fail-closed，不接受「沒找到所以沒問題」）"
  elif [ -z "$ln_copy_end" ]; then
    why="找不到 COPY 終止符，payload 形狀不符（fail-closed）"
  elif [ "$ln_copy_end" -ge "$ln_setval" ] || [ "$ln_setval" -ge "$ln_insert" ]; then
    why="矯正 setval 位置錯誤：COPY 終止 ${ln_copy_end} / setval ${ln_setval} / INSERT ${ln_insert}（須嚴格遞增）"
  fi

  if [ -n "$why" ]; then
    echo "FATAL: ${t} 的同步 payload 未通過送出前守衛：${why}" >&2
    echo "       payload 保留於 ${f}（未送出，生產未被觸碰）" >&2
    return 1
  fi
  return 0
}

# 不變量遙測。prod_max 另下一次唯讀查詢取得（payload 內的矯正 setval 走 prod 端即時
# 計算、不吃這個值），本機 last_value 亦然——那正是「舊碼會 setval 到多少」。
_revision_telemetry() {  # $1=表  $2=本機序列名
  local t="$1" seq="$2" old_seq prod_max zone_before corrected zone_after
  old_seq="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -At -c "SELECT last_value FROM ${seq}")"
  prod_max="$(ssh -n -o BatchMode=yes "$VPS" \
    "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec prod_pg psql -Atq \
      -U \"\$DB_USER\" -d \"\$DB_NAME\" -c 'SELECT COALESCE(max(id), 0) FROM cpbl.${t}'")"
  if ! [[ "$old_seq" =~ ^[0-9]+$ ]] || ! [[ "$prod_max" =~ ^[0-9]+$ ]]; then
    echo "FATAL: ${t} 不變量遙測取值失敗（old_seq='${old_seq}' prod_max='${prod_max}'）" >&2
    return 1
  fi
  zone_before=$(( prod_max > old_seq ? prod_max - old_seq : 0 ))
  corrected=$(( prod_max > 0 ? prod_max : 1 ))
  zone_after=$(( prod_max > corrected ? prod_max - corrected : 0 ))
  printf '    ⓘ %s : old_seq=%s  prod_max=%s  zone_before=%s  →  corrected=%s  zone_after=%s\n' \
    "$t" "$old_seq" "$prod_max" "$zone_before" "$corrected" "$zone_after"
}

sync_revision_table() {  # $1=表 $2=內容唯一鍵 其餘=欄位（**不含** identity 欄 id）
  local t="$1" pk="$2"; shift 2
  local cols; cols="$(printf '%s,' "$@")"; cols="${cols%,}"
  local seq payload
  if ! seq="$(_serial_sequence "$t")"; then
    echo "FATAL: 取不到 cpbl.${t} 的 id 序列名（表結構已變？）——拒絕以可能含 setval 的 payload 同步生產" >&2
    exit 66
  fi
  payload="$(mktemp "${TMPDIR:-/tmp}/cpbl-rev-${t}.XXXXXX")"
  {
    _stage_noseq "$t" _rev_stg "$seq"
    echo "SELECT setval(pg_get_serial_sequence('cpbl.${t}', 'id'), \
GREATEST(COALESCE((SELECT max(id) FROM cpbl.${t}), 0), 1), \
(SELECT count(*) FROM cpbl.${t}) > 0);"
    echo "INSERT INTO cpbl.${t} (${cols}) SELECT ${cols} FROM _rev_stg \
ON CONFLICT (${pk}) DO UPDATE SET $(_excl "$@");"
  } > "$payload"

  _assert_revision_payload "$payload" "$t" || exit 67
  _revision_telemetry "$t" "$seq"

  ssh -o BatchMode=yes "$VPS" \
      "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
        -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\"" < "$payload"
  rm -f "$payload"
  echo "    ✓ ${t}"
}

# 整表鏡像（#344）：單交易 TRUNCATE 目標表 → `_stage` 暫存 → 全量 INSERT，id 與序列一併鏡像本機。
#
# 適用：本機寫入語意與 sync_table（只 UPSERT、不 DELETE）對不上的表——
#   - box_pitching_revisions：只有 identity `id`，072 刻意拿掉內容 UNIQUE；兩邊各自配號，
#     拿 id 當衝突鍵就是 game_recap_source_revisions 事故的形狀（見 sync_pa_build 上方註解），
#     而 sync_revision_table 需要內容唯一鍵。
#   - championship_members：本機 builder 每次 TRUNCATE 重建；sync_table 會讓本機已移除的列殘留在 prod。
# 形狀同 sync_advanced_snapshot：`_stage`（**非** `_stage_noseq`）——dump 帶出的 setval 把 prod 序列設成本機值，
# 與 OVERRIDING SYSTEM VALUE 明確帶入的本機 id 一致，是對的（見 sync_revision_table 上方說明）。
# 前提：prod 不是這些表的權威 writer，本機值整表覆蓋 prod（#344 需求方裁定：以本機為準）。
# 第二參數 `identity`：該表有 GENERATED ALWAYS identity 欄，INSERT 需 OVERRIDING SYSTEM VALUE。
#
# fail-closed：本機 0 列（或取不到列數）拒寫——TRUNCATE 後灌入空表等於清空 prod。
# payload 先落地、斷言只 TRUNCATE 目標表一張（無 CASCADE）＋恰 1 個 COPY＋1 個 INSERT 才送出。
mirror_table() {  # $1=表 $2=identity（可省略）
  local t="$1" mode="${2:-}" n payload why overriding=""
  [ "$mode" = identity ] && overriding="OVERRIDING SYSTEM VALUE "
  n="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -At -c "SELECT count(*) FROM cpbl.${t}" || true)"
  if ! [[ "$n" =~ ^[0-9]+$ ]] || [ "$n" -eq 0 ]; then
    echo "FATAL: mirror_table ${t}：本機列數為 '${n}'，拒絕以 TRUNCATE 整表鏡像（未送出，生產未被觸碰）" >&2
    exit 67
  fi
  payload="$(mktemp "${TMPDIR:-/tmp}/cpbl-mirror-${t}.XXXXXX")"
  {
    echo "TRUNCATE cpbl.${t};"
    _stage "$t" _mirror_stg
    echo "INSERT INTO cpbl.${t} ${overriding}SELECT * FROM _mirror_stg;"
  } > "$payload"
  why="$(awk -v t="$t" '
    in_copy { if ($0 == "\\.") in_copy = 0; next }
    /^COPY _mirror_stg / { copies++; in_copy = 1; next }
    /^TRUNCATE / { truncs++; if ($0 != "TRUNCATE cpbl." t ";") print "TRUNCATE 對象不符：" substr($0, 1, 80) }
    /^INSERT INTO / { inserts++; if (index($0, "INSERT INTO cpbl." t " ") != 1) print "INSERT 對象不符：" substr($0, 1, 80) }
    toupper($0) ~ /^(DELETE|DROP|ALTER)([^A-Z_]|$)|(^|[^A-Z_])CASCADE([^A-Z_]|$)/ { print "禁止語句：" substr($0, 1, 80) }
    END { if (truncs != 1 || copies != 1 || inserts != 1 || in_copy) print "形狀不符：TRUNCATE=" truncs+0 " COPY=" copies+0 " INSERT=" inserts+0 " 未結束=" in_copy+0 }
  ' "$payload")"
  if [ -n "$why" ]; then
    echo "FATAL: mirror_table ${t} 的 payload 未通過送出前守衛（未送出；payload 保留於 ${payload}）：${why}" >&2
    exit 67
  fi
  ssh -o BatchMode=yes "$VPS" \
      "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
        -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\"" < "$payload"
  rm -f "$payload"
  echo "    ✓ ${t}（整表鏡像 ${n} 列）"
}

# 季後賽果三表（#268）：games 與兩張官方狀態軌跡表，加上官方賽程異動訊號表（B1）。完整鏈與
# POSTSEASON_RESULTS_ONLY 共用**同一份**欄位清單——兩處各寫一份會漂（sync_table 的「只插不更」教訓見上方）。
sync_postseason_results() {
  sync_table games "year,kind_code,game_season_code,game_sno" \
    game_date present_status venue home_team_code home_team_name away_team_code away_team_name \
    home_score away_score home_starter_id away_starter_id winning_pitcher_id losing_pitcher_id closer_id mvp_id \
    delay_kind orig_date
  # 官方狀態觀測軌跡：`/api/v1/games/{sno}/status` 與首頁 unresolved_games 的官方狀態判定
  # （helpers.official_status）讀的就是 game_schedule_status_revisions；不同步過來，prod
  # 對每一場都只能 fail closed 回 unknown，延賽／保留賽在線上永遠看不出來。
  sync_revision_table game_schedule_status_revisions \
    "year,kind_code,game_season_code,game_sno,payload_hash" \
    year kind_code game_season_code game_sno raw_present_status raw_game_result \
    raw_game_date raw_pre_exe_date payload_hash raw_payload fetched_at last_seen_at seen_count
  sync_revision_table game_source_revisions \
    "year,kind_code,game_sno,source,source_version" \
    year kind_code game_sno source source_version outcome row_count error_code detail \
    fetched_at last_seen_at seen_count
  # 官方賽程異動訊號（migration 075，#268 B1 需求方裁定 6142744045）：首頁／季後頁／日曆的「賽程待更新」
  # 讀的就是它；不同步過來，正式站在 www／同步失敗時永遠看不到待更新。自然鍵 PK、無 identity，
  # 走通用 sync_table（含寫入前欄位守衛）。prod 端無其他 writer；本機只 resolve 不刪列，upsert 足夠。
  # ⚠️ 表由 075 建立：主站部署含 075 的映像前，這一行會因生產端無此表而失敗（同 073 前例）——先部署再同步。
  sync_table official_change_signals "year,kind_code,game_sno,field" official_value detected_at resolved_at
}

# #365 S4（P-EVENING-BACKUP）：晚間兩個早退模式（RESULTS_ONLY／BOXPA_ONLY）的「每晚首次同步前備份一次」。
# 晚間鏈在同一晚已有已驗證備份時帶 REUSE_VERIFIED_BACKUP／REUSE_VERIFIED_BACKUP_SHA256；這裡在**同一行程**、
# 緊接同步之前重新確認三件事——檔案存在、位於本次 BACKUP_DIR 下、sha256 相符——全成立才略過備份；任一不成立
# 就照現行呼叫 backup-prod-db.sh（重備，不是失敗）。⛔ 不在無已驗證備份時放行同步。
# 新備份（或沿用）成功後寫一行到 BACKUP_RECORD（`new|reuse <sha256> <path>`，晚間狀態檔入帳用）；寫不出來不擋同步，
# 只是下一次會重備（方向安全）。sha256 用 sha256sum（CI ubuntu）或 shasum -a 256（macOS），⛔ 不用 python3
# （測試 harness 把 python3 換成假樁）。⛔ 不影響完整鏈 2/4 的每日備份（7 份）。
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'
}
real_dir() { (cd "$1" 2>/dev/null && pwd -P); }
evening_backup() {  # $1＝本次 BACKUP_DIR；設 BACKUP_PATH
  local dir="$1" reuse="${REUSE_VERIFIED_BACKUP:-}" want="${REUSE_VERIFIED_BACKUP_SHA256:-}" have="" mode="new"
  if [ -n "$reuse" ] && [ -n "$want" ] && [ -f "$reuse" ] && [ -n "$(real_dir "$dir")" ] \
     && [ "$(real_dir "$(dirname "$reuse")")" = "$(real_dir "$dir")" ] \
     && [ "$(sha256_of "$reuse" 2>/dev/null || true)" = "$want" ]; then
    BACKUP_PATH="$reuse"
    mode="reuse"
    echo "    ✓ 沿用 night_backup=${BACKUP_PATH}（同一行程重驗：存在、位於 BACKUP_DIR、sha256 相符）"
  else
    [ -n "$reuse" ] && echo "    ⓘ night_backup 不可沿用（檔案／目錄／sha256 不符）：照現行重新備份"
    BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" BACKUP_DIR="$dir" \
      BACKUP_KEEP="${BACKUP_KEEP:-3}" "$REPO_DIR/scripts/backup-prod-db.sh")"
    echo "    ✓ 已驗證備份：${BACKUP_PATH}"
  fi
  if [ -n "${BACKUP_RECORD:-}" ]; then
    have="$(sha256_of "$BACKUP_PATH" 2>/dev/null || true)"
    if [ -n "$have" ]; then
      printf '%s %s %s\n' "$mode" "$have" "$BACKUP_PATH" > "$BACKUP_RECORD" 2>/dev/null \
        || echo "    ⚠ BACKUP_RECORD 寫不出來（不擋同步；下一次同步會重備）"
    fi
  fi
}

# 季後晚間事件鏈（#268 WP3，scripts/postseason-evening.sh 呼叫）：比照 LINEUP_ONLY 早退。
# 只做「獨立目錄的已驗證備份 → 三表＋異動訊號表同步 → /api/info data-only 對帳」（僅訊號變動時同一路徑）：
#   ⛔ 不爬（必須 SKIP_SCRAPE=1）、不 build-features、不跑 migration、不訓練、
#   ⛔ 不寫 prod refresh 標記（那是整鏈成功的標記，晚間只同步三表不得冒用）、不同步 074 公告表。
# BACKUP_DIR 必須明示且不得是 10:10 的預設目錄：晚間備份不得輪替掉每日鏈的 7 份歷史深度。
if [ -n "${POSTSEASON_RESULTS_ONLY:-}" ]; then
  if [ "$POSTSEASON_RESULTS_ONLY" != 1 ] || [ "${SKIP_SCRAPE:-}" != 1 ] || [ -n "${WITH_DETAIL:-}" ]; then
    echo 'FATAL: POSTSEASON_RESULTS_ONLY=1 必須搭配 SKIP_SCRAPE=1，且不得帶 WITH_DETAIL' >&2
    exit 64
  fi
  if [ -z "${BACKUP_DIR:-}" ] \
     || [ "$BACKUP_DIR" = "$HOME/Library/Application Support/cpbl-analytics/backups" ]; then
    echo 'FATAL: POSTSEASON_RESULTS_ONLY 需明示獨立的 BACKUP_DIR（不得與每日鏈共用輪替視窗）' >&2
    exit 64
  fi
  cd "$REPO_DIR"
  # ⚠️ 與完整鏈下方的 freshness 基準**逐字同源**（tests/test_postseason_evening_sync.py 釘住）：
  # 同一支 `cpbl.completion --with-evidence`、同一段 SQL。
  COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion --with-evidence)"
  LOCAL_FRESHNESS="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -At -F '|' -c \
    "SELECT COALESCE(max(game_date) FILTER (WHERE ${COMPLETED_GAMES_SQL})::text, ''), \
            count(*) FILTER (WHERE year = ${YEAR} AND ${COMPLETED_GAMES_SQL}) \
     FROM cpbl.games g")"
  IFS='|' read -r EXPECTED_LAST_GAME_DATE EXPECTED_COMPLETED <<< "$LOCAL_FRESHNESS"
  if [ -z "$EXPECTED_LAST_GAME_DATE" ] || ! [[ "$EXPECTED_COMPLETED" =~ ^[0-9]+$ ]]; then
    echo "FATAL: 無法取得本機 freshness 基準：${LOCAL_FRESHNESS}" >&2
    exit 65
  fi
  echo '==> 季後晚間：獨立目錄備份 production（整庫）；驗證不過即中止'
  # 檔案 0600／目錄 0700 由 backup-prod-db.sh 自身的 umask 077 保證（producer 是唯一責任層，
  # #268 需求方裁定 6138860627）；這裡不重複設 umask，只指定晚間專用的 BACKUP_DIR／BACKUP_KEEP。
  evening_backup "$BACKUP_DIR"
  echo '==> 季後晚間：三表＋異動訊號表非破壞性 upsert（games／官方狀態軌跡兩表／official_change_signals）'
  sync_postseason_results
  echo '==> 季後晚間：對帳 production 真實資料 freshness（data-only；不寫 refresh 標記）'
  wait_api_info_cache_since "$(date +%s)"
  # 對帳不等（或取不到 /api/info）回專屬的 68：核定規劃對它的處置是「記失敗並停止當晚」，
  # 與 64–67／psql 錯誤的「立即停、bootout、交人工」不同，故不得與其他非零碼混用。
  if ! curl -fsS --retry 3 --retry-delay 15 --max-time 20 "$API_INFO_URL" \
    | python3 "$REPO_DIR/scripts/verify_refresh_info.py" --data-only \
        --expected-last-game-date "$EXPECTED_LAST_GAME_DATE" \
        --expected-season-games-completed "$EXPECTED_COMPLETED"; then
    echo 'FATAL: 季後晚間 data-only 對帳不等（停止當晚，三表已寫入；見 Runbook §10）' >&2
    exit 68
  fi
  echo '==> 季後晚間：完成（只代表三表＋異動訊號表同步與對帳，不代表整鏈刷新）'
  exit 0
fi

# 季後目標場 box／PA（#293 S12 WP2；scripts/postseason-evening.sh 的晚間目標場階段呼叫）：比照 ROSTER_ONLY 早退。
# 只做：唯讀自檢（production 已完賽、本機 FK 閉包、可送 PA 的場）→ 獨立目錄已驗證備份 →
#       box 七表只對目標場鍵 upsert（sync_box_tables，與完整鏈同一份欄位清單；不 DELETE）→
#       PA 五表在單一交易內只替換目標場鍵（子→父 DELETE＋父→子 OVERRIDING SYSTEM VALUE 插入）→
#       逐表逐場對帳，manifest 寫到 BOXPA_MANIFEST。
#   ⛔ 不爬、不 build-features、不跑 migration、不訓練、⛔ 不寫 refresh 標記、不同步其他表、
#   ⛔ 不 TRUNCATE、不 CASCADE、⛔ 不呼叫 prod_cpbl_api（新碼只在本機跑；VPS 只收 SQL 文字，PLAN r2 §9.1；
#   tests/test_boxpa_sync_mode.py 釘住）。
# 離開碼：0 成功 · 64 參數錯 · 67 本機自檢／payload 守衛不過（未送） · 68 對帳不等
#        72 ssh 連線失敗（暫時性，晚間鏈可重送一次） · 73 production 尚未完賽（等下一次）
#        74 production psql 錯誤（不重送） · 其他＝備份或本機錯誤（不重送）
if [ -n "${POSTSEASON_BOXPA_ONLY:-}" ]; then
  if [ -z "${POSTSEASON_BOXPA_GAMES:-}" ] \
     || ! [[ "$POSTSEASON_BOXPA_GAMES" =~ ^[0-9]{4}-[AEC]-[0-9]{1,3}(,[0-9]{4}-[AEC]-[0-9]{1,3})*$ ]]; then
    # #365：晚間鏈涵蓋一軍 A（⛔ 不收 D）；A 與 E／C 同一送達單位，PARTS 預設 box,pa 不另設。
    echo 'FATAL: POSTSEASON_BOXPA_GAMES 需為目標場鍵清單（YYYY-A|E|C-SNO，逗號分隔）' >&2
    exit 64
  fi
  # 這次要送的來源（#293 審核席 1 F3）：box＝box 七表、pa＝PA 五表；預設兩者。晚間鏈只傳仍有額度的來源。
  BOXPA_PARTS="${POSTSEASON_BOXPA_PARTS:-box,pa}"
  if ! [[ "$BOXPA_PARTS" =~ ^(box|pa|box,pa)$ ]]; then
    echo 'FATAL: POSTSEASON_BOXPA_PARTS 只接受 box、pa 或 box,pa' >&2
    exit 64
  fi
  if [ -z "${BOXPA_MANIFEST:-}" ] || [ "${BOXPA_MANIFEST#/}" = "$BOXPA_MANIFEST" ]; then
    echo 'FATAL: POSTSEASON_BOXPA_ONLY 需明示 BOXPA_MANIFEST（對帳 manifest 的絕對路徑）' >&2
    exit 64
  fi
  # 備份目錄比照 ROSTER_ONLY：只收絕對路徑、以 realpath 與每日鏈目錄比較（不得共用輪替視窗）。
  if [ -z "${BACKUP_DIR:-}" ] || [ "${BACKUP_DIR#/}" = "$BACKUP_DIR" ]; then
    echo 'FATAL: POSTSEASON_BOXPA_ONLY 需明示獨立的 BACKUP_DIR（絕對路徑；不得與每日鏈共用輪替視窗）' >&2
    exit 64
  fi
  BOXPA_BACKUP_DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$BACKUP_DIR")"
  BOXPA_DAILY_BACKUP_DIR="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' \
    "$HOME/Library/Application Support/cpbl-analytics/backups")"
  if [ -z "$BOXPA_BACKUP_DIR" ] || [ "$BOXPA_BACKUP_DIR" = "$BOXPA_DAILY_BACKUP_DIR" ]; then
    echo 'FATAL: POSTSEASON_BOXPA_ONLY 的 BACKUP_DIR 與每日鏈備份目錄是同一個目錄（不得共用輪替視窗）' >&2
    exit 64
  fi
  cd "$REPO_DIR"
  BOXPA_STARTED="$(date +%s)"
  BOXPA_LOCAL_PSQL="docker exec -i ${LOCAL_DB} psql -X -U cpbl -d cpbl"
  BOXPA_TARGET_PSQL="ssh -o BatchMode=yes ${VPS} 'cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -X -U \"\$DB_USER\" -d \"\$DB_NAME\"'"
  echo "==> 季後目標場 box／PA（${POSTSEASON_BOXPA_GAMES}）：唯讀自檢（production 完賽／本機 FK 閉包／可送 PA 的場）"
  # 非零（64／67／72／73／74）在 set -e 下原碼結束：未備份、未寫入。
  BOXPA_PRECHECK="$(uv run python -m cpbl.ingest.boxpa_sync precheck --games "$POSTSEASON_BOXPA_GAMES" \
    --local-psql "$BOXPA_LOCAL_PSQL" --target-psql "$BOXPA_TARGET_PSQL")"
  echo "$BOXPA_PRECHECK"
  BOXPA_PA_GAMES="$(printf '%s\n' "$BOXPA_PRECHECK" | sed -n 's/^BOXPA_PA_GAMES=//p')"
  case ",${BOXPA_PARTS}," in *,pa,*) ;; *) BOXPA_PA_GAMES="" ;; esac   # 不送 PA：production PA 一列不動
  SYNC_SCOPE_KEYS_SQL="$(printf '%s\n' "$BOXPA_PRECHECK" | sed -n 's/^BOXPA_KEYS_SQL=//p')"
  if [ -z "$SYNC_SCOPE_KEYS_SQL" ]; then
    echo 'FATAL: 自檢未回傳目標場鍵條件（未備份、未寫入）' >&2
    exit 67
  fi
  BOXPA_PA_PAYLOAD="$(mktemp "${TMPDIR:-/tmp}/cpbl-boxpa-pa.XXXXXX")"
  uv run python -m cpbl.ingest.boxpa_sync pa-payload --games "$POSTSEASON_BOXPA_GAMES" \
    --pa-games "$BOXPA_PA_GAMES" --local-psql "$BOXPA_LOCAL_PSQL" --out "$BOXPA_PA_PAYLOAD"
  echo '==> 季後目標場 box／PA：獨立目錄備份 production（整庫）；驗證不過即中止'
  evening_backup "$BOXPA_BACKUP_DIR"
  case ",${BOXPA_PARTS}," in
    *,box,*)
      echo '==> 季後目標場 box／PA：box 七表目標場 upsert（同完整鏈欄位清單；不 DELETE）'
      sync_box_tables
      ;;
    *) echo '    · box：本次不送（POSTSEASON_BOXPA_PARTS 不含 box；production box 未動）' ;;
  esac
  if [ -s "$BOXPA_PA_PAYLOAD" ]; then
    echo "==> 季後目標場 box／PA：PA 五表目標場單交易替換（${BOXPA_PA_GAMES}；不 TRUNCATE、不 CASCADE）"
    BOXPA_RC=0
    ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
          -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\"" \
        < "$BOXPA_PA_PAYLOAD" || BOXPA_RC=$?
    if [ "$BOXPA_RC" -ne 0 ]; then
      echo "FATAL: PA 五表目標場替換失敗 rc=${BOXPA_RC}（單交易已回滾；payload 保留於 ${BOXPA_PA_PAYLOAD}）" >&2
      [ "$BOXPA_RC" -eq 255 ] && exit 72
      exit 74
    fi
    echo '    ✓ PA 五表（目標場）'
  else
    echo '    · PA：本次沒有可送的場（POSTSEASON_BOXPA_PARTS 不含 pa，或本機尚無 published build；production PA 未動）'
  fi
  rm -f "$BOXPA_PA_PAYLOAD"
  echo '==> 季後目標場 box／PA：逐表逐場對帳（本機 vs production）'
  BOXPA_RC=0
  uv run python -m cpbl.ingest.boxpa_sync reconcile --games "$POSTSEASON_BOXPA_GAMES" \
    --pa-games "$BOXPA_PA_GAMES" --local-psql "$BOXPA_LOCAL_PSQL" --target-psql "$BOXPA_TARGET_PSQL" \
    --parts "$BOXPA_PARTS" --out "$BOXPA_MANIFEST" || BOXPA_RC=$?
  echo "    ⓘ 耗時 $(( $(date +%s) - BOXPA_STARTED )) 秒；manifest：${BOXPA_MANIFEST}"
  if [ "$BOXPA_RC" -ne 0 ]; then
    echo "FATAL: 季後目標場對帳未通過 rc=${BOXPA_RC}（已寫入的列保留；見 manifest）" >&2
    exit "$BOXPA_RC"
  fi
  echo '==> 季後目標場 box／PA：完成（只代表目標場 box 七表＋PA 五表同步與對帳，不代表整鏈刷新）'
  exit 0
fi

cd "$REPO_DIR"

# —— #364 §3.5 VPS 訓練閘門（只決定跑不跑；單次尖峰與記憶體屬 #353）——
# 只在每日鏈帶 DAILY_DAY_TYPE 時生效；手動直呼（未設定）＝現況四步照跑。
# RUN_OUTCOME 管三件同條件的事：本機 cpbl-build-features、3/4 的 game_features 清空＋全鏡像、
# 4/4 的 cpbl-train-outcome（無新完賽場時三者內容都不變，PLAN-r2 §3.5）。
# RUN_SIMPLE＝auto 時於 4/4 讀正式站 artifact 的 trained_through 再決定。
#
# 正式站兩個量（一次唯讀 psql，印一行 JSON）：最新 model_versions(task='outcome') 的 cv_metrics（trainer
# 自己寫的 test_seasons／n_train／n_test），與 game_features 各季 completed 列數（含和局，#364 第 2 輪 F1）。
# 讀不到一律印空字串 → daily_gate train-gate 判照跑（fail open）。不依賴新碼部署。
remote_outcome_model_metrics() {
  ssh -o BatchMode=yes "$VPS" \
    "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec prod_pg psql -At -U \"\$DB_USER\" -d \"\$DB_NAME\" -c \"SELECT json_build_object('model', (SELECT cv_metrics FROM cpbl.model_versions WHERE task = 'outcome' ORDER BY trained_at DESC LIMIT 1), 'features_completed', (SELECT json_object_agg(season, n) FROM (SELECT season, count(*) AS n FROM cpbl.game_features WHERE completed GROUP BY season) s))::text\"" \
    2>/dev/null | tail -n 1 || true
}
# #353 WP1：PA 全量模式只能人工指定——在任何備份／寫入之前就擋下每日鏈與錯誤的值。
case "${PA_FULL_RESYNC:-0}" in
  0) ;;
  1)
    if [ -n "${DAILY_DAY_TYPE:-}" ] || [ -z "${WITH_DETAIL:-}" ]; then
      echo 'FATAL: PA_FULL_RESYNC=1 只能人工指定（不得帶 DAILY_DAY_TYPE），且需 WITH_DETAIL=1（未備份、未寫入）' >&2
      exit 64
    fi
    ;;
  *)
    echo "FATAL: PA_FULL_RESYNC 只接受 0 或 1：${PA_FULL_RESYNC}" >&2
    exit 64
    ;;
esac
RUN_OUTCOME=1
RUN_SIMPLE=1
OUTCOME_REASON="未套閘門（手動直呼或 DAILY_FORCE_FULL=1）"
if [ -n "${DAILY_DAY_TYPE:-}" ] && [ "${DAILY_FORCE_FULL:-0}" != "1" ]; then
  case "$DAILY_DAY_TYPE" in
    full)
      # §3.5：本機完成場（唯讀）對照正式站上次回測的訓練資料規模；任何失敗 → 照跑（fail open）。
      if GATE_OUT="$(remote_outcome_model_metrics \
           | uv run python -m cpbl.ingest.daily_gate train-gate --prod-metrics - 2>&1)" \
         && printf '%s\n' "$GATE_OUT" | grep -q '^RUN_OUTCOME=[01]$'; then
        RUN_OUTCOME="$(printf '%s\n' "$GATE_OUT" | sed -n 's/^RUN_OUTCOME=//p' | tail -n 1)"
        OUTCOME_REASON="$(printf '%s\n' "$GATE_OUT" | sed -n 's/^OUTCOME_REASON=//p' | tail -n 1)"
      else
        RUN_OUTCOME=1
        OUTCOME_REASON="訓練閘門判定失敗 → 照跑（fail open）：$(printf '%s' "${GATE_OUT:-}" | tail -n 1)"
      fi
      RUN_SIMPLE=auto
      ;;
    light|sync_only)
      RUN_OUTCOME=0
      RUN_SIMPLE=0
      OUTCOME_REASON="日型 ${DAILY_DAY_TYPE}：不訓練（PLAN-r2 §3.2）"
      ;;
    *)
      echo "FATAL: DAILY_DAY_TYPE 只接受 full／light／sync_only：${DAILY_DAY_TYPE}" >&2
      exit 64
      ;;
  esac
  echo "==> 訓練閘門（§3.5，日型 ${DAILY_DAY_TYPE}）：RUN_OUTCOME=${RUN_OUTCOME} — ${OUTCOME_REASON}"
fi

# SKIP_SCRAPE=1：本機 DB 已是最新時，跳過重爬、直接把現有資料同步到 prod。
if [ -n "${SKIP_SCRAPE:-}" ]; then
  echo "==> 1/4 略過爬取（SKIP_SCRAPE），直接同步本機現有資料"
else
  echo "==> 1/4 本機（台灣 IP）爬最新資料"
  # --group scrape：官網爬蟲需 playwright（見 scrape-daily.sh 說明）。
  uv run --group scrape cpbl-scrape-games "$YEAR" "$YEAR"
  uv run --group scrape cpbl-scrape-stats "$PREV" "$YEAR"

  # 選手細項（投打對決 / 對戰各隊 / 分項）變動慢且耗時逾 1 小時，預設不跑；
  # 需要時以 WITH_DETAIL=1 觸發（每隔幾週跑一次即可）。
  if [ -n "${WITH_DETAIL:-}" ]; then
    echo "    + 選手細項（耗時較長：投打對決生涯 + 對戰各隊 + 分項）"
    uv run --group scrape cpbl-scrape-fighting 9999 1.2 cur
    uv run --group scrape cpbl-scrape-detail 1.2
  fi
fi

# 本機重建賽事預測特徵（全史 kind A；leakage-safe）。game_features 是「派生」資料，
# 由本機完整 games 計算後直接鏡像到 prod，省去同步 1990+ 原始逐場（歷史不可變）。
if [ "$RUN_OUTCOME" = 1 ]; then
  echo "    + 重建 game_features（賽事預測特徵，全史 kind A）"
  uv run cpbl-build-features 2>&1 | tail -1
else
  echo "    ⏭ 略過 cpbl-build-features（§3.5 訓練閘門：${OUTCOME_REASON}）"
fi

# 記住本機真實賽事 freshness；同步後 API 必須回報相同值，不能只靠腳本自寫 marker。
# 由 Python contract 產生 SQL，避免同步 gate 與 API 各自複製 completed 語意。
#
# ⚠️ **必須是 --with-evidence，且不得省略**（DATA-TZ-BOUNDARY-SUCCESSION1 (3c)）：本值會被
# verify_refresh_info.py 拿去跟 /api/info 的 last_game_date／season_games_completed 做
# **精確相等**比對，不等就擋同步。/api/info（api/routers/info.py）用的是
# completed_games_sql_with_evidence，所以閘門也必須用同一支 helper——否則比的是兩套判準，
# 一分歧就是「資料明明對、同步卻被擋」，而且擋在**已經備份完、正要 upsert** 的位置。
# 兩套判準的差在本機實測為 5 場（2018/A/124、2021/A/256、2023/A/119、2023/A/175、
# 2025/A/233 這 5 場經取證的 0:0 真和局），舊判準全部漏判。
#
# ⚠️ **日界也必須自帶時區**：這段 SQL 文字在 `docker exec psql` 裡求值——那是**連線池之外**
# 的 session，`cpbl.db` 的 `configure` 管不到它，其 `CURRENT_DATE` 仍是 UTC（2026-08-20
# 20:2x UTC 實測：該 session `SHOW timezone` = UTC、`CURRENT_DATE` = 2026-08-20，而台北
# 已是 08-21）。helper 的預設 as_of 是 `(now() AT TIME ZONE 'Asia/Taipei')::date`，
# 不依賴執行它的 session，這正是這裡需要的性質。
#
# ⚠️ `FROM cpbl.games g` 的別名不是排版：--with-evidence 產出的條件帶 `g.` 限定詞
# （相關子查詢內未限定的欄名會解析到內層證據表，見 completion.py 的說明），沒有別名
# 這段 SQL 直接語法錯誤。回歸釘在 tests/test_backup_prod_db.py。
# ⚠️ 外層的 `max(game_date)`／`year` 刻意**不加**限定詞：FROM 只有一張表、無歧義，
# 而 tests/test_prod_sync_revision_seq.py 的假 docker 樁以字面 `max(game_date)` 認這支
# 查詢（認不出就回空字串 → 腳本 exit 65）。加了限定詞會讓那 13 條測試全紅，
# 而那個檔不在本卡資源宣告內。
COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion --with-evidence)"
LOCAL_FRESHNESS="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -At -F '|' -c \
  "SELECT COALESCE(max(game_date) FILTER (WHERE ${COMPLETED_GAMES_SQL})::text, ''), \
          count(*) FILTER (WHERE year = ${YEAR} AND ${COMPLETED_GAMES_SQL}) \
   FROM cpbl.games g")"
IFS='|' read -r EXPECTED_LAST_GAME_DATE EXPECTED_COMPLETED <<< "$LOCAL_FRESHNESS"
if [ -z "$EXPECTED_LAST_GAME_DATE" ] || ! [[ "$EXPECTED_COMPLETED" =~ ^[0-9]+$ ]]; then
  echo "FATAL: 無法取得本機 freshness 基準：${LOCAL_FRESHNESS}" >&2
  exit 65
fi

trap _on_exit EXIT
start_availability_sentinel || echo "    ⚠ 可用性哨兵啟動失敗（不影響本次同步）" >&2

echo "==> 2/4 備份 production 資料庫（整庫：cpbl ＋ 主站 public）"
BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" "$REPO_DIR/scripts/backup-prod-db.sh")"
echo "    ✓ 已驗證備份：${BACKUP_PATH}"

echo "==> 3/4 套用 prod migration + 非破壞性 upsert 同步"
# 同步前先讓 prod 套用任何新 migration（否則新欄位不存在、COPY 對不上）
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api python -c "
from cpbl import db
try:
    print(\"migrated:\", db.migrate())
finally:
    if db._pool is not None:
        db._pool.close()
    print(\"migration pool closed\")"'

# 正常daily/full在同一次已驗證備份與schema後也同步074。
prepare_lineup_copy
sync_lineup_announcements

# games＋官方狀態軌跡兩表＋異動訊號表（與 POSTSEASON_RESULTS_ONLY 共用同一份清單，見 sync_postseason_results）。
sync_postseason_results
sync_table pitching_current "year,player_id" name team_code era ip g gs w l whip k9 fip era_plus sv hld \
  so cg sho pa np h hr bb ibb hbp wp bk r er go ao goao
sync_table batting_current "year,player_id" name team_code pa avg obp slg ops hr ops_plus k_pct bb_pct \
  g ab r h b2 b3 rbi bb so sb cs tb gidp sh sf ibb hbp go ao goao
sync_table fielding_current "year,kind_code,player_id,pos" name team_code g tc po a e dp tp pb cs sba fpct
sync_table team_current "year,team_code" name bat_avg bat_obp bat_slg bat_ops bat_hr pit_era pit_whip
sync_table coaches "year,team_code,name" pos uniform_no
# 維基/官網參考資料（一次抓+手動刷新；非每日爬）：本機灌好後鏡像到 prod
sync_table managers "team_code,era_name,name,from_year" to_year g w l t win_pct postseason championships source needs_review
sync_table overseas "player_id,league,from_year" team source needs_review
sync_table player_awards "player_id,year,category,award" source
# 維基個人頁補充（所屬球隊/教練/行政、國際賽獎牌、獎項）：一次抓+手動刷新
sync_table wiki_tenures "player_id,phase,seq" team_raw role from_year to_year source needs_review
sync_table wiki_medals "player_id,seq" color competition event year source
sync_table wiki_awards "player_id,seq" award note years source
sync_table retired_numbers "team_code,number" holder_type player_id holder_name retired_year status note source needs_review
sync_table players "id" \
  name full_name handedness bats throws birthday country \
  height_cm weight_kg debut education birthplace draft bio_updated_at
sync_table venue_dim "venue" \
  full_name turf indoor city capacity infield_seats outfield_seats lf_dist cf_dist rf_dist \
  big_screen address phone field_sid
# 打擊投影（本機容器 cpbl-train 產出；outcome 的 model_versions 由 VPS 自己回測寫入，upsert 不衝突）
sync_table model_versions "id" task algo trained_at params cv_metrics
sync_table projections "player_id,target_year,model_version,stat" predicted actual
# sabermetrics 打底（本機 cpbl-build-sabr 產出，derived 故鏡像）
sync_table fielding_innings "year,kind_code,player_id,pos" outs games
sync_table run_expectancy "span,kind_code,bases,outs" re samples
# sabermetrics Phase A+B 指標（wSB/DER/捕手失分/RE24；同為 derived 鏡像）
sync_table sabr_run_values "span,kind_code,metric" value samples
sync_table batter_wsb "year,player_id" sb cs opp wsb
sync_table team_der "year,team_id" bf h hr bb hbp so der
sync_table catcher_runs "year,kind_code,player_id" runs games
sync_table batter_re24 "year,kind_code,player_id" pa re24
sync_table pitcher_re24 "year,kind_code,player_id" bf re24
# 逐打席勝率打底（run_dist 分布 + WE 邊界；API /games/{sno}/winprob 讀這兩張）
sync_table run_dist "span,kind_code,side,bases,outs,k" p samples
sync_table win_expectancy "span,kind_code,inning,half,diff" p_win p_tie
sync_table batter_traits "year,kind_code,player_id" \
  pa p_pa go fo dir_left dir_center dir_right two_strike_pa two_strike_k two_strike_hit
sync_table pitcher_traits "year,kind_code,player_id" bf p_pa go fo two_strike_pa two_strike_k
sync_table team_standings "year,kind_code,season_code,team_code" \
  team_name rank g w t l win_pct gb elim home_record away_record streak last10 h2h updated_at
# #344：每日鏈本機寫入、prod API 有讀取端但原本沒同步的表。
# 球員升降一／二軍事件（每日鏈 scrape_transactions；players.py 一／二軍判定）。
sync_table player_transactions "year,acnt,trans_date,kind_code" name team_name reason updated_at
# 完成場外部證據（completion.py 完賽判準的輸入；寫入者目前只有一次性腳本）。
sync_table game_completion_evidence "year,kind_code,game_sno,evidence_kind" \
  source_url payload_sha256 innings_played approved_by note created_at
# 總冠軍成員：本機每日 TRUNCATE 重建，故整表鏡像（見 mirror_table）。
mirror_table championship_members

# 賽事預測特徵：完整鏡像（先 TRUNCATE 清掉 prod 舊版＝早期未過濾 kind 混入的二軍/季後列），
# 再把本機全史 kind A 特徵灌入。derived 資料，安全可重建。
# #364 §3.5：本機特徵沒重建（RUN_OUTCOME=0）時不重灌——內容不變，清空＋全鏡像只是白做。
if [ "$RUN_OUTCOME" = 1 ]; then
ssh -o BatchMode=yes "$VPS" \
  "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -q -U \"\$DB_USER\" -d \"\$DB_NAME\" -c 'TRUNCATE cpbl.game_features'"
sync_table game_features "year,kind_code,game_season_code,game_sno" \
  game_date season home_team_code away_team_code home_team_name away_team_name home_win completed \
  winrate_diff prior_winpct_diff runs_scored_diff runs_allowed_diff recent_form_diff rest_days_diff \
  h2h_home home_field starter_era_diff starter_whip_diff starter_k9_diff \
  prior_team_ops_diff prior_team_slg_diff prior_team_era_diff prior_team_whip_diff \
  team_ops_now_diff team_avg_now_diff team_sb_now_diff team_wp_now_diff team_err_now_diff run_diff_diff
else
  echo "    ⏭ 略過 game_features 清空＋全鏡像（§3.5 訓練閘門：${OUTCOME_REASON}）"
fi

if [ -n "${WITH_DETAIL:-}" ]; then
  sync_table batter_pitcher_matchups "year,kind_code,hitter_acnt,pitcher_acnt" \
    hitter_name pitcher_name hitter_team_no pitcher_team_no plate_appearances at_bats hits rbi \
    singles doubles triples home_runs total_bases avg obp slg ops sac_hit sac_fly bb ibb hbp so \
    ground_out fly_out goao strike_pct ball_pct swing_pct first_pitch_swing_pct whiff_pct gb_pct ld_pct fb_pct updated_at
  sync_table batting_vs_team "year,kind_code,acnt,fight_team_code" \
    fight_team_name team_no total_games plate_appearances at_bats hits rbi runs singles doubles triples \
    home_runs total_bases gidp sac_hit sac_fly bb ibb hbp so sb_ok sb_fail sb_pct avg obp slg ta ops updated_at
  sync_table pitching_vs_team "year,kind_code,acnt,fight_team_code" \
    fight_team_name team_no total_games starts closes complete_games shutouts wins loses save_ok save_fail \
    holds inning_pitched_cnt inning_pitched_div3 whip era plate_appearances pitch_cnt hits home_runs bb ibb \
    hbp so wild_pitch balk runs earned_runs updated_at
  sync_table batting_splits "year,kind_code,acnt,item_group_code,item_index,item_name" \
    item_note plate_appearances at_bats hits rbi singles doubles triples home_runs total_bases \
    sac_hit sac_fly bb ibb hbp so ground_outs fly_outs goao avg obp slg ops updated_at
  sync_table pitching_splits "year,kind_code,acnt,item_group_code,item_index,item_name" \
    item_note wins loses starts complete_games shutouts save_ok inning_pitched_cnt \
    inning_pitched_div3 plate_appearances pitch_cnt strikes balls hits home_runs sac_hit sac_fly bb ibb \
    hbp so wild_pitch balk runs earned_runs updated_at
  sync_box_game_detail
  sync_box_game_scoreboard
  sync_box_game_livelog
  # 進階快照：父子表 + gating pointer 原子同步（見檔首 sync_advanced_snapshot）。
  # 取代舊 sync_table advanced_stats（RECONCILE1 後 FK 失敗 + gating 濾除既有列）。
  sync_advanced_snapshot
  # ⚠️ 欄位清單必須涵蓋所有非 PK 欄。sync_table 是 `INSERT … ON CONFLICT DO UPDATE SET <清單>`：
  # 漏列的欄只在生產端「首次插入」時帶上，之後永不更新。2026-09-23 實測：本清單寫於
  # 2026-06-17（5fe07703），其後 migration 新增的 19 欄（軌跡、球種推算、落點）全漏——
  # 7/08 後插入生產的逐球，pitch_type_pred／_v2 在生產上一律 NULL，本機重跑推算也帶不上去。
  sync_box_pitch_tracking
  # 逐場逐投手官方旗標（migration 073；救援成功／失敗等，與逐球同一個單場請求寫入）。
  # ⚠️ 表由 073 建立：生產端的 migration 用已部署的 prod_cpbl_api 映像執行，主站未部署
  # 含 073 的映像前，這一行會因生產端無此表而失敗——依 Runbook 先部署再同步。
  sync_box_pitching_game_flags
  sync_box_batting_gamelog
  sync_box_pitching_gamelog
  # 官方 box 逐投手快照（#344；與 gamelog 同一個單場請求寫入）：只有 identity id、無內容唯一鍵，
  # 故整表鏡像（見 mirror_table）。
  mirror_table box_pitching_revisions identity
  # canonical PA build（INGEST-PA-DAILY1）：衍生自上面剛同步的 game_livelog／pitch_tracking／
  # batting_gamelog／pitching_gamelog，故放在其後；逐場增量替換＋全族對帳見 sync_pa_build（#353）。
  sync_pa_build
  # 隊伍比較摘要（#287 S06）：衍生自本機 gamelog（每日鏈 builder 已在爬取後建置），故排在 gamelog
  # 同步之後。insert-only＋單交易＋事後對帳在 Python 模組；整庫備份已於 2/4 完成。
  # ⛔ 失敗只記錄、不擋其他同步（production 尚無三表時為 exit 69，待部署窗口；舊摘要保留標待更新）。
  echo "    + 隊伍比較摘要（insert-only；失敗只記錄、不擋其他同步）"
  if team_comparison_sync apply; then
    :
  else
    echo "    ⚠ 隊伍比較摘要同步未完成 exit=$?（只記錄，不擋其他同步；見上方訊息）" >&2
  fi
  sync_table batting_seasons "player_id,year,team_id" \
    team_name g pa ab rbi r h b1 b2 b3 hr tb so sb gidp sh sf bb ibb hbp cs go fo
  sync_table pitching_seasons "player_id,year,team_id" \
    team_name g gs gr cg sho nbb w l sv hld ip bf np h hr bb ibb hbp so wp bk r er go fo
  # 同一寫入者（cpbl-backfill-season）的守備表；#344 前只同步了打／投兩表。
  sync_table fielding_seasons "player_id,year,team_id,pos" team_name g tc po a e dp tp pb cs sb
fi
SYNC_DONE_AT="$(date +%s)"   # 3/4 寫入全部結束；freshness 檢查等 /api/info 快取在此之後換代

# 遠端跑訓練並**保留 trainer 的 exit code**。ssh 回傳的是遠端命令串最後一個指令的碼，
# 遠端 shell（登入 shell 可能是 sh／dash）沒有 pipefail，所以
# `docker exec ... | grep -v httpx | tail -N` 一律回 tail 的 0——trainer crash 也會被
# 當成功，流程照樣往下寫 refresh 成功標記，正是本腳本要避免的
# 「舊 artifact 配新特徵分布」（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。
# 不用 `set -o pipefail` 是因為 `grep -v` 在「全部行都被濾掉」時回 1，會製造假失敗；
# 改成先把輸出收進變數取回 rc，過濾只作用在顯示上。
remote_train() {
  local command="$1" lines="$2"
  ssh -o BatchMode=yes "$VPS" \
    "output=\$(${command} 2>&1); rc=\$?; printf '%s\n' \"\$output\" | grep -v httpx | tail -${lines}; exit \$rc"
}

# 取線上 /api/info（下方兩道 freshness 檢查共用）。
# ⚠️ 重試是刻意的（2026-09-23）：這兩道檢查緊接在上面兩次 VPS 訓練之後，而 VPS 只有
# 1 vCPU／950MB RAM——cpbl API 平時約八成在 swap（swap 104MB、常駐 23MB），同步與訓練期間
# swap-in 約 800–1,150 頁/s（sar 10 分鐘平均），部署時可達 9,814 頁/s。重工作後的第一個請求
# 得等換頁回來：09-23 22:07:57（CST）#190 部署後那次同步，10 秒內一個位元組都沒收到，
# 整條同步以失敗結束，而資料其實早已寫完。平常容器內量 /api/info 只要 0.05s。
# 只重試暫時性錯誤（curl --retry 的定義：逾時、HTTP 408／429／500／502／503／504）；
# 拿到回應後的內容比對失敗（verify_refresh_info.py）不重試、照樣讓同步失敗——
# ⛔ 重試只吸收主機暫時卡住，不得拿來蓋過資料不一致。最壞耗時 4×20s＋3×15s＝125s。
fetch_api_info() {
  curl -fsS --retry 3 --retry-delay 15 --max-time 20 "$API_INFO_URL"
}

# 正式站 serving artifact 的訓練上界季（#364 §3.5）。用現行部署映像既有的函式讀，不依賴新碼部署；
# 讀不到（無 artifact、舊格式、ssh／python 失敗）一律印空字串 → 呼叫端照跑（fail open）。
remote_simple_trained_through() {
  ssh -o BatchMode=yes "$VPS" \
    "docker exec prod_cpbl_api python -c 'from cpbl.api.pregame_serving import artifact_path
from cpbl.models.outcome_simple import load_artifact
p = artifact_path()
print(load_artifact(p).get(\"trained_through\", \"\") if p.exists() else \"\")' 2>/dev/null" 2>/dev/null \
    | tail -n 1 || true
}

echo "==> 4/4 VPS 跑賽事預測回測（LightGBM 需 libgomp；prod_cpbl_api 容器內有）"
# game_features 已由本機鏡像（全史），VPS 不需再 build-features；直接以鏡像資料跑
# 走查回測並把 model_versions(task='outcome') 持久化，供 /api/info 與 /predict 面板展示。
if [ "$RUN_OUTCOME" = 1 ]; then
  # 基準就是 trainer 寫進正式站的 model_versions 本身，不另記本機狀態（#364 審核 F1）。
  remote_train "docker exec prod_cpbl_api cpbl-train-outcome" 4
else
  echo "    ⏭ 略過 cpbl-train-outcome（§3.5 訓練閘門：${OUTCOME_REASON}；model_versions 不新增）"
fi

# 上線 serving 模型（首頁 pregame 點機率／/methodology#pregame）也吃 game_features。
# 少了這一步，鏡像進來的新特徵分布會被餵給用舊分布 fit 的 outcome_simple.joblib，
# 屬 serving 端分布錯配（ML-OUTCOME-SIMPLE-LEAK2）。閘門未過時它不更新 artifact 而是
# 沿用上一版，API 會回報 serving_previous，首頁與方法頁據此如實揭露降級。
# #364 §3.5：trainer 只訓練到去年（trained_through=今年−1），季內每天重訓沒有新輸入；
# 只在正式站 artifact 的訓練上界季 < 今年−1（每年第一次）才跑。以資料判斷，不寫死日曆。
if [ "$RUN_SIMPLE" = auto ]; then
  SIMPLE_THROUGH="$(remote_simple_trained_through)"
  if [[ "$SIMPLE_THROUGH" =~ ^[0-9]{4}$ ]] && [ "$SIMPLE_THROUGH" -ge "$PREV" ]; then
    RUN_SIMPLE=0
    SIMPLE_REASON="正式站 artifact trained_through=${SIMPLE_THROUGH} ≥ 今年−1=${PREV}"
  else
    RUN_SIMPLE=1
    SIMPLE_REASON="正式站 artifact trained_through=${SIMPLE_THROUGH:-讀不到} → 照跑"
  fi
else
  SIMPLE_REASON="${OUTCOME_REASON}"
fi
if [ "$RUN_SIMPLE" = 1 ]; then
  echo "    + 重訓 outcome_simple（賽前勝率 serving 模型；閘門未過則保留舊 artifact）"
  remote_train "docker exec prod_cpbl_api cpbl-train-outcome-simple" 7
else
  echo "    ⏭ 略過 cpbl-train-outcome-simple（§3.5 訓練閘門：${SIMPLE_REASON}）"
fi

echo "    + 對帳 production 真實資料 freshness"
wait_api_info_cache_since "$SYNC_DONE_AT"
fetch_api_info \
  | python3 "$REPO_DIR/scripts/verify_refresh_info.py" --data-only \
      --expected-last-game-date "$EXPECTED_LAST_GAME_DATE" \
      --expected-season-games-completed "$EXPECTED_COMPLETED"

echo "    + 寫入 production refresh 成功標記"
ssh -o BatchMode=yes "$VPS" \
  "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec prod_pg psql -v ON_ERROR_STOP=1 -q \
    -U \"\$DB_USER\" -d \"\$DB_NAME\" -c \"INSERT INTO cpbl.refresh_log \
    (scope, from_date, to_date, detail, ok, note) VALUES \
    ('prod-sync', CURRENT_DATE, CURRENT_DATE, jsonb_build_object('source', 'local-refresh'), true, \
    'local-to-production sync completed')\""

MARKER_AT="$(date +%s)"

echo "    + 驗證 production API freshness"
wait_api_info_cache_since "$MARKER_AT"
fetch_api_info \
  | python3 "$REPO_DIR/scripts/verify_refresh_info.py" --max-age-minutes 15 \
      --expected-last-game-date "$EXPECTED_LAST_GAME_DATE" \
      --expected-season-games-completed "$EXPECTED_COMPLETED"

echo "==> 完成。線上資料已更新且 freshness 驗證通過。"
