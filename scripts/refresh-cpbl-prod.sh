#!/usr/bin/env bash
# CPBL 線上資料手動更新（不掛 cron，避免浪費資源；要更新時自己跑）。
#
# 為什麼要在本機跑：CPBL 官網（HiNetCDN）對海外 IP 封鎖資料路徑，VPS 爬不到，
# 只有台灣 IP（你的 Mac）能爬。故流程＝本機爬 → 非破壞性 upsert 同步到 prod →
# VPS 重建賽果特徵（build-features 只讀 DB，VPS 可跑）。
#
# 用法：./scripts/refresh-cpbl-prod.sh
#       WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh                 # 連同選手細項（耗時逾 1 小時）
#       SKIP_SCRAPE=1 WITH_DETAIL=1 ./scripts/refresh-cpbl-prod.sh   # 本機已最新：只同步不重爬
#
# 可用環境變數覆蓋：LOCAL_DB / VPS / DEPLOY_PATH / WITH_DETAIL / SKIP_SCRAPE
set -euo pipefail

LOCAL_DB="${LOCAL_DB:-cpbl-analytics-db-1}"
VPS="${VPS:-root@45.76.100.29}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/personal-website}"
API_INFO_URL="${API_INFO_URL:-https://cpbl.ruan-ruan.com/api/info}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
YEAR="$(date +%Y)"
PREV="$((YEAR - 1))"

# 非破壞性同步一張表（bash 3.2 相容，不用關聯陣列）：$1=表 $2=conflict鍵 其餘=upsert欄位
sync_table() {
  local t="$1" pk="$2"; shift 2
  local set_clause=""
  local c
  for c in "$@"; do set_clause="${set_clause}${c}=EXCLUDED.${c},"; done
  set_clause="${set_clause%,}"
  {
    echo "CREATE TEMP TABLE _stg (LIKE cpbl.${t} INCLUDING DEFAULTS) ON COMMIT DROP;"
    docker exec "$LOCAL_DB" pg_dump -U cpbl -d cpbl --data-only -t "cpbl.${t}" \
      | sed -e "s/^COPY cpbl\.${t} /COPY _stg /" -e '/^\\restrict /d' -e '/^\\unrestrict /d'
    echo "INSERT INTO cpbl.${t} SELECT * FROM _stg ON CONFLICT (${pk}) DO UPDATE SET ${set_clause};"
  } | ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
          -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\""
  echo "    ✓ ${t}"
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

# canonical PA build 家族原子同步（INGEST-PA-DAILY1；migrations/066_game_recap_pa_expand.sql；
# TRUNCATE+全量重灌改法見 INGEST-PA-DAILY1-FIX1／Issue #88）。
# 為何不能用通用 sync_table：
#   1) game_recap_source_revisions/game_plate_appearances/game_pa_events/game_pa_pitch_mappings
#      四表 PK 皆 GENERATED ALWAYS AS IDENTITY 代理鍵，INSERT 帶入 pg_dump 匯出的既有值
#      需 OVERRIDING SYSTEM VALUE（同 advanced_ingest_runs 前例）；game_recap_builds 的
#      build_id 是 builder 產生的 uuid（非 identity），走一般 INSERT 即可。
#   2) 四表彼此 FK 相依（source_revisions ← builds ← plate_appearances ← pa_events／
#      pitch_mappings；source_revisions 同時被 pitch_mappings 直接參照），INSERT 必須
#      同一 --single-transaction 依此順序灌入，否則 FK 失敗。
# id 值直接鏡像本機、不重新分配：本卡「不部署」——cpbl-refresh-recent 只在本機跑，
# prod 從不獨立寫入這五張表（唯一 writer 是本同步腳本），故無 prod 自產 identity 與
# 匯入值碰撞風險，與 advanced_ingest_runs「本機↔prod run id 語意已對齊」同一理由。
#
# 為何改 TRUNCATE 而非 ON CONFLICT upsert（FIX1 根因，首次真實生產同步實測炸裂）：
# 2026-08-03 有一次一次性 ad-hoc 手動同步（見 INGEST-PA-DAILY1.md Log），對 prod 留下
# 「內容相同、id 不同」的 game_recap_source_revisions 舊列。舊版 ON CONFLICT (id) 對不到
# 那些列（衝突鍵是 id，來源 id 與舊列 id 不同→不觸發 UPDATE），退回一般 INSERT 又撞上
# (year,kind_code,game_sno,source_kind,source_sha256) 內容唯一鍵
# （game_recap_source_revisions_year_kind_code_game_sno_source__key）→ 整個
# --single-transaction 回滾（prod 未污染，仍是同步前狀態）。只要 prod 曾有任何一次
# id 與本機不同步的手動寫入，同一 class 的錯誤就會再發生；TRUNCATE 徹底消滅 id 漂移
# 殘留列，是唯一能讓「每日全量重灌」真正對 id 漂移免疫的作法（比照下方 game_features
# 既有 TRUNCATE 先例，理由相同：derived 資料、prod 非獨立 writer，可安全整表重建）。
#
# 五表在同一條 TRUNCATE 陳述式內列出（非個別五條）：Postgres 只要求「被參照表與參照表
# 同時出現在同一 TRUNCATE 命令」，不檢查列出順序，故不需要 CASCADE（CASCADE 會波及
# 「未列出但仍參照這 5 表的其他表」，此處刻意不用、以免意外波及未知表）。已逐一 grep
# 全部 migrations 確認：除這 5 表彼此互相參照外，沒有其他表對它們建 FK
# （見 INGEST-PA-DAILY1-FIX1 驗證留痕），故列出這 5 張即完整覆蓋。
# TRUNCATE 與其後 INSERT 同在一個 --single-transaction 內（非分兩次呼叫，與下方
# game_features 前例的兩段式不同——PA 家族有跨表 FK、blast radius 較大，要求更嚴格的
# 原子性）：中途任何一步失敗即整體回滾，prod 維持同步前原狀，不留半殘表。
# 不需要 RESTART IDENTITY：所有列都以 OVERRIDING SYSTEM VALUE 明確帶入本機 id，
# 序列本身的下一個值從不被讀取（prod 對這 5 表從不自行 INSERT）。
#
# ON CONFLICT 子句已移除（不是遺漏）：TRUNCATE 與 INSERT 同一交易內，INSERT 執行時
# 目標表保證清空，不可能真的觸發衝突；留著舊 ON CONFLICT (id) 只會誤導讀者以為這裡
# 仍是「增量 upsert」語意——那正是本次事故的根因（id 對不上舊列、退回撞內容唯一鍵）。
# 若未來要改回非 TRUNCATE 的增量同步，須重新設計 conflict 鍵（比照本機 pa_build 寫入
# 契約逐表另行論證），不能只是加回這裡移除的舊子句。
sync_pa_build() {
  {
    echo "TRUNCATE cpbl.game_recap_source_revisions, cpbl.game_recap_builds, cpbl.game_plate_appearances, cpbl.game_pa_events, cpbl.game_pa_pitch_mappings;"
    _stage game_recap_source_revisions _pa_rev
    echo "INSERT INTO cpbl.game_recap_source_revisions OVERRIDING SYSTEM VALUE SELECT * FROM _pa_rev;"
    _stage game_recap_builds _pa_build
    echo "INSERT INTO cpbl.game_recap_builds SELECT * FROM _pa_build;"
    _stage game_plate_appearances _pa_pa
    echo "INSERT INTO cpbl.game_plate_appearances OVERRIDING SYSTEM VALUE SELECT * FROM _pa_pa;"
    _stage game_pa_events _pa_ev
    echo "INSERT INTO cpbl.game_pa_events OVERRIDING SYSTEM VALUE SELECT * FROM _pa_ev;"
    _stage game_pa_pitch_mappings _pa_map
    echo "INSERT INTO cpbl.game_pa_pitch_mappings OVERRIDING SYSTEM VALUE SELECT * FROM _pa_map;"
  } | ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql \
          -v ON_ERROR_STOP=1 -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\""
  echo "    ✓ canonical PA build（TRUNCATE + 全量重灌：source_revisions/builds/plate_appearances/pa_events/pitch_mappings 原子同步）"
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
# 為何也不比照 sync_pa_build 用 TRUNCATE 全量重灌：那五表是可由 livelog 重算的 derived
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
# `sync_pa_build`／`sync_advanced_snapshot` 續用 `_stage`、**不得**改用 `_stage_noseq`：
# 那兩者以 `OVERRIDING SYSTEM VALUE` 明確鏡像本機 id，dump 的 setval 在那裡是**對的**。

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

cd "$REPO_DIR"
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
echo "    + 重建 game_features（賽事預測特徵，全史 kind A）"
uv run cpbl-build-features 2>&1 | tail -1

# 記住本機真實賽事 freshness；同步後 API 必須回報相同值，不能只靠腳本自寫 marker。
# 由 Python contract 產生 SQL，避免同步 gate 與 API 各自複製 completed 語意。
COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion)"
LOCAL_FRESHNESS="$(docker exec "$LOCAL_DB" psql -U cpbl -d cpbl -At -F '|' -c \
  "SELECT COALESCE(max(game_date) FILTER (WHERE ${COMPLETED_GAMES_SQL})::text, ''), \
          count(*) FILTER (WHERE year = ${YEAR} AND ${COMPLETED_GAMES_SQL}) \
   FROM cpbl.games")"
IFS='|' read -r EXPECTED_LAST_GAME_DATE EXPECTED_COMPLETED <<< "$LOCAL_FRESHNESS"
if [ -z "$EXPECTED_LAST_GAME_DATE" ] || ! [[ "$EXPECTED_COMPLETED" =~ ^[0-9]+$ ]]; then
  echo "FATAL: 無法取得本機 freshness 基準：${LOCAL_FRESHNESS}" >&2
  exit 65
fi

echo "==> 2/4 備份 production 資料庫（整庫：cpbl ＋ 主站 public）"
BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" "$REPO_DIR/scripts/backup-prod-db.sh")"
echo "    ✓ 已驗證備份：${BACKUP_PATH}"

echo "==> 3/4 套用 prod migration + 非破壞性 upsert 同步"
# 同步前先讓 prod 套用任何新 migration（否則新欄位不存在、COPY 對不上）
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api python -c "from cpbl.db import migrate; print(\"migrated:\", migrate())"'

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
sync_table pitching_current "year,player_id" name team_code era ip g gs w l whip k9 fip era_plus sv hld \
  so cg sho pa np h hr bb ibb hbp wp bk r er go ao goao
sync_table batting_current "year,player_id" name team_code pa avg obp slg ops hr ops_plus k_pct bb_pct \
  g ab r h b2 b3 rbi bb so sb cs tb gidp sh sf ibb hbp go ao goao
sync_table fielding_current "year,kind_code,player_id,pos" name team_code g tc po a e dp tp pb cs sba fpct
sync_table team_current "year,team_code" name bat_avg bat_obp bat_slg bat_ops bat_hr pit_era pit_whip
sync_table coaches "year,team_code,name" pos uniform_no
# 維基/官網參考資料（一次抓+手動刷新；非每日爬）：本機灌好後鏡像到 prod
sync_table managers "team_code,era_name,name,from_year" to_year g w l t win_pct postseason championships source
sync_table overseas "player_id,league,from_year" team source
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
  team_name rank g w t l win_pct gb elim home_record away_record streak last10 h2h

# 賽事預測特徵：完整鏡像（先 TRUNCATE 清掉 prod 舊版＝早期未過濾 kind 混入的二軍/季後列），
# 再把本機全史 kind A 特徵灌入。derived 資料，安全可重建。
ssh -o BatchMode=yes "$VPS" \
  "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -q -U \"\$DB_USER\" -d \"\$DB_NAME\" -c 'TRUNCATE cpbl.game_features'"
sync_table game_features "year,kind_code,game_season_code,game_sno" \
  game_date season home_team_code away_team_code home_team_name away_team_name home_win completed \
  winrate_diff prior_winpct_diff runs_scored_diff runs_allowed_diff recent_form_diff rest_days_diff \
  h2h_home home_field starter_era_diff starter_whip_diff starter_k9_diff \
  prior_team_ops_diff prior_team_slg_diff prior_team_era_diff prior_team_whip_diff \
  team_ops_now_diff team_avg_now_diff team_sb_now_diff team_wp_now_diff team_err_now_diff

if [ -n "${WITH_DETAIL:-}" ]; then
  sync_table batter_pitcher_matchups "year,kind_code,hitter_acnt,pitcher_acnt" \
    hitter_name pitcher_name hitter_team_no pitcher_team_no plate_appearances at_bats hits rbi \
    singles doubles triples home_runs total_bases avg obp slg ops sac_hit sac_fly bb ibb hbp so \
    ground_out fly_out goao strike_pct ball_pct swing_pct first_pitch_swing_pct whiff_pct gb_pct ld_pct fb_pct
  sync_table batting_vs_team "year,kind_code,acnt,fight_team_code" \
    fight_team_name team_no total_games plate_appearances at_bats hits rbi runs singles doubles triples \
    home_runs total_bases gidp sac_hit sac_fly bb ibb hbp so sb_ok sb_fail sb_pct avg obp slg ta ops
  sync_table pitching_vs_team "year,kind_code,acnt,fight_team_code" \
    fight_team_name team_no total_games starts closes complete_games shutouts wins loses save_ok save_fail \
    holds inning_pitched_cnt inning_pitched_div3 whip era plate_appearances pitch_cnt hits home_runs bb ibb \
    hbp so wild_pitch balk runs earned_runs
  sync_table batting_splits "year,kind_code,acnt,item_group_code,item_index,item_name" \
    item_note plate_appearances at_bats hits rbi singles doubles triples home_runs total_bases \
    sac_hit sac_fly bb ibb hbp so ground_outs fly_outs goao avg obp slg ops
  sync_table pitching_splits "year,kind_code,acnt,item_group_code,item_index,item_name" \
    item_note wins loses starts complete_games shutouts save_ok inning_pitched_cnt \
    inning_pitched_div3 plate_appearances pitch_cnt strikes balls hits home_runs sac_hit sac_fly bb ibb \
    hbp so wild_pitch balk runs earned_runs
  sync_table game_detail "year,kind_code,game_sno" \
    attendance game_time head_umpire first_umpire second_umpire third_umpire left_umpire right_umpire \
    weather_code weather_desc winning_type attendance_backend
  sync_table game_scoreboard "year,kind_code,game_sno,team_no,inning_seq" \
    visiting_home_type team_name score_cnt hitting_cnt error_cnt
  sync_table game_livelog "year,kind_code,game_sno,main_event_no" \
    inning_seq visiting_home_type batting_order out_cnt ball_cnt strike_cnt pitch_cnt content \
    action_name batting_action_name defend_station_code hitter_acnt hitter_name pitcher_acnt \
    pitcher_name catcher_acnt catcher_name first_base second_base third_base is_strike is_ball \
    is_score is_change_player is_special_event visiting_score home_score
  # 進階快照：父子表 + gating pointer 原子同步（見檔首 sync_advanced_snapshot）。
  # 取代舊 sync_table advanced_stats（RECONCILE1 後 FK 失敗 + gating 濾除既有列）。
  sync_advanced_snapshot
  sync_table pitch_tracking "year,kind_code,game_sno,pitcher_acnt,pitch_cnt" \
    pitcher_name hitter_acnt hitter_name inning_seq ball_cnt strike_cnt out_cnt batting_order content \
    pitch_call auto_pitch_type tagged_pitch_type rel_speed spin_rate rel_side rel_height extension \
    zone_speed plate_loc_side plate_loc_height hit_exit_speed hit_launch_angle hit_direction \
    hit_distance hit_hang_time
  sync_table batting_gamelog "year,kind_code,game_sno,hitter_acnt" \
    hitter_name visiting_home_type uniform_no role_type plate_appearances at_bats hits rbi runs \
    singles doubles triples home_runs grand_slam total_bases gidp sac_hit sac_fly bb ibb hbp so sb cs \
    lob errors gw_rbi is_mvp
  sync_table pitching_gamelog "year,kind_code,game_sno,pitcher_acnt" \
    pitcher_name visiting_home_type uniform_no role_type game_result is_complete_game is_shutout \
    inning_pitched_cnt inning_pitched_div3 plate_appearances pitch_cnt strike_cnt ball_cnt hits \
    home_runs sac_hit sac_fly bb ibb hbp so wild_pitch balk runs earned_runs relief_point max_speed is_mvp
  # canonical PA build（INGEST-PA-DAILY1）：衍生自上面剛同步的 game_livelog／pitch_tracking／
  # batting_gamelog／pitching_gamelog，故放在其後；父子表 FK 順序見檔首 sync_pa_build。
  sync_pa_build
  sync_table batting_seasons "player_id,year,team_id" \
    team_name g pa ab rbi r h b1 b2 b3 hr tb so sb gidp sh sf bb ibb hbp cs go fo
  sync_table pitching_seasons "player_id,year,team_id" \
    team_name g gs gr cg sho nbb w l sv hld ip bf np h hr bb ibb hbp so wp bk r er go fo
fi

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

echo "==> 4/4 VPS 跑賽事預測回測（LightGBM 需 libgomp；prod_cpbl_api 容器內有）"
# game_features 已由本機鏡像（全史），VPS 不需再 build-features；直接以鏡像資料跑
# 走查回測並把 model_versions(task='outcome') 持久化，供 /api/info 與 /predict 面板展示。
remote_train "docker exec prod_cpbl_api cpbl-train-outcome" 4

# 上線 serving 模型（首頁 pregame 點機率／/methodology#pregame）也吃 game_features。
# 少了這一步，鏡像進來的新特徵分布會被餵給用舊分布 fit 的 outcome_simple.joblib，
# 屬 serving 端分布錯配（ML-OUTCOME-SIMPLE-LEAK2）。閘門未過時它不更新 artifact 而是
# 沿用上一版，API 會回報 serving_previous，首頁與方法頁據此如實揭露降級。
echo "    + 重訓 outcome_simple（賽前勝率 serving 模型；閘門未過則保留舊 artifact）"
remote_train "docker exec prod_cpbl_api cpbl-train-outcome-simple" 7

echo "    + 對帳 production 真實資料 freshness"
curl -fsS --max-time 10 "$API_INFO_URL" \
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

echo "    + 驗證 production API freshness"
curl -fsS --max-time 10 "$API_INFO_URL" \
  | python3 "$REPO_DIR/scripts/verify_refresh_info.py" --max-age-minutes 15 \
      --expected-last-game-date "$EXPECTED_LAST_GAME_DATE" \
      --expected-season-games-completed "$EXPECTED_COMPLETED"

echo "==> 完成。線上資料已更新且 freshness 驗證通過。"
