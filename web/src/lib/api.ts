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

export const api = {
  gamesRecent: (limit = 60) => get<GamesRecentResponse>(`/api/v1/games/recent?limit=${limit}`, 120),
  standings: (season?: number) =>
    get<StandingsResponse>(`/api/v1/season/standings${season ? `?season=${season}` : ""}`),
  // 排行榜改由前端點欄位排序/隊伍篩選，故抓全名單（低門檻、大 limit）。
  // revalidate=60：資料隨爬蟲更新，縮短快取避免欄位/數值過時。
  battingLeaders: (sort = "ops", { limit = 400, minPa = 0 } = {}) =>
    get<BattingLeadersResponse>(`/api/v1/season/batting-leaders?sort=${sort}&limit=${limit}&min_pa=${minPa}`, 60),
  pitchingLeaders: (sort = "era", { limit = 400, minIp = 0 } = {}) =>
    get<PitchingLeadersResponse>(`/api/v1/season/pitching-leaders?sort=${sort}&limit=${limit}&min_ip=${minIp}`, 60),
  fielding: (sort = "tc", pos?: string, { limit = 600 } = {}) =>
    get<FieldingResponse>(
      `/api/v1/season/fielding?sort=${sort}${pos ? `&pos=${encodeURIComponent(pos)}` : ""}&limit=${limit}`,
      60,
    ),
};
