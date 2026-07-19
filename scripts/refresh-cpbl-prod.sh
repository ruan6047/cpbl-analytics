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

echo "==> 2/4 備份 production cpbl schema"
BACKUP_PATH="$(VPS="$VPS" DEPLOY_PATH="$DEPLOY_PATH" "$REPO_DIR/scripts/backup-cpbl-prod.sh")"
echo "    ✓ 已驗證備份：${BACKUP_PATH}"

echo "==> 3/4 套用 prod migration + 非破壞性 upsert 同步"
# 同步前先讓 prod 套用任何新 migration（否則新欄位不存在、COPY 對不上）
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api python -c "from cpbl.db import migrate; print(\"migrated:\", migrate())"'

sync_table games "year,kind_code,game_season_code,game_sno" \
  game_date present_status venue home_team_code home_team_name away_team_code away_team_name \
  home_score away_score home_starter_id away_starter_id winning_pitcher_id losing_pitcher_id closer_id mvp_id \
  delay_kind orig_date
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
  sync_table advanced_stats "year,kind_code,acnt,role" \
    pa woba woba_pr ba ba_pr slg slg_pr iso iso_pr obp obp_pr brl brl_pr brlp brlp_pr ev ev_pr \
    max_ev max_ev_pr hardhitp hardhitp_pr kp kp_pr bbp bbp_pr whiffp whiffp_pr chasep chasep_pr
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
  sync_table batting_seasons "player_id,year,team_id" \
    team_name g pa ab rbi r h b1 b2 b3 hr tb so sb gidp sh sf bb ibb hbp cs go fo
  sync_table pitching_seasons "player_id,year,team_id" \
    team_name g gs gr cg sho nbb w l sv hld ip bf np h hr bb ibb hbp so wp bk r er go fo
fi

echo "==> 4/4 VPS 跑賽事預測回測（LightGBM 需 libgomp；prod_cpbl_api 容器內有）"
# game_features 已由本機鏡像（全史），VPS 不需再 build-features；直接以鏡像資料跑
# 走查回測並把 model_versions(task='outcome') 持久化，供 /api/info 與 /predict 面板展示。
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api cpbl-train-outcome 2>&1 | grep -v httpx | tail -4'

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
