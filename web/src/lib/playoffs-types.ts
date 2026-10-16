// `playoffs-overview/v1`（#285 S04）的 TS 型別鏡像與取數。唯一來源是 `src/cpbl/playoffs/overview.py`；
// 本檔只鏡射形狀與組 URL，不含勝場／完賽／目標場邏輯（那些全在 S02，前端只讀）。
//
// - 第 1 區預告不含先發投手（需求方 D7）：型別刻意沒有 starter 欄位。
// - `context_version` 是 S02 原值，與 #289 watch 回應同源可比；不一致時由輪詢控制器（playoffs-poll.ts）重取。
// - server 取數 `no-store`：控制狀態快取不得超過 30 秒輪詢（⛔ 用 api.ts 的 600 秒 revalidate）。

import type { GameKeyV2, SeriesContractCoverage, SeriesContractOfficialStatus, SeriesStatusV2, TargetStatusV2 } from "./postseason-series-contract.ts";
import type { SeriesSummary } from "./playoffs-series-summary.ts";

export type PlayoffsSeriesCode = "E" | "C";

export type OverviewSide = {
  team_code: string | null;
  initial_wins: number | null;
  initial_wins_basis: "rule_standings" | "announcement_confirmed" | "unsourced" | null;
  game_wins: number;
  total_wins: number | null;
  remaining: number | null;
};

export type OverviewMvpMissing = "official_mvp_not_ingested" | "player_name_unavailable";

export type OverviewGameCard = {
  game_key: GameKeyV2;
  official_game_sno: number;
  series_game_no: number;
  announced_slot_id: string | null;
  game_date: string | null;
  /** 公告開賽時刻（`HH:mm`，來源見頂層 `schedule_source`）；無公告格時 null。 */
  start: string | null;
  venue: string | null;
  away_team_code: string;
  home_team_code: string;
  completed: boolean;
  result: "home_win" | "away_win" | "tie" | null;
  /** 未完賽恆 null（S02）。 */
  away_score: number | null;
  home_score: number | null;
  counted_for_wins: boolean;
  official_status: SeriesContractOfficialStatus;
  target_status: TargetStatusV2;
  display_status: "final" | "scheduled" | "announced" | "result_pending" | "not_needed" | null;
  conditional: boolean;
  hidden_not_needed: boolean;
  /** 只在完賽卡；`name` 為 null 時看 `mvp_missing_reason`。 */
  mvp: { id: string; name: string | null } | null;
  mvp_missing_reason: OverviewMvpMissing | null;
};

export type OverviewSeriesBlock = {
  kind_code: PlayoffsSeriesCode;
  series_id: { year: number; kind_code: PlayoffsSeriesCode; rule_version: string | null; teams: (string | null)[] };
  participants_status: "known" | "pending_e_winner" | "unknown";
  best_of: number | null;
  wins_needed: number | null;
  series_status: SeriesStatusV2;
  conflict_reason: string | null;
  winner: string | null;
  ties: number;
  sides: OverviewSide[];
  games: OverviewGameCard[];
};

export type PlayoffsOverview = {
  contract: "playoffs-overview/v1";
  context_contract: string;
  year: number;
  context_version: string;
  default_series: PlayoffsSeriesCode;
  series_id: OverviewSeriesBlock["series_id"];
  target_game_key: GameKeyV2 | null;
  as_of: {
    now: string;
    taipei_date: string;
    last_completed_game_date: string | null;
    last_refresh_at: string | null;
    last_refresh_ok: boolean | null;
    last_refresh_scope: string | null;
    coverage: SeriesContractCoverage;
    pending_games: { year: number; kind_code: string; game_sno: number; game_date: string | null; reason: string }[];
  };
  coverage: SeriesContractCoverage;
  missing_reason: string[];
  source_manifest: { source: string; scope: string; version_or_hash: string | null; observed_at: string | null; status: string }[];
  schedule_source: { kind: "official_announcement"; url: string; published_on: string } | null;
  series_section: {
    /** `empty`＝整年 E／C 都沒有場次列；只有當前系列缺列時仍是 `ok`，缺列見 `missing_reason`（`series_games_missing`）。 */
    status: "ok" | "empty";
    missing_reason: string[];
    previous: OverviewSeriesBlock | null;
    current: OverviewSeriesBlock;
    next_game: OverviewGameCard | null;
    next_game_missing_reason: "no_target" | "target_not_in_games" | "series_decided" | "target_completed" | null;
  };
  /** #288 系列累計榜（選填：舊版 API 沒有此欄）；形狀見 `playoffs-series-summary.ts`。 */
  series_summary?: SeriesSummary | null;
  sections: {
    series: { status: "ok" | "empty"; missing_reason: string[] };
    watch: { status: "ok" | "no_target"; series: PlayoffsSeriesCode; game: number | null };
  };
};

export function overviewPath(year: number): string {
  return `/api/v1/playoffs/overview?season=${year}`;
}

export function watchPath(year: number, series: PlayoffsSeriesCode, game: number | null): string {
  return `/api/v1/playoffs/watch?season=${year}&series=${series}${game ? `&game=${game}` : ""}`;
}

/** `?game=`：只收正整數官方場號（給 4A 當目標場）；其他值一律忽略，不報錯。 */
export function parseGameParam(raw: string | string[] | undefined): number | null {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (!v || !/^\d{1,3}$/.test(v)) return null;
  const n = Number(v);
  return n >= 1 ? n : null;
}

/** `?year=`：四位數年份，否則用預設年度。 */
export function parseYearParam(raw: string | string[] | undefined, fallback: number): number {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return v && /^\d{4}$/.test(v) ? Number(v) : fallback;
}

/** SSR 取 overview（`no-store`）。失敗回 null，由頁面顯示第 1 區讀取失敗。 */
export async function fetchPlayoffsOverview(year: number): Promise<PlayoffsOverview | null> {
  const base = process.env.API_URL ?? "http://localhost:4001";
  try {
    const res = await fetch(`${base}${overviewPath(year)}`, { cache: "no-store" });
    if (!res.ok) return null;
    const body = (await res.json()) as PlayoffsOverview;
    return body?.contract === "playoffs-overview/v1" ? body : null;
  } catch {
    return null;
  }
}
