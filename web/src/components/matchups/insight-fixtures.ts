// 洞察契約 fixtures（UX-MATCHUP1 驗收：四種 fail-closed 空狀態＋成功態＋角色翻轉）。
// 形狀取自本機真實 API 回應（2026-07-18 抽樣），數值节錄；供契約測試與
// /dev fixture 走查使用，不進 production 資料流。
import type { InsightsResponse } from "./api";

const METHOD_OK = {
  metric: "woba_generic_v1",
  baseline_source: "official_season_aggregates（全史，可驗證）",
  observed_source: "batter_pitcher_matchups 對戰爬蟲樣本",
  expected:
    "league + batter_dev + pitcher_dev（leave-pair-out：兩側 baseline 先扣除被評配對；對稱，角色翻轉不得雙方同優）",
  sigma2: 0.238834,
  tau2: 0.00069428,
  prior_strength: 344.0,
  credibility_gate: 0.75,
  prior_available: true,
  pairs_used: 344,
};

const base = {
  scope: "career",
  from_year: 9999,
  to_year: 9999,
  eligible: 0,
  gated_out: 0,
  sensitivity: null,
  disclaimer:
    "描述性統計（經驗貝氏收縮後的 wOBA 差），不代表因果或未來預測；baseline／聯盟均值取自官方完整季彙總，對戰觀察值來自對戰爬蟲樣本；小樣本已回縮並以可信度與覆蓋率閘門過濾。",
} as const;

/** fail-closed #4：C–E 無同賽事類型官方 baseline（API _empty_insights 形狀）。 */
export const FIXTURE_NO_BASELINE_CE: InsightsResponse = {
  ...base,
  player_id: "0000003467",
  role: "batting",
  kind_code: "C",
  baseline: null,
  league: null,
  coverage: null,
  query_sample: { opponent_team: null, opponents: 0, sampled_opportunities: 0 },
  advantages: [],
  disadvantages: [],
  sample_note: "季後賽／總冠軍賽無同賽事類型官方季彙總 baseline，不輸出洞察",
  method: { metric: "woba_generic_v1", credibility_gate: 0.75 },
};

/** fail-closed #1：全 scope 覆蓋率未過閘門（投手側常態，如官方生涯缺退休打者對戰）。 */
export const FIXTURE_LOW_COVERAGE: InsightsResponse = {
  ...base,
  player_id: "0000001234",
  role: "pitching",
  kind_code: "A",
  baseline: { woba: 0.3121, official_opportunities: 4210 },
  league: { woba: 0.3148, source: "official_season_aggregates" },
  coverage: {
    scope: "all_opponents",
    sampled_opportunities: 1980,
    official_opportunities: 4210,
    ratio: 0.47,
    gate: 0.6,
    passed: false,
  },
  query_sample: { opponent_team: null, opponents: 88, sampled_opportunities: 1980 },
  advantages: [],
  disadvantages: [],
  gated_out: 88,
  sample_note:
    "對戰樣本僅覆蓋官方生涯 47%（門檻 60%），非隨機子集，不輸出天敵／優勢排行",
  method: { ...METHOD_OK },
};

/** fail-closed #2：先驗無法估計（單季 scope 幾乎無 n≥50 配對）。 */
export const FIXTURE_NO_PRIOR: InsightsResponse = {
  ...base,
  player_id: "0000003467",
  role: "batting",
  kind_code: "A",
  scope: "season",
  from_year: 2026,
  to_year: 2026,
  baseline: { woba: 0.3641, official_opportunities: 205 },
  league: { woba: 0.3202, source: "official_season_aggregates" },
  coverage: {
    scope: "all_opponents",
    sampled_opportunities: 201,
    official_opportunities: 205,
    ratio: 0.98,
    gate: 0.6,
    passed: true,
  },
  query_sample: { opponent_team: null, opponents: 64, sampled_opportunities: 201 },
  advantages: [],
  disadvantages: [],
  gated_out: 64,
  sample_note:
    "該範圍可用配對樣本不足，經驗貝氏先驗（tau²）無法可靠估計，不輸出天敵／優勢排行",
  method: {
    ...METHOD_OK,
    sigma2: 0.214712,
    tau2: null,
    prior_strength: null,
    prior_available: false,
    pairs_used: 0,
  },
};

/** fail-closed #3：閘門全通過但所有候選未過 credibility（低樣本：1 打數 1 轟不成結論）。 */
export const FIXTURE_GATED: InsightsResponse = {
  ...base,
  player_id: "0000005678",
  role: "batting",
  kind_code: "A",
  baseline: { woba: 0.331, official_opportunities: 812 },
  league: { woba: 0.3197, source: "official_season_aggregates" },
  coverage: {
    scope: "all_opponents",
    sampled_opportunities: 809,
    official_opportunities: 812,
    ratio: 0.996,
    gate: 0.6,
    passed: true,
  },
  query_sample: { opponent_team: null, opponents: 41, sampled_opportunities: 809 },
  advantages: [],
  disadvantages: [],
  eligible: 0,
  gated_out: 41,
  sample_note: "樣本不足或差異不可信，僅提供一般對戰紀錄，不產生洞察排行",
  method: { ...METHOD_OK },
};

/** 成功態：打者視角，通過全部閘門（林泓育 career 抽樣節錄）。 */
export const FIXTURE_OK_BATTING: InsightsResponse = {
  ...base,
  player_id: "0000003467",
  role: "batting",
  kind_code: "A",
  baseline: { woba: 0.3808, official_opportunities: 6611 },
  league: { woba: 0.3197, source: "official_season_aggregates" },
  coverage: {
    scope: "all_opponents",
    sampled_opportunities: 6612,
    official_opportunities: 6611,
    ratio: 1.0,
    gate: 0.6,
    passed: true,
  },
  query_sample: { opponent_team: null, opponents: 408, sampled_opportunities: 6612 },
  advantages: [
    {
      opp_id: "0000003078",
      opp_name: "官大元",
      opp_team_code: "ACN011",
      opp_franchise: "ACN011",
      plate_appearances: 66,
      opportunities: 66,
      avg: 0.4643,
      ops: 1.3491,
      observed_woba: 0.5703,
      expected_woba: 0.3928,
      delta_shrunk: 0.0278,
      credibility: 0.875,
      opponent_official_opportunities: 2850,
    },
  ],
  disadvantages: [
    {
      opp_id: "0000003606",
      opp_name: "陳鴻文",
      opp_team_code: "AJL011",
      opp_franchise: "AJL011",
      plate_appearances: 82,
      opportunities: 82,
      avg: 0.1875,
      ops: 0.4948,
      observed_woba: 0.2179,
      expected_woba: 0.3772,
      delta_shrunk: -0.0298,
      credibility: 0.895,
      opponent_official_opportunities: 3541,
    },
  ],
  eligible: 10,
  gated_out: 397,
  sample_note: null,
  sensitivity: {
    stable: false,
    reference_members: ["0000003078", "0000003606"],
    variants: { "gate_0.75": ["0000003078", "0000003606"] },
  },
  method: { ...METHOD_OK },
};

/**
 * 角色翻轉：同一組對戰（林泓育×陳鴻文）換成投手（陳鴻文）視角。
 * API 對稱性保證：delta_shrunk 同號向同值（正＝有利打者），
 * 打者的劣勢候選＝投手的優勢候選，|delta| 相同。
 */
export const FIXTURE_OK_PITCHING_FLIPPED: InsightsResponse = {
  ...base,
  player_id: "0000003606",
  role: "pitching",
  kind_code: "A",
  baseline: { woba: 0.3018, official_opportunities: 3541 },
  league: { woba: 0.3148, source: "official_season_aggregates" },
  coverage: {
    scope: "all_opponents",
    sampled_opportunities: 3320,
    official_opportunities: 3541,
    ratio: 0.938,
    gate: 0.6,
    passed: true,
  },
  query_sample: { opponent_team: null, opponents: 210, sampled_opportunities: 3320 },
  advantages: [
    {
      opp_id: "0000003467",
      opp_name: "林泓育",
      opp_team_code: "AJL011",
      opp_franchise: "AJL011",
      plate_appearances: 82,
      opportunities: 82,
      avg: 0.1875,
      ops: 0.4948,
      observed_woba: 0.2179,
      expected_woba: 0.3772,
      delta_shrunk: -0.0298,
      credibility: 0.895,
      opponent_official_opportunities: 6611,
    },
  ],
  disadvantages: [],
  eligible: 4,
  gated_out: 206,
  sample_note: null,
  sensitivity: null,
  method: { ...METHOD_OK },
};
