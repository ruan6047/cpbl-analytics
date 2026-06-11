#!/usr/bin/env bash
# CPBL 線上資料手動更新（不掛 cron，避免浪費資源；要更新時自己跑）。
#
# 為什麼要在本機跑：CPBL 官網（HiNetCDN）對海外 IP 封鎖資料路徑，VPS 爬不到，
# 只有台灣 IP（你的 Mac）能爬。故流程＝本機爬 → 非破壞性 upsert 同步到 prod →
# VPS 重建賽果特徵（build-features 只讀 DB，VPS 可跑）。
#
# 用法：./scripts/refresh-cpbl-prod.sh
#
# 可用環境變數覆蓋：LOCAL_DB / VPS / DEPLOY_PATH
set -euo pipefail

LOCAL_DB="${LOCAL_DB:-cpbl-analytics-db-1}"
VPS="${VPS:-root@45.76.100.29}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/personal-website}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
YEAR="$(date +%Y)"
PREV="$((YEAR - 1))"

# 各表 → conflict 鍵 + 要 upsert 的欄位
declare -A PK=(
  [games]="year,kind_code,game_season_code,game_sno"
  [pitching_current]="year,player_id"
  [batting_current]="year,player_id"
  [team_current]="year,team_code"
)
declare -A COLS=(
  [games]="game_date present_status venue home_team_code home_team_name away_team_code away_team_name home_score away_score home_starter_id away_starter_id winning_pitcher_id losing_pitcher_id closer_id mvp_id"
  [pitching_current]="name team_code era ip g gs w l whip k9 fip era_plus"
  [batting_current]="name team_code pa avg obp slg ops hr ops_plus k_pct bb_pct"
  [team_current]="name bat_avg bat_obp bat_slg bat_ops bat_hr pit_era pit_whip"
)

echo "==> 1/3 本機（台灣 IP）爬最新資料"
cd "$REPO_DIR"
uv run cpbl-scrape-games "$YEAR" "$YEAR"
uv run cpbl-scrape-stats "$PREV" "$YEAR"

echo "==> 2/3 非破壞性 upsert 同步到 prod"
for t in games pitching_current batting_current team_current; do
  set_clause=""
  for c in ${COLS[$t]}; do set_clause+="${c}=EXCLUDED.${c},"; done
  set_clause="${set_clause%,}"
  {
    echo "CREATE TEMP TABLE _stg (LIKE cpbl.${t} INCLUDING DEFAULTS) ON COMMIT DROP;"
    docker exec "$LOCAL_DB" pg_dump -U cpbl -d cpbl --data-only -t "cpbl.${t}" \
      | sed "s/^COPY cpbl\.${t} /COPY _stg /"
    echo "INSERT INTO cpbl.${t} SELECT * FROM _stg ON CONFLICT (${PK[$t]}) DO UPDATE SET ${set_clause};"
  } | ssh -o BatchMode=yes "$VPS" \
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\""
  echo "    ✓ ${t}"
done

echo "==> 3/3 VPS 重建賽果特徵"
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api cpbl-build-features 2>&1 | grep -v httpx | tail -1'

echo "==> 完成。線上資料已更新。"
