// FastAPI 資料層 client（Server Component 用）。prod 走 Docker 內網，dev 走 localhost。
import { ApiError } from "./http-error";
import type { DailySummary } from "./daily-summary";

const API_URL = process.env.API_URL ?? "http://localhost:4001";

export type Standing = {
  code: string;
  name: string;
  w: number;
  l: number;
  g: number;
  win_pct: number;
  rs_pg: number;
  ra_pg: number;
  run_diff: number;
  form: string;
  ops: number | null;
  era: number | null;
  whip: number | null;
};

export type StandingsResponse = { season: number; standings: Standing[] };

// 球隊當季團隊指標的全年／上半季／下半季範圍切換（單一 gamelog+games 聚合路徑）。
export type TeamSplitTeam = {
  code: string;
  ops?: number | null;
  era?: number | null;
  whip?: number | null;
  rs_pg?: number | null;
  ra_pg?: number | null;
  run_diff?: number | null;
  g?: number | null;
};
export type TeamSplitScope = { key: "full" | "first" | "second"; label: string; available: boolean; teams: TeamSplitTeam[] };
export type TeamSplitResponse = { season: number; scopes: TeamSplitScope[] };

async function get<T>(path: string, revalidate = 600): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate } });
  if (!res.ok) throw new ApiError(path, res.status);
  return res.json() as Promise<T>;
}

export type BattingLeader = {
  player_id: string;
  name: string | null;
  team: string | null;
  g: number | null;
  pa: number | null;
  ab: number | null;
  r: number | null;
  h: number | null;
  b2: number | null;
  b3: number | null;
  hr: number | null;
  rbi: number | null;
  bb: number | null;
  so: number | null;
  sb: number | null;
  cs: number | null;
  avg: number | null;
  obp: number | null;
  slg: number | null;
  ops: number | null;
  ops_plus?: number | null;
};

export type BattingLeadersResponse = { season: number; sort: string; items: BattingLeader[] };

export type PitchingLeader = {
  player_id: string;
  name: string | null;
  team: string | null;
  g: number | null;
  gs: number | null;
  cg: number | null;
  sho: number | null;
  w: number | null;
  l: number | null;
  sv: number | null;
  hld: number | null;
  ip: number | null;
  era: number | null;
  whip: number | null;
  k9: number | null;
  pa: number | null;
  np: number | null;
  h: number | null;
  hr: number | null;
  bb: number | null;
  ibb: number | null;
  hbp: number | null;
  so: number | null;
  wp: number | null;
  bk: number | null;
  r: number | null;
  er: number | null;
  go: number | null;
  ao: number | null;
  goao: number | null;
  era_plus?: number | null;
};
export type PitchingLeadersResponse = { season: number; sort: string; items: PitchingLeader[] };

export type FieldingRecord = {
  player_id: string;
  name: string | null;
  team: string | null;
  pos: string;
  g: number | null;
  tc: number | null;
  po: number | null;
  a: number | null;
  e: number | null;
  dp: number | null;
  fpct: number | null;
};
export type FieldingResponse = {
  season: number;
  positions: string[];
  pos: string | null;
  sort: string;
  items: FieldingRecord[];
};

export type GameSummary = {
  year: number;
  kind_code: string;
  game_sno: number;
  game_date: string;
  away_team_name: string;
  away_team_code: string;
  away_score: number;
  home_team_name: string;
  home_team_code: string;
  home_score: number;
};
export type GamesRecentResponse = { season: number; items: GameSummary[] };
export type CalendarGame = {
  year: number;
  kind_code: string;
  game_sno: number;
  game_date: string;
  venue: string | null;
  present_status: number | null;
  away_team_name: string;
  away_team_code: string;
  away_score: number;
  home_team_name: string;
  home_team_code: string;
  home_score: number;
  win_pitcher: string | null;
  lose_pitcher: string | null;
  mvp: string | null;
  home_starter: string | null;
  away_starter: string | null;
  attendance: number | null;
  game_time: string | null;
  delay_kind: string | null;
  orig_date: string | null;
};
export type GamesCalendarResponse = { season: number; items: CalendarGame[] };

export type OfficialStanding = {
  team_code: string;
  team_name: string;
  rank: number;
  g: number;
  w: number;
  t: number;
  l: number;
  win_pct: number | null;
  gb: number | null;
  elim: string | null;
  home_record: string | null;
  away_record: string | null;
  streak: string | null;
  last10: string | null;
  h2h: Record<string, string> | null;
  is_champion?: boolean;
};
export type HalfInfo = { finalized: boolean; clinched: boolean; champion_code: string | null };
export type OfficialStandingsResponse = {
  season: number;
  season_code: number;
  items: OfficialStanding[];
  half?: HalfInfo | null;
};

// 特殊戰績：各情境 [W, L] 或 [正向, 反向] 配對；sweeps/swept 為次數
export type WL = [number, number];
export type WTL = [number, number, number]; // 系列 [勝, 平, 負]
export type SpecialRecord = {
  team_code: string;
  team_name: string;
  // 場地
  natural: WL;
  artificial: WL;
  indoor: WL;
  // 比分型
  one_run: WL;
  blowout: WL;
  shutout: WL;   // [完封勝, 被完封]
  comeback: WL;  // [逆轉勝, 被逆轉]
  // 賽況軌跡
  scored_first: WL;
  scored_first_against: WL;
  intense: WL;
  tailwind: WL;
  headwind: WL;
  big_inning: WL;
  // 終局與守備
  extra: WL;
  save: WL;      // [守成成功, 失敗]
  errorful: WL;
  // 賽程
  weekday: WL;
  weekend: WL;
  // 對手先發
  vs_lhp: WL;
  vs_rhp: WL;
  // 系列賽（依官方比賽編號分組）
  series3: WTL;  // 三連戰系列 [勝, 平, 負]（2-1/3-0 同記一勝）
  series2: WTL;  // 雙連賽系列 [勝(2-0), 平(1-1), 負(0-2)]
  sweeps: number;          // 三連戰橫掃（3-0）
  swept: number;           // 被三連戰橫掃（0-3）
  twogame_sweep: number;   // 雙連賽橫掃（2-0＝series2 勝）
  twogame_swept: number;   // 被雙連賽橫掃（0-2＝series2 負）
  // 再見
  walkoff: number;                       // 再見勝
  walkoff_types: Record<string, number>; // 致勝方式分類 {類型: 次數}
  walked_off: number;                    // 被再見
  // 連勝連敗
  max_win_streak: number;
  max_lose_streak: number;
  // 月份趨勢
  months: Record<string, WL>;
};
export type SpecialRecordsResponse = { season: number; items: SpecialRecord[] };

// 戰績走勢：points 每筆含 date + 各 team_code 的累積勝-敗差
export type StandingsTrendPoint = { date: string } & Record<string, number | string>;
export type StandingsTrendResponse = { season: number; teams: string[]; names?: Record<string, string>; points: StandingsTrendPoint[] };
export type PostseasonSummaryResponse = {
  season: number;
  series: {
    kind_code: string;
    kind_name: string;
    team1_code: string;
    team1_name: string;
    team1_wins: number;
    team2_code: string;
    team2_name: string;
    team2_wins: number;
    games?: {
      game_no: number;
      date: string | null;
      home_code: string;
      home_name: string;
      home_score: number;
      away_code: string;
      away_name: string;
      away_score: number;
    }[];
  }[];
};

// —— 球場數據特色（VENUE-PARK1 契約；方法論見 docs/VENUE_PARK1_CONTRACT.md）——
// PF>1＝該球場放大該事件。games＝實際完成場次；估計基礎是 eligible_team_games（隊-場），
// low_sample 依估計基礎判定 —— UI 有義務同時揭露樣本與 low_sample，不得只列數字。
export const FACTOR_STATS = ["r", "hr", "xbh", "h", "bb", "so"] as const;
export type FactorStat = (typeof FACTOR_STATS)[number];
export type Factors = Record<FactorStat, { observed: number; expected: number; pf: number | null }>;
export type FactorSplit = {
  games: number;
  eligible_team_games: number;
  excluded_team_games: number;
  low_sample: boolean;
  factors: Factors;
};
export type VenueFactorsResponse = {
  venue: string;
  kind_code: string;
  from_year: number;
  to_year: number;
  method: string;
  method_note: string;
  data_floor_note: string;
  seasons: (FactorSplit & { year: number })[];
  pooled: FactorSplit;
  excluded_team_games: number;
};

export type VenueEnvLine = {
  year: number;
  pa: number | null; ab: number | null; h: number | null; hr: number | null;
  doubles: number | null; triples: number | null;
  avg: number | null; obp: number | null; slg: number | null; ops: number | null;
  hr_pct: number | null; so_pct: number | null; bb_pct: number | null;
  go: number | null; fo: number | null; go_ao: number | null;
};
export type VenueStatsResponse = {
  venue: string; item_name: string; kind_code: string;
  seasons: VenueEnvLine[];
  league: VenueEnvLine[];
  note: string;
};

// 生涯口徑（官方分項 year=9999，含 2018 以前）。delta＝該球場減自身生涯，描述性統計。
export type VenueBatter = {
  player_id: string; name: string | null;
  venue_pa: number; venue_avg: number | null; venue_ops: number | null; venue_hr: number | null;
  career_pa: number; career_ops: number; delta_ops: number;
};
export type VenuePitcher = {
  player_id: string; name: string | null;
  venue_ip: number; venue_era: number | null; venue_k_pct: number | null;
  career_ip: number; career_era: number | null; delta_era: number;
};
export type VenuePlayersResponse<T> = {
  venue: string; item_name: string; role: string;
  thresholds: { min_pa: number; min_outs: number };
  best: T[]; worst: T[];
  note: string;
};

// —— /methodology 用：模型回測紀錄（model_versions 快照）。available=false＝artifact／
// 回測紀錄缺席，頁面須退回報告快照文字並明示，不得空白或拋錯。
export type BacktestModelRow = {
  name: string;
  accuracy: number;
  brier: number;
  log_loss: number;
  ece?: number;
};
export type PregameBacktestResponse = {
  available: boolean;
  version?: string;
  trained_at?: string | null;
  gate?: { checks: Record<string, boolean>; deployable: boolean };
  models?: BacktestModelRow[];
  n_test?: number;
  test_years?: number[];
  seasons_beating_baseline?: number;
  paired_bootstrap?: {
    method: string;
    iterations: number;
    brier_delta_ci95: [number, number];
    log_loss_delta_ci95: [number, number];
  };
};
export type OutcomeBenchmarkResponse = {
  available: boolean;
  version?: string;
  trained_at?: string | null;
  best?: string;
  models?: { name: string; brier: number; accuracy: number; log_loss: number }[];
  n_test?: number;
  test_seasons?: number[];
};

export const api = {
  officialStandings: (seg = 0, year?: number, kind = "A") =>
    get<OfficialStandingsResponse>(`/api/v1/standings?season_code=${seg}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 120),
  seasons: (kind = "A") => get<{ years: number[] }>(`/api/v1/seasons?kind_code=${kind}`, 600),
  teamDer: (code: string) =>
    get<{ team: string; franchise: string;
      items: { year: number; team_id: string; der: string; rnk: number; n: number; lg_der: string }[];
    }>(`/api/v1/teams/${code}/der`, 600),
  teamEras: (code: string) =>
    get<{
      franchise: string; origins: string | null;
      eras: { code: string; name: string; from: number; to: number; w: number; t: number; l: number; win_pct: number | null }[];
      total: { w: number; l: number; t: number; win_pct: number | null };
      longest_win_streak: number; longest_lose_streak: number;
      best_season: { year: number; name: string; win_pct: number } | null;
      worst_season: { year: number; name: string; win_pct: number } | null;
      championships: number[]; championship_count: number;
    }>(`/api/v1/teams/${code}/eras`, 600),
  franchises: () =>
    get<{
      items: {
        code: string; name: string; active: boolean;
        from: number; to: number; w: number; l: number; t: number; win_pct: number | null;
        eras: { code: string; name: string; from: number; to: number }[];
      }[];
    }>(`/api/v1/franchises`, 600),
  teamPlayers: (code: string) =>
    get<{
      code: string;
      batters: { player_id: string; name: string; g: number; h: number; hr: number; rbi: number; from: number; to: number; active: boolean }[];
      pitchers: { player_id: string; name: string; g: number; w: number; sv: number; so: number; from: number; to: number; active: boolean }[];
      coaches?: { pos: string; name: string; uniform_no: string | null; player_id?: string | null }[];
      managers?: {
        era: string; name: string; from: number; to: number;
        w: number; l: number; t: number; win_pct: number | null;
        postseason: number; championships: number; player_id?: string | null;
        source?: "db" | "wiki";
      }[];
      roster?: {
        first_batters: { player_id: string; name: string }[];
        first_pitchers: { player_id: string; name: string }[];
        farm: { player_id: string; name: string }[];
      };
      retired?: {
        number: number; holder_type: "player" | "fans" | "org";
        player_id: string | null; holder: string; status: "active" | "revoked"; note: string | null;
      }[];
    }>(`/api/v1/teams/${code}/players`, 600),
  specialRecords: (season?: number) =>
    get<SpecialRecordsResponse>(`/api/v1/special-records${season ? `?season=${season}` : ""}`, 120),
  standingsTrend: (season?: number, kind = "A") =>
    get<StandingsTrendResponse>(`/api/v1/standings-trend?kind_code=${kind}${season ? `&season=${season}` : ""}`, 120),
  postseasonSummary: (season?: number, kind = "A") =>
    get<PostseasonSummaryResponse>(`/api/v1/postseason-summary?kind_code=${kind}${season ? `&season=${season}` : ""}`, 120),
  gamesRecent: (limit = 60, year?: number, kind = "A") =>
    get<GamesRecentResponse>(`/api/v1/games/recent?limit=${limit}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 120),
  gamesCalendar: (year?: number, kind = "A") =>
    get<GamesCalendarResponse>(`/api/v1/games/calendar?kind_code=${kind}${year ? `&season=${year}` : ""}`, 120),
  standings: (season?: number) =>
    get<StandingsResponse>(`/api/v1/season/standings${season ? `?season=${season}` : ""}`),
  teamSplit: (season?: number) =>
    get<TeamSplitResponse>(`/api/v1/season/team-split${season ? `?season=${season}` : ""}`, 120),
  records: () =>
    get<{
      games: Record<"max_margin" | "max_team_runs" | "max_combined", { year: number; date: string; home: string; away: string; hs: number; as: number } | null>;
      season_batting: Record<string, { name: string; pid: string; year: number; val: number | string }[]>;
      season_pitching: Record<string, { name: string; pid: string; year: number; val: number }[]>;
      career_batting: Record<string, { name: string; pid: string; val: number; active: boolean }[]>;
      career_pitching: Record<string, { name: string; pid: string; val: number | string; active: boolean }[]>;
    }>("/api/v1/records", 600),
  // 冠軍編：coverage fail-closed（缺年時 API 不回傳 franchise/player_ranking，前端據此不呈現累計結論）。
  championships: () =>
    get<{
      coverage: { from_year: number; through_year: number; complete: boolean; missing_years: number[]; as_of: string | null };
      seasons: {
        year: number; champion_team_code: string | null; champion: string | null;
        runner_up_team_code: string | null; runner_up: string | null;
        franchise_code: string | null; manager_name: string | null; source_url: string | null;
      }[];
      note?: string;
      franchise_ranking?: { team_code: string; team: string | null; titles: number; years: number[]; rk: number }[];
      player_ranking?: { name: string; pid: string; titles: number; years: number[]; active: boolean; is_manager: boolean; rk: number }[];
    }>("/api/v1/records/championships", 600),
  // 例行賽球隊紀錄集錦（全史完整資料；每項一位保持者）。
  teamRecords: () =>
    get<{
      records: { label: string; team_code: string; team: string | null; value: number; unit: string; year: number }[];
    }>("/api/v1/records/team", 600),
  // 季後賽球團戰績（僅完整資料：亞軍/連霸/勝率/出賽）。
  postseason: () =>
    get<{
      postseason_kinds: string[];
      teams: {
        team_code: string; team: string | null; runner_up: number; appearances: number;
        w: number; l: number; g: number; win_pct: number | null;
        streak: number; streak_from: number; streak_to: number;
      }[];
    }>("/api/v1/records/postseason", 600),
  // 排行榜改由前端點欄位排序/隊伍篩選，故抓全名單（低門檻、大 limit）。
  // revalidate=60：資料隨爬蟲更新，縮短快取避免欄位/數值過時。
  venues: (season?: number) =>
    get<{
      season: number;
      items: {
        venue: string; full_name: string | null; turf: string | null; indoor: boolean | null;
        city: string | null; capacity: number | null; infield_seats: number | null;
        outfield_seats: number | null; lf_dist: number | null; cf_dist: number | null;
        rf_dist: number | null; big_screen: boolean | null; address: string | null;
        games_played: number | null; avg_attendance: number | null; home_teams: string | null;
        first_year: number | null; last_year: number | null;
      }[];
    }>(`/api/v1/venues${season ? `?season=${season}` : ""}`, 600),
  // 球場詳情三端點。{venue} 為短名（含中文 → encodeURIComponent）；查無資料回 404 → 呼叫端 notFound()。
  venueFactors: (venue: string) =>
    get<VenueFactorsResponse>(`/api/v1/venues/${encodeURIComponent(venue)}/factors`, 600),
  venueStats: (venue: string) =>
    get<VenueStatsResponse>(`/api/v1/venues/${encodeURIComponent(venue)}/stats`, 600),
  venuePlayers: <T>(venue: string, role: "batting" | "pitching", limit = 6) =>
    get<VenuePlayersResponse<T>>(
      `/api/v1/venues/${encodeURIComponent(venue)}/players?role=${role}&limit=${limit}`, 600),
  projections: (stat = "ops", limit = 50) =>
    get<{
      model_version: string | null; stat: string; target_year: number | null;
      items: { player_id: string; name: string | null; predicted: number; actual: number | null }[];
    }>(`/api/v1/projections/batting?stat=${stat}&limit=${limit}`, 600),
  pitchingProjections: (stat = "era", limit = 50) =>
    get<{
      model_version: string | null; stat: string; target_year: number | null;
      items: { player_id: string; name: string | null; predicted: number; actual: number | null }[];
    }>(`/api/v1/projections/pitching?stat=${stat}&limit=${limit}`, 600),
  battingLeaders: (sort = "ops", { limit = 400, minPa = 0, year, kind = "A" }: { limit?: number; minPa?: number; year?: number; kind?: string } = {}) =>
    get<BattingLeadersResponse>(`/api/v1/season/batting-leaders?sort=${sort}&limit=${limit}&min_pa=${minPa}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 60),
  pitchingLeaders: (sort = "era", { limit = 400, minIp = 0, year, kind = "A" }: { limit?: number; minIp?: number; year?: number; kind?: string } = {}) =>
    get<PitchingLeadersResponse>(`/api/v1/season/pitching-leaders?sort=${sort}&limit=${limit}&min_ip=${minIp}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 60),
  fielding: (sort = "g", { season, pos, limit = 1000 }: { season?: number; pos?: string; limit?: number } = {}) =>
    get<FieldingResponse>(`/api/v1/season/fielding?sort=${sort}&limit=${limit}${season ? `&season=${season}` : ""}${pos ? `&pos=${encodeURIComponent(pos)}` : ""}`, 300),
  // 首頁每日入口單一聚合契約（API-DAILY-SUMMARY1）：最近比賽日／下一批賽事／freshness／
  // 三軸 availability，取代舊首頁十餘組請求（blueprint §8.4）。revalidate=120 對齊賽事類。
  dailySummary: (kind = "A", season?: number) =>
    get<DailySummary>(`/api/v1/daily/summary?kind_code=${kind}${season ? `&season=${season}` : ""}`, 120),
  // /methodology 賽前勝率段：正式回測紀錄與舊全特徵 benchmark 對照。
  pregameBacktest: () =>
    get<PregameBacktestResponse>("/api/v1/outcome/pregame/backtest", 600),
  outcomeBenchmark: () => get<OutcomeBenchmarkResponse>("/api/v1/outcome/backtest", 600),
  playersRoster: (season?: number) =>
    get<{
      season: number;
      batters: { id: string; name: string; team: string }[];
      pitchers: { id: string; name: string; team: string }[];
    }>(`/api/v1/players/roster${season ? `?season=${season}` : ""}`, 600),
};
