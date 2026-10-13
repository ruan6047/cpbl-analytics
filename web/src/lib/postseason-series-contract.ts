// `postseason-series-contract/v1` 的 TS 型別鏡像（#268 WP1／WP5）。唯一來源是
// `src/cpbl/postseason_contract.py`；本檔只鏡射形狀，不含任何邏輯、不新增端點。
//
// 給 #238 等消費端的語意（與 Python docstring 一致）：
// - `games` 只含 `cpbl.games` 真實列的 (year, kind_code, game_sno)；不從公告場序、E 或 stats 推 C 的場號。
// - `completed` 與 `/api/v1/postseason-summary` 同一支 canonical 判準（2026 起 E／C 只認官方 final／完賽證據）。
// - 未完成場的比分一律 null（DB 的 0–0 是佔位）；未知一律 null／"unknown"，不零填。
// - `as_of.last_refresh_*` 只代表最後一次整鏈刷新；是否已涵蓋最新完賽看 `as_of.coverage`。
// - 不含晉級、名單、報告語意與開賽時間。

export type SeriesContractCoverage = "covered" | "pending_update" | "unknown";

export type SeriesContractOfficialStatus = "final" | "scheduled" | "postponed" | "reserved" | "unknown";

export type SeriesContractPendingGame = {
  year: number;
  kind_code: string;
  game_sno: number;
  /** 異動訊號在官方與本站都沒有日期時為 null（不猜）。 */
  game_date: string | null;
  official_status: string;
  reason: "official_final_not_ingested" | "past_game_without_result" | "live_final_not_ingested"
    | "official_status_unknown" | "live_status_unavailable" | "official_change_not_ingested";
};

export type SeriesContractGame = {
  year: number;
  kind_code: "E" | "C";
  game_sno: number;
  game_date: string | null;
  away_team_code: string;
  home_team_code: string;
  venue: string | null;
  completed: boolean;
  official_status: SeriesContractOfficialStatus;
  away_score: number | null;
  home_score: number | null;
};

export type PostseasonSeriesContractV1 = {
  contract: "postseason-series-contract/v1";
  year: number;
  as_of: {
    taipei_date: string;
    last_completed_game_date: string | null;
    last_refresh_at: string | null;
    last_refresh_ok: boolean | null;
    last_refresh_scope: string | null;
    coverage: SeriesContractCoverage;
    pending_games: SeriesContractPendingGame[];
  };
  games: SeriesContractGame[];
  completed_keys: [number, string, number][];
};
