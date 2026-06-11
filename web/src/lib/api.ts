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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 600 } });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export type BattingLeader = {
  player_id: string;
  name: string | null;
  team: string | null;
  pa: number | null;
  avg: number | null;
  obp: number | null;
  slg: number | null;
  ops: number | null;
  hr: number | null;
  ops_plus: number | null;
  k_pct: number | null;
  bb_pct: number | null;
};

export type BattingLeadersResponse = { season: number; sort: string; items: BattingLeader[] };

export const api = {
  standings: (season?: number) =>
    get<StandingsResponse>(`/api/v1/season/standings${season ? `?season=${season}` : ""}`),
  battingLeaders: (sort = "ops") =>
    get<BattingLeadersResponse>(`/api/v1/season/batting-leaders?sort=${sort}&limit=50`),
};
