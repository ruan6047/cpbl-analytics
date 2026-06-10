// FastAPI 資料層 client。Server Component 直接 fetch；prod 走 Docker 內網。
const API_URL = process.env.API_URL ?? "http://localhost:4001";

export type ProjectionItem = {
  player_id: string;
  name: string;
  predicted: number;
  actual: number | null;
};

export type ProjectionResponse = {
  model_version: string | null;
  stat: string;
  target_year: number | null;
  items: ProjectionItem[];
};

export type PlayerSeason = {
  year: number;
  g: number | null;
  pa: number | null;
  ab: number | null;
  h: number | null;
  hr: number | null;
  rbi: number | null;
  bb: number | null;
  so: number | null;
  avg: number | null;
};

export type PlayerResponse = {
  player: { id: string; name: string; bats: string | null; throws: string | null; birthday: string | null } | null;
  seasons: PlayerSeason[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  battingProjections: (stat = "ops", limit = 25) =>
    get<ProjectionResponse>(`/api/v1/projections/batting?stat=${stat}&limit=${limit}`),
  player: (id: string) => get<PlayerResponse>(`/api/v1/players/${id}/batting`),
};
