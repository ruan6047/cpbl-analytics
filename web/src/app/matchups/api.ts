// /matchups 查詢頁專用 API 取用層（UX-MATCHUP1）。
// 只消費 MATCHUP-DATA1／ML-MATCHUP1 已核可端點；統計判定一律由 API 計算，
// 前端不得重做（紅線）。共用元件抽離屬 UX-MATCHUP2，先收在本資料夾。
import { clientGet } from "@/lib/client";

export type Role = "batting" | "pitching";
export type Kind = "A" | "C" | "E";
export type Scope = "career" | "season" | "range";
export type SortKey = "plate_appearances" | "avg" | "ops" | "home_runs" | "so";

/** 對戰資料的年度涵蓋（來自對戰爬蟲）：官網僅提供本季年度列＋生涯彙總列。 */
export type YearCoverage = { career: boolean; annual_years: number[] };

export type RosterHit = {
  id: string;
  name: string | null;
  team_code: string | null;
  team: string | null;
  franchise: string | null;
};

export type MatchupRow = {
  opp_id: string;
  opp_name: string | null;
  opp_team_code: string | null;
  opp_team: string | null;
  opp_franchise: string | null;
  plate_appearances: number;
  at_bats: number;
  hits: number;
  rbi: number;
  singles: number;
  doubles: number;
  triples: number;
  home_runs: number;
  total_bases: number;
  sac_hit: number;
  sac_fly: number;
  bb: number;
  ibb: number;
  hbp: number;
  so: number;
  ground_out: number;
  fly_out: number;
  avg: number | null;
  obp: number | null;
  slg: number | null;
  ops: number | null;
  goao: number | null;
  source_rows: number;
  from_year: number | null;
  to_year: number | null;
  strike_pct: number | null;
  ball_pct: number | null;
  swing_pct: number | null;
  first_pitch_swing_pct: number | null;
  whiff_pct: number | null;
  gb_pct: number | null;
  ld_pct: number | null;
  fb_pct: number | null;
};

export type MatchupList = {
  player_id: string;
  role: Role;
  kind_code: Kind;
  scope: Scope;
  from_year: number;
  to_year: number;
  source: string;
  coverage: YearCoverage;
  filters: { opponent_team: string | null; opponent_id: string | null };
  sort: string;
  order: string;
  available_count: number;
  items: MatchupRow[];
};

export type PairRow = Omit<
  MatchupRow,
  "opp_id" | "opp_name" | "opp_team_code" | "opp_team" | "opp_franchise"
> & {
  kind_code: Kind;
  hitter_name: string | null;
  pitcher_name: string | null;
  hitter_team_code: string | null;
  pitcher_team_code: string | null;
  hitter_franchise: string | null;
  pitcher_franchise: string | null;
};

export type PairDetail = {
  hitter: string;
  pitcher: string;
  kind_code: Kind | null;
  scope: Scope;
  from_year: number;
  to_year: number;
  coverage: YearCoverage;
  items: PairRow[];
};

// ---- ML-MATCHUP1 洞察契約 ----

export type InsightItem = {
  opp_id: string;
  opp_name: string | null;
  opp_team_code: string | null;
  opp_franchise: string | null;
  plate_appearances: number | null;
  opportunities: number;
  avg: number | null;
  ops: number | null;
  observed_woba: number;
  expected_woba: number;
  delta_shrunk: number;
  credibility: number;
  opponent_official_opportunities: number;
};

/** 樣本覆蓋率閘門（全 scope 評估，與 query_sample 分開；勿與年度涵蓋混淆）。 */
export type InsightCoverage = {
  scope: "all_opponents";
  sampled_opportunities: number;
  official_opportunities: number;
  ratio: number;
  gate: number;
  passed: boolean;
};

export type InsightMethod = {
  metric: string;
  baseline_source?: string;
  observed_source?: string;
  expected?: string;
  sigma2?: number;
  tau2?: number | null;
  prior_strength?: number | null;
  credibility_gate: number;
  prior_available?: boolean;
  pairs_used?: number;
};

export type Sensitivity = {
  stable: boolean;
  reference_members: string[];
  variants: Record<string, string[]>;
} | null;

export type InsightsResponse = {
  player_id: string;
  role: Role;
  kind_code: Kind;
  scope: Scope;
  from_year: number;
  to_year: number;
  baseline: { woba: number | null; official_opportunities: number } | null;
  league: { woba: number; source: string } | null;
  coverage: InsightCoverage | null;
  query_sample: {
    opponent_team: string | null;
    opponents: number;
    sampled_opportunities: number;
  };
  advantages: InsightItem[];
  disadvantages: InsightItem[];
  eligible: number;
  gated_out: number;
  sample_note: string | null;
  sensitivity: Sensitivity;
  method: InsightMethod;
  disclaimer: string;
};

export type FranchiseInfo = {
  code: string;
  name: string;
  active: boolean;
  from: number;
  to: number;
};

// ---- 查詢參數（唯一事實來源：deep-link 與 fetch 共用） ----

export type MatchupQuery = {
  role: Role;
  kind: Kind;
  scope: Scope;
  fromYear: number | null;
  toYear: number | null;
};

function scopeParams(q: MatchupQuery): string {
  // season 不帶年份：交給 API 的 DEFAULT_SEASON（當季），避免前端寫死年度。
  if (q.scope === "season") return "scope=season";
  if (q.scope === "career") return "scope=career";
  return `scope=range&from_year=${q.fromYear}&to_year=${q.toYear}`;
}

export const matchupApi = {
  searchRoster: (role: Role, q: string, limit = 12) =>
    clientGet<{ items: RosterHit[] }>(
      `/api/v1/players/roster?role=${role}&q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  list: (
    pid: string,
    q: MatchupQuery,
    opts: { team?: string | null; sort?: SortKey; order?: "asc" | "desc" } = {},
  ) => {
    let url =
      `/api/v1/players/${pid}/matchups?role=${q.role}&kind_code=${q.kind}` +
      `&${scopeParams(q)}&limit=200&sort=${opts.sort ?? "plate_appearances"}` +
      `&order=${opts.order ?? "desc"}`;
    if (opts.team) url += `&opponent_team=${opts.team}`;
    return clientGet<MatchupList>(url);
  },
  insights: (pid: string, q: MatchupQuery, team?: string | null) => {
    let url =
      `/api/v1/players/${pid}/matchups/insights?role=${q.role}` +
      `&kind_code=${q.kind}&${scopeParams(q)}&limit=3`;
    if (team) url += `&opponent_team=${team}`;
    return clientGet<InsightsResponse>(url);
  },
  pair: (hitter: string, pitcher: string, q: MatchupQuery) =>
    clientGet<PairDetail>(
      `/api/v1/matchups?hitter=${hitter}&pitcher=${pitcher}&${scopeParams(q)}`,
    ),
  franchises: () =>
    clientGet<{ items: FranchiseInfo[] }>("/api/v1/franchises"),
  playerName: async (pid: string): Promise<string | null> => {
    const d = await clientGet<{ player: { name: string | null } | null }>(
      `/api/v1/players/${pid}/profile`,
    );
    return d.player?.name ?? null;
  },
};
