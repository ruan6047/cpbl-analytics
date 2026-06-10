// 瀏覽器端 API base。prod 同源(經 nginx)→ 可留空走相對路徑；dev 指向 FastAPI。
export const CLIENT_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4001";

export type FeatureMeta = { key: string; label: string; desc?: string };

export type EvalResult = {
  features: string[];
  n_train: number;
  n_test: number;
  test_season: number;
  accuracy: number;
  baseline_home_always: number;
  brier: number;
  log_loss: number;
  coefficients: Record<string, number>;
};

export type UpcomingGame = {
  game_date: string;
  home: string;
  away: string;
  home_win_prob: number;
};

export async function clientGet<T>(path: string): Promise<T> {
  const res = await fetch(`${CLIENT_API}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ---- 賽果預測：對戰卡 ----

export type OutcomeModel = {
  features: string[];
  weights: Record<string, number>;
  accuracy: number;
  baseline: number;
  n_train: number;
  test_season: number;
};

export type Factor = {
  key: string;
  label: string;
  home_val: number | null;
  away_val: number | null;
  favored: "home" | "away" | "even";
};

export type Starter = { name: string | null; era: number | null } | null;

export type TeamSide = {
  code: string;
  name: string;
  win_pct: number;
  rs_pg: number;
  ra_pg: number;
  form: string;
  record: string;
  starter?: Starter;
};

export type Matchup = {
  game_date: string | null;
  home: TeamSide;
  away: TeamSide;
  h2h_home: number;
  factors: Factor[];
  z: Record<string, number>;
  home_win_prob: number;
};

export type MatchupsResponse = { model: OutcomeModel; items: Matchup[] };
export type SimulateResponse = { model: OutcomeModel; matchup: Matchup };
export type Team = { code: string; name: string };

// 前端用 z + 使用者調整後的權重即時重算主勝率：p = sigmoid(Σ wₖ·zₖ)
export function winProb(z: Record<string, number>, weights: Record<string, number>): number {
  let logit = 0;
  for (const k in z) logit += (weights[k] ?? 0) * z[k];
  return 1 / (1 + Math.exp(-logit));
}
