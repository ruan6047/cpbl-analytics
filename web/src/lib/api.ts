// FastAPI 資料層 client（Server Component 用）。prod 走 Docker 內網，dev 走 localhost。
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

async function get<T>(path: string, revalidate = 600): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate } });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
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
};
export type OfficialStandingsResponse = { season: number; season_code: number; items: OfficialStanding[] };

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

export const api = {
  officialStandings: (seg = 0, year?: number, kind = "A") =>
    get<OfficialStandingsResponse>(`/api/v1/standings?season_code=${seg}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 120),
  seasons: (kind = "A") => get<{ years: number[] }>(`/api/v1/seasons?kind_code=${kind}`, 600),
  teamEras: (code: string) =>
    get<{
      franchise: string; origins: string | null;
      eras: { code: string; name: string; from: number; to: number; w: number; t: number; l: number; win_pct: number | null }[];
      total: { w: number; l: number; t: number; win_pct: number | null };
      longest_win_streak: number; longest_lose_streak: number;
      best_season: { year: number; name: string; win_pct: number } | null;
      worst_season: { year: number; name: string; win_pct: number } | null;
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
  gamesRecent: (limit = 60, year?: number, kind = "A") =>
    get<GamesRecentResponse>(`/api/v1/games/recent?limit=${limit}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 120),
  standings: (season?: number) =>
    get<StandingsResponse>(`/api/v1/season/standings${season ? `?season=${season}` : ""}`),
  records: () =>
    get<{
      games: Record<"max_margin" | "max_team_runs" | "max_combined", { year: number; date: string; home: string; away: string; hs: number; as: number } | null>;
      season_batting: Record<string, { name: string; pid: string; year: number; val: number | string }[]>;
      season_pitching: Record<string, { name: string; pid: string; year: number; val: number }[]>;
      career_batting: Record<string, { name: string; pid: string; val: number; active: boolean }[]>;
      career_pitching: Record<string, { name: string; pid: string; val: number; active: boolean }[]>;
    }>("/api/v1/records", 600),
  // 排行榜改由前端點欄位排序/隊伍篩選，故抓全名單（低門檻、大 limit）。
  // revalidate=60：資料隨爬蟲更新，縮短快取避免欄位/數值過時。
  battingLeaders: (sort = "ops", { limit = 400, minPa = 0, year, kind = "A" }: { limit?: number; minPa?: number; year?: number; kind?: string } = {}) =>
    get<BattingLeadersResponse>(`/api/v1/season/batting-leaders?sort=${sort}&limit=${limit}&min_pa=${minPa}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 60),
  pitchingLeaders: (sort = "era", { limit = 400, minIp = 0, year, kind = "A" }: { limit?: number; minIp?: number; year?: number; kind?: string } = {}) =>
    get<PitchingLeadersResponse>(`/api/v1/season/pitching-leaders?sort=${sort}&limit=${limit}&min_ip=${minIp}&kind_code=${kind}${year ? `&season=${year}` : ""}`, 60),
};
