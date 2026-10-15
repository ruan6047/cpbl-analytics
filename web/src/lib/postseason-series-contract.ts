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

// —— `postseason-series-context/v2`（#283 S02）——
// `/api/v1/postseason-summary` 的 `series_context`。唯一來源 `src/cpbl/postseason_contract.py`
// （規則常數、§60 推導、勝場／決勝）與 `src/cpbl/playoffs/state.py`（T0–T5）。本檔只鏡射形狀：
// ⛔ 前端不得重算 initial_wins／decided／winner／not_needed／next，一律讀這裡的欄位。

export type GameKeyV2 = { year: number; kind_code: "E" | "C"; game_sno: number };

export type SeriesStatusV2 = "pending" | "active" | "decided" | "unknown";

export type SeriesSideV2 = {
  team_code: string | null;
  initial_wins: number | null;
  initial_wins_basis: "rule_standings" | "announcement_confirmed" | "unsourced" | null;
  game_wins: number;
  total_wins: number | null;
  remaining: number | null;
  clinch: boolean;
  facing_elimination: boolean;
};

export type SeriesV2 = {
  kind_code: "E" | "C";
  series_id: { year: number; kind_code: "E" | "C"; rule_version: string | null; teams: (string | null)[] };
  participants_status: "known" | "pending_e_winner" | "unknown";
  best_of: number | null;
  wins_needed: number | null;
  sides: SeriesSideV2[];
  ties: number;
  series_status: SeriesStatusV2;
  conflict_reason: "team_mismatch" | "participants_unresolved" | "both_reached" | "game_after_decided"
    | "announcement_mismatch" | null;
  winner: string | null;
  decided_by_game_key: GameKeyV2 | null;
  summary_kind: "advance_summary" | "championship_summary";
  corrections: { game_key: GameKeyV2; reason: "official_change_unresolved" | "official_final_not_completed" }[];
  counted_game_keys: GameKeyV2[];
  analysis_status: "pending" | "partial" | "ready" | "reconciling";
};

export type TargetStatusV2 = "scheduled" | "live" | "suspended" | "final" | "postponed" | "unknown";

export type SeriesGameV2 = {
  game_key: GameKeyV2;
  official_game_sno: number;
  series_game_no: number;
  announced_slot_id: string | null;
  game_date: string | null;
  venue: string | null;
  away_team_code: string;
  home_team_code: string;
  away_score: number | null;
  home_score: number | null;
  completed: boolean;
  result: "home_win" | "away_win" | "tie" | null;
  counted_for_wins: boolean;
  official_status: SeriesContractOfficialStatus;
  target_status: TargetStatusV2;
  official_mvp_id: string | null;
  analysis: "published" | "reconciling" | "pending" | null;
};

export type TeamSlotV2 = { code: string } | { placeholder: "E_WINNER" };
export type VenueV2 = { name: string } | { by_winner: Record<string, string> } | { unknown: true };

export type ArrangedSlotV2 = {
  /** 公告格＝場序（E1…、C1…）；公告外的真實列（動態加賽 G8 等）＝`C-sno8` 形式，⛔ 不是公告場序。 */
  slot_id: string;
  kind_code: "E" | "C";
  /** 公告格＝公告場序；公告外的真實列＝該列在系列真實列中的順序。 */
  seq: number;
  /** false＝公告沒有、但真實存在的 E／C 列（#283 再審 F1）。 */
  announced: boolean;
  announced_date: string | null;
  /** 顯示日期：對到真實列時以列為準。 */
  date: string;
  start: string | null;
  away: TeamSlotV2 | null;
  home: TeamSlotV2 | null;
  venue: VenueV2;
  conditional: boolean;
  official_sno: number | null;
  game_key: GameKeyV2 | null;
  change: { kind: "moved"; announced_date: string } | { kind: "changed" } | null;
  display_status: "final" | "scheduled" | "announced" | "result_pending" | "not_needed";
  hidden_not_needed: boolean;
};

export type RosterLeadV2 = { url: string; label: string; published_on: string; kind: "二手報導" };

export type AnnouncementV2 = {
  url: string;
  published_on: string;
  captured_at: string;
  checks: { on: string; scope: "E" | "C" | "announcement"; url: string; ok: boolean; note: string }[];
  series: {
    E: { name: string; best_of: number; wins_needed: number; handicap_team: string; teams: [string, string]; roster_leads: RosterLeadV2[] };
    C: { name: string; best_of: number; wins_needed: number; seeded_team: string; opponent_from: "E"; roster_leads: RosterLeadV2[] };
  };
  reserve_days: { date: string; series: "C"; note: string }[];
};

export type LayoutV2 = {
  kind_code: "E" | "C";
  layout_state: "T0" | "T1" | "T2" | "T3" | "T4" | "T5";
  layout_reason: string;
  section_order: number[];
  summary_kind: "advance_summary" | "championship_summary" | null;
  target_game_key: GameKeyV2 | null;
  target_status: TargetStatusV2 | null;
  window: { basis: "ended_at" | "observed_final" | "unknown"; started_at: string | null; ends_at: string | null };
  overlays: ("postponed" | "suspended" | "status_unknown" | "pending_update")[];
};

export type PostseasonSeriesContextV2 = {
  contract: "postseason-series-context/v2";
  algorithm_version: string;
  year: number;
  rule_version: string | null;
  rule_status: "sourced" | "unsourced";
  context_version: string;
  source_manifest: { source: string; scope: string; version_or_hash: string | null; observed_at: string | null; status: string }[];
  as_of: PostseasonSeriesContractV1["as_of"] & { now: string };
  coverage: SeriesContractCoverage;
  missing_reason: string[];
  series: { E: SeriesV2; C: SeriesV2 };
  games: SeriesGameV2[];
  announcement: AnnouncementV2 | null;
  arrangement: { slots: ArrangedSlotV2[]; next_slot_id: string | null; remaining: boolean } | null;
  state: LayoutV2 & { default_series: "E" | "C"; by_series: { E: LayoutV2; C: LayoutV2 } };
  teams: {
    series: "E" | "C"; team_code: string;
    roster_status: "missing" | "draft" | "submitted";
    registration_status: "confirmed" | "partial" | "unknown";
    starter_status: "missing" | "partial" | "announced" | "changed" | "unknown";
  }[];
};
