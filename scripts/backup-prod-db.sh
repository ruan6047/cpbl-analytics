#!/usr/bin/env bash
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
# 備份並驗證整個 production 資料庫（alpha_db：cpbl schema ＋ 主站 public schema）；
# stdout 只輸出備份路徑。任何 production migration/upsert 前都應先跑這支。
#
# 為什麼備整庫而不只 cpbl（OPS-BACKUP-EMPTY1，2026-07-31）：alpha_db 為兩專案共用，
# 主站 public 的 18 張表（users／blog_posts／media／projects／work_experiences…）
# 在 VPS cron 壞掉的期間完全沒有備份覆蓋。實測整庫壓縮後只比 cpbl-only 大
# 633,869 bytes（+0.26%），近乎零成本換到全庫覆蓋，故不再分 schema 備份。
#
# 為什麼由這台 Mac 跑而不是 VPS cron：備份與 DB 放同一台主機是弱設計（主機損失即
# 兩者俱失）；本機相對 production DB 本身即異地。VPS 上原本的 infra/scripts/backup-db.sh
# cron 因憑證預設值錯誤連續 86 天產出 20-byte 空檔且無人知情，已停用——一個持續
# 產出「看起來像成功」產物的機制，比沒有機制更危險。
#
# 失敗語意：任一步失敗都非零退出且 **不留下任何產物**（trap 清 .partial）。呼叫端
# refresh-cpbl-prod.sh 會因此非零退出，狀態落入 logs/last-status.json——本專案的
# 告警模型是機器可讀狀態檔供人／AI 每日查，不另設推播管道。
set -euo pipefail

# ============================================================== argv 守衛
# 這一段必須留在檔案最前面、任何副作用之前——往下移就等於沒有。
#
# 為什麼（實測，非讀碼推斷；副本 ＋ 假樁，版控樹上未執行）：
#   `backup-prod-db.sh --help` 當場送出 `ssh -o BatchMode=yes <VPS> … docker exec
#   prod_pg pg_dump …`——整庫 dump 對**生產**發出，argv 從頭到尾沒有人看。
#   假樁改成會成功後再跑一次：**exit 0、產出一份備份、並把 7 份輪替視窗中最舊的
#   那份 `rm -f` 掉**（08-08 消失、08-15 補進來）。
#
# 所以這一支的傷害不是「跑起來很慢」，是**探索動作會吃掉歷史深度**：連打七次
# `--help`，整個保留視窗就塌成同一天的七份副本，而每一次都 exit 0、看起來像成功。
# 那正是 OPS-BACKUP-EMPTY1 的教訓（失敗會留下看起來像成功的產物）換一個方向重演。
#
# 清冊原本沒擋住它：不變式 4 的判準是「判定為**寫入型**」＝對 **DB** 有寫入，而本
# 腳本 `pg_dump` 對 DB 唯讀，於是 README 印著「⚠️ --help 不安全」卻沒有任何強制路徑。
# 判準已隨本次修正加寬為「高後果」（寫 DB **或**接觸遠端生產主機 **或**不可逆刪檔）。
#
# 想知道它在做什麼的人應該拿到答案，所以 `--help` 印用法並 exit 0，不是 exit 1。
# 未知參數則拒絕（exit 64＝EX_USAGE，與本檔既有的參數錯誤同碼）。
usage() {
  cat <<'EOF'
scripts/backup-prod-db.sh — 備份並驗證整個 production 資料庫（alpha_db）

在做什麼
  1/3  ssh 進 production 主機，對 prod_pg 跑整庫 pg_dump（cpbl schema ＋ 主站 public）
  2/3  驗內容門檻：解壓後的 CREATE TABLE 數與位元組數都要過門檻，否則中止且不留產物
  3/3  晉升為正式備份，然後把超出保留份數的**最舊備份刪掉**

會寫什麼（⚠️ 沒有 dry-run）
  · 本機檔案系統：BACKUP_DIR 下新增一份 .sql.gz（整庫約 240 MB）
  · 本機檔案系統：**rm -f 掉最舊的備份**，只保留最近 BACKUP_KEEP 份
  · production：唯讀（pg_dump），但會對生產 DB 施加一次整庫 dump 的負載
  不要拿這一支來「跑跑看會發生什麼」——每跑一次就少一天的歷史深度。

怎麼呼叫（不接受位置參數，設定一律走環境變數）
  ./scripts/backup-prod-db.sh                    # stdout 只輸出備份路徑
  BACKUP_KEEP=14 ./scripts/backup-prod-db.sh     # 加大保留視窗
  由 refresh-cpbl-prod.sh 在同步生產前自動呼叫，一般不需要自己跑

環境變數
  VPS                production 主機的 ssh 目標
  DEPLOY_PATH        production 主機上的部署目錄
  BACKUP_DIR         備份存放目錄（預設 ~/Library/Application Support/cpbl-analytics/backups）
  BACKUP_KEEP        保留份數，正整數（預設 7）
  BACKUP_MIN_TABLES  內容門檻：CREATE TABLE 數下限（預設 90）
  BACKUP_MIN_BYTES   內容門檻：解壓後位元組下限（預設 100000000）

離開碼
  0 成功 · 64 參數錯 · 66 備份內容未達門檻（產物已清除）

背景：docs/archive/tasks/OPS-BACKUP-EMPTY1.md（為什麼備整庫、為什麼驗內容）
EOF
}

if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '未知參數：%s\n' "$1" >&2
      printf '本腳本不接受位置參數，設定一律走環境變數；用法請打 --help。\n' >&2
      exit 64
      ;;
  esac
fi

VPS="${VPS:-root@45.76.100.29}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/personal-website}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/Library/Application Support/cpbl-analytics/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
# 內容門檻：只驗 gzip 完整性不夠——空 dump 也是合法的 gzip 串流（VPS cron 那 86 份
# 20-byte 檔正是如此，每一份都能通過 gzip -t）。故解壓後另驗 CREATE TABLE 數與位元組數。
BACKUP_MIN_TABLES="${BACKUP_MIN_TABLES:-90}"
BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-100000000}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/alphadb-prod-${STAMP}-$$.sql.gz"
PARTIAL_PATH="${BACKUP_PATH}.partial.$$"

for var in BACKUP_KEEP BACKUP_MIN_TABLES BACKUP_MIN_BYTES; do
  eval "value=\$$var"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "${var} 必須是正整數（got: ${value}）" >&2
    exit 64
  fi
done

mkdir -p "$BACKUP_DIR"
trap 'rm -f "$PARTIAL_PATH"' EXIT

ssh -o BatchMode=yes "$VPS" \
  "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec prod_pg pg_dump \
    -U \"\$DB_USER\" -d \"\$DB_NAME\" --clean --if-exists --no-owner" \
  | gzip -c > "$PARTIAL_PATH"

test -s "$PARTIAL_PATH"
gzip -t "$PARTIAL_PATH"

# 單次解壓同時取兩個指標，避免走兩趟 240MB。
# LC_ALL=C 釘住位元組語意：POSIX 允許 awk 的 length() 在 UTF-8 locale 下回傳字元數，
# 屆時「bytes」門檻量到的就不是 bytes。macOS 的 awk 實測兩種 locale 皆回位元組
# （含中文字串驗證過），故此處是可攜性保險而非修正既有缺陷；GNU awk 行為不同。
VERIFY="$(gunzip -c "$PARTIAL_PATH" \
  | LC_ALL=C awk '/^CREATE TABLE /{t++} {b+=length($0)+1} END{printf "%d %d", t+0, b+0}')"
TABLES="${VERIFY%% *}"
BYTES="${VERIFY##* }"

if [ "$TABLES" -lt "$BACKUP_MIN_TABLES" ]; then
  echo "備份內容驗證失敗：CREATE TABLE ${TABLES} < 門檻 ${BACKUP_MIN_TABLES}" >&2
  exit 66
fi
if [ "$BYTES" -lt "$BACKUP_MIN_BYTES" ]; then
  echo "備份內容驗證失敗：解壓後 ${BYTES} bytes < 門檻 ${BACKUP_MIN_BYTES}" >&2
  exit 66
fi

mv "$PARTIAL_PATH" "$BACKUP_PATH"
trap - EXIT
echo "已驗證備份：tables=${TABLES} uncompressed_bytes=${BYTES}" >&2

# 只在新備份完整晉升後才清理。同時納入舊前綴 cpbl-prod-*（改名前的 cpbl-only 備份），
# 讓它們隨輪替自然淘汰；排序鍵取檔名中 `-prod-` 之後的時間戳，故與前綴無關。
CLEANUP_LIST="$(
  for f in "$BACKUP_DIR"/alphadb-prod-*.sql.gz "$BACKUP_DIR"/cpbl-prod-*.sql.gz; do
    [ -e "$f" ] || continue
    base="${f##*/}"
    printf '%s\t%s\n' "${base#*-prod-}" "$f"
  done | sort -t"$(printf '\t')" -k1,1
)"

TOTAL=0
while IFS= read -r line; do
  [ -n "$line" ] && TOTAL=$((TOTAL + 1))
done <<< "$CLEANUP_LIST"

REMOVE_COUNT=$((TOTAL - BACKUP_KEEP))
if [ "$REMOVE_COUNT" -gt 0 ]; then
  removed=0
  while IFS=$'\t' read -r _stamp path; do
    [ -n "$path" ] || continue
    [ "$removed" -lt "$REMOVE_COUNT" ] || break
    rm -f "$path"
    removed=$((removed + 1))
  done <<< "$CLEANUP_LIST"
fi

printf '%s\n' "$BACKUP_PATH"
