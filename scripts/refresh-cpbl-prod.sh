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
        "cd ${DEPLOY_PATH} && set -a && . ./.env && docker exec -i prod_pg psql -q --single-transaction -U \"\$DB_USER\" -d \"\$DB_NAME\""
  echo "    ✓ ${t}"
}

cd "$REPO_DIR"
# SKIP_SCRAPE=1：本機 DB 已是最新時，跳過重爬、直接把現有資料同步到 prod。
if [ -n "${SKIP_SCRAPE:-}" ]; then
  echo "==> 1/3 略過爬取（SKIP_SCRAPE），直接同步本機現有資料"
else
  echo "==> 1/3 本機（台灣 IP）爬最新資料"
  uv run cpbl-scrape-games "$YEAR" "$YEAR"
  uv run cpbl-scrape-stats "$PREV" "$YEAR"

  # 選手細項（投打對決 / 對戰各隊 / 分項）變動慢且耗時逾 1 小時，預設不跑；
  # 需要時以 WITH_DETAIL=1 觸發（每隔幾週跑一次即可）。
  if [ -n "${WITH_DETAIL:-}" ]; then
    echo "    + 選手細項（耗時較長：投打對決生涯 + 對戰各隊 + 分項）"
    uv run cpbl-scrape-fighting 9999 1.2 cur
    uv run cpbl-scrape-detail 1.2
  fi
fi

echo "==> 2/3 套用 prod migration + 非破壞性 upsert 同步"
# 同步前先讓 prod 套用任何新 migration（否則新欄位不存在、COPY 對不上）
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api python -c "from cpbl.db import migrate; print(\"migrated:\", migrate())"'

sync_table games "year,kind_code,game_season_code,game_sno" \
  game_date present_status venue home_team_code home_team_name away_team_code away_team_name \
  home_score away_score home_starter_id away_starter_id winning_pitcher_id losing_pitcher_id closer_id mvp_id
sync_table pitching_current "year,player_id" name team_code era ip g gs w l whip k9 fip era_plus sv hld \
  so cg sho pa np h hr bb ibb hbp wp bk r er go ao goao
sync_table batting_current "year,player_id" name team_code pa avg obp slg ops hr ops_plus k_pct bb_pct \
  g ab r h b2 b3 rbi bb so sb cs tb gidp sh sf ibb hbp go ao goao
sync_table fielding_current "year,player_id,pos" name team_code g tc po a e dp fpct
sync_table team_current "year,team_code" name bat_avg bat_obp bat_slg bat_ops bat_hr pit_era pit_whip
sync_table team_standings "year,kind_code,season_code,team_code" \
  team_name rank g w t l win_pct gb elim home_record away_record streak last10 h2h

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
  sync_table batting_splits "year,kind_code,acnt,item_group_code,item_index" \
    item_name item_note plate_appearances at_bats hits rbi singles doubles triples home_runs total_bases \
    sac_hit sac_fly bb ibb hbp so ground_outs fly_outs goao avg obp slg ops
  sync_table pitching_splits "year,kind_code,acnt,item_group_code,item_index" \
    item_name item_note wins loses starts complete_games shutouts save_ok inning_pitched_cnt \
    inning_pitched_div3 plate_appearances pitch_cnt strikes balls hits home_runs sac_hit sac_fly bb ibb \
    hbp so wild_pitch balk runs earned_runs
  sync_table game_scoreboard "year,kind_code,game_sno,team_no,inning_seq" \
    visiting_home_type team_name score_cnt hitting_cnt error_cnt
  sync_table game_livelog "year,kind_code,game_sno,main_event_no" \
    inning_seq visiting_home_type batting_order out_cnt ball_cnt strike_cnt pitch_cnt content \
    action_name batting_action_name defend_station_code hitter_acnt hitter_name pitcher_acnt \
    pitcher_name catcher_acnt catcher_name first_base second_base third_base is_strike is_ball \
    is_score is_change_player is_special_event visiting_score home_score
  sync_table advanced_stats "year,acnt,role" \
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

echo "==> 3/3 VPS 重建賽果特徵"
ssh -o BatchMode=yes "$VPS" 'docker exec prod_cpbl_api cpbl-build-features 2>&1 | grep -v httpx | tail -1'

echo "==> 完成。線上資料已更新。"
