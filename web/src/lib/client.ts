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

export type Starter = { pid?: string | null; name: string | null; era: number | null } | null;

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

// 全特徵走查回測對照（LightGBM vs 邏輯回歸 vs 全押主場）
export type BacktestModel = { name: string; accuracy: number; brier: number; log_loss: number };
export type Backtest = {
  available: boolean;
  trained_at?: string;
  test_seasons?: (number | null)[];
  n_test?: number;
  home_rate_test?: number;
  models?: BacktestModel[];
  best?: string;
  beats_baseline?: boolean;
  importance?: { key: string; label: string; gain: number }[];
};

// 前端用 z + 使用者調整後的權重即時重算主勝率：p = sigmoid(Σ wₖ·zₖ)
export function winProb(z: Record<string, number>, weights: Record<string, number>): number {
  let logit = 0;
  for (const k in z) logit += (weights[k] ?? 0) * z[k];
  return 1 / (1 + Math.exp(-logit));
}

// ---- 投打對決 / 對戰各隊 / 分項 ----

export type RosterPlayer = { id: string; name: string | null; team: string | null };
export type Roster = { season: number; batters: RosterPlayer[]; pitchers: RosterPlayer[] };

// 各表欄位眾多，統一以寬鬆 record 表示，由頁面挑欄位呈現。
export type StatRow = Record<string, number | string | null>;
export type MatchupsData = { hitter: string; pitcher: string; items: StatRow[] };
export type VsTeamData = { player_id: string; role: string; items: StatRow[] };
export type SplitsData = { player_id: string; role: string; year: number; kind_code: string; items: StatRow[] };

export const KIND_LABEL: Record<string, string> = {
  A: "一軍例行賽",
  C: "總冠軍賽",
  E: "季後挑戰賽",
};

export type PlayerProfile = {
  id: string;
  name: string | null;
  team: string | null;
  is_batter: boolean;
  is_pitcher: boolean;
  bats: string | null;
  throws: string | null;
  former_names: string[];
  pitcher_role?: string | null;
  country?: string | null;
  import_status?: "local" | "import" | "loree" | "nagata";
  import_label?: string | null;
};
export type ProfileData = { player: PlayerProfile | null };
export type PlayerMatchupsData = {
  player_id: string;
  role: string;
  kind_code: string;
  items: StatRow[];
};

export const detail = {
  roster: () => clientGet<Roster>("/api/v1/players/roster"),
  matchups: (hitter: string, pitcher: string) =>
    clientGet<MatchupsData>(`/api/v1/matchups?hitter=${hitter}&pitcher=${pitcher}`),
  vsTeam: (id: string, role: "batting" | "pitching") =>
    clientGet<VsTeamData>(`/api/v1/players/${id}/vs-team?role=${role}`),
  splits: (id: string, role: "batting" | "pitching", year: number, kind = "A") =>
    clientGet<SplitsData>(`/api/v1/players/${id}/splits?role=${role}&year=${year}&kind_code=${kind}`),
  profile: (id: string) => clientGet<ProfileData>(`/api/v1/players/${id}/profile`),
  playerMatchups: (id: string, role: "batting" | "pitching", kind = "A") =>
    clientGet<PlayerMatchupsData>(`/api/v1/players/${id}/matchups?role=${role}&kind_code=${kind}`),
  season: (id: string) =>
    clientGet<{ batting: StatRow | null; pitching: StatRow | null }>(`/api/v1/players/${id}/season`),
  arsenal: (id: string, role: "batting" | "pitching") =>
    clientGet<{ items: StatRow[] }>(`/api/v1/players/${id}/arsenal?role=${role}`),
  trend: (id: string, role: "batting" | "pitching") =>
    clientGet<{ items: StatRow[] }>(`/api/v1/players/${id}/trend?role=${role}`),
  fielding: (id: string) =>
    clientGet<{ items: StatRow[] }>(`/api/v1/players/${id}/fielding`),
  career: (id: string, role: "batting" | "pitching") =>
    clientGet<{ seasons: StatRow[] }>(`/api/v1/players/${id}/${role}`),
  careerStats: (id: string) =>
    clientGet<{
      batting: (Record<string, number | null> & { seasons: number }) | null;
      best: Record<string, { year: number; value: number } | null>;
      milestones: { first_hit: string | null; first_hr: string | null };
      rank: { hr: number; h: number; sb: number } | null;
      teams?: { code: string; name: string; from: number; to: number }[];
      overseas?: { league: string; team: string | null; year: number }[];
      awards?: { year: number; category: string; award: string }[];
      coach_tenures?: { team: string; role: string | null; from: number | null; to: number | null }[];
      exec_tenures?: { team: string; role: string | null; from: number | null; to: number | null }[];
      medals?: { color: string; competition: string | null; event: string | null; year: number | null }[];
    }>(`/api/v1/players/${id}/career`),
  advanced: (id: string) =>
    clientGet<{ batting: StatRow | null; pitching: StatRow | null }>(`/api/v1/players/${id}/advanced`),
  abilityCard: (id: string) =>
    clientGet<{
      player_id: string;
      batting: { career: import("@/components/ability-card").Card; season: import("@/components/ability-card").Card };
      pitching: { career: import("@/components/ability-card").Card; season: import("@/components/ability-card").Card };
    }>(`/api/v1/players/${id}/ability-card`),
  discipline: (id: string, role: "batting" | "pitching") =>
    clientGet<{
      summary: Record<string, number | null>;
      quality: Record<string, number | null>;
      points: { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null }[];
      spray: { dir: number; dist: number; ev: number | null; result: string }[];
      batted: { la: number; ev: number; result: string }[];
    }>(`/api/v1/players/${id}/discipline?role=${role}`),
  pitchMix: (id: string, role: "batting" | "pitching") =>
    clientGet<{ items: { bucket: string; n: number; fastball: number; breakingball: number }[] }>(
      `/api/v1/players/${id}/pitch-mix?role=${role}`,
    ),
  gameLive: (sno: number, kind = "A", year?: number) =>
    clientGet<{
      game: StatRow | null; scoreboard: StatRow[]; livelog: StatRow[];
      batting: StatRow[]; pitching: StatRow[]; people: Record<string, string>;
      records: Record<string, { w: number; l: number; form: string }>;
      batter_avg: Record<string, number>;
      has_tracking: boolean;
    }>(`/api/v1/games/${sno}/live?kind_code=${kind}${year ? `&season=${year}` : ""}`),
  // 全聯盟本季母體（算百分位 PR 用）
  leaders: (role: "batting" | "pitching") =>
    clientGet<{ items: StatRow[] }>(
      role === "batting"
        ? "/api/v1/season/batting-leaders?sort=ops&limit=400&min_pa=0"
        : "/api/v1/season/pitching-leaders?sort=era&limit=400&min_ip=0",
    ),
};
