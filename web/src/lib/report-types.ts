import type { Card as Ability } from "../components/ability-card";
import type { JourneyRow, SummarySeries, PostseasonJourney } from "./postseason-journey.ts";

export type ReportKind = "E" | "C";
export type ReportTab = "overview" | "pitchers" | "fielders";
export type Counts = Record<string, number | string | null>;
export type Period = { status: "available" | "not_appeared" | "missing"; counts: Counts; sample: Counts; covered_game_keys: string[]; expected_game_keys: string[]; coverage_status: string; source: string; cutoff_label: string };
export type ReportPlayer = {
  player_id: string; team_code: string; role: "batting" | "pitching"; name: string | null; bats: string | null; throws: string | null;
  periods: Record<"series" | "regular" | "opponent_regular", Period>;
  last_game: Period; ability: Ability;
  official_pr: Record<string, number | string | null> | null;
  traits: { traits: Counts | null; league: Counts } | null;
  splits: Record<string, number | string | null>[];
  fielding: { pos: string; g: number | null }[];
  vs_starter: { status: string; pitcher_id?: string | null; counts?: Counts; sample?: Counts; updated_at?: string | null; coverage_status?: string };
  pitching_usage: { recent_games?: Record<string, unknown>[]; total_outs?: number | null; total_pitches?: number | null; consecutive_days?: number | null; days_to_next?: number | null; [k: string]: unknown } | null;
};
export type ReportSource = { source: string; source_version: string | null; fetched_at?: string | null; updated_at?: string | null; last_seen_at?: string | null; read_at?: string; reference: string; cutoff_basis?: string; coverage_status?: string };
export type Starter = { acnt: string | null; name: string | null; status: string; team_code: string; observed_at?: string | null; source_version?: string | null };
export type LineupTeamEvidence = { status: string; source_type?: string; raw_status?: string | null; source_version?: string | null; fetched_at?: string | null; observed_at?: string | null; first_content_at?: string | null; first_status_at?: string | null; first_started_at?: string | null; boundary_sources?: { source_type: string; source_version?: string | null; raw_status?: string | null; fetched_at: string }[] };
export type Report = {
  status: "ok" | "not_found" | "not_final"; season: number; kind_code: ReportKind; game_sno: number;
  game?: { year: number; kind_code: string; game_sno: number; game_date: string; venue: string | null; home_team_code: string; away_team_code: string; home_score: number; away_score: number };
  anchor?: { cutoff_label: string; through_game_keys: string[] };
  journey_context?: { summary: SummarySeries[]; rows: JourneyRow[]; sources: ReportSource[]; context_hash: string; cutoff_date: string; through_game_keys: string[]; order_consistent: boolean };
  next_game?: { year: number; kind_code: string; game_sno: number; game_date: string; away_team_code: string; home_team_code: string; venue: string | null; away_starter: Starter; home_starter: Starter } | null;
  players?: ReportPlayer[];
  population?: { team_code: string; status: string; complete: boolean; source_url?: string | null; roster_version?: string | null }[];
  field_candidates?: Record<string, Record<string, { status: string; g: number; player_ids: string[] }>>;
  sources?: ReportSource[]; read_at?: string;
  regular_coverage?: { year: number; kind: string; closed_before_X: boolean; covered_game_keys: string[] };
  teams?: { team: string; axes: { key: string; label: string; semantics: string }[]; seasons: { n_teams: number; axes: Record<string, { z: number; rank: number; raw: number | null }> }[] }[];
  watch_points?: { team_code: string; player_id: string; origin: string; count_line: Counts; question: string }[];
  announcements?: { lineup: { status: string; items: { player_id: string; team_code: string; pos: string; order: number; name?: string | null }[]; source_type?: string; raw_status?: string | null; source_url?: string; team_evidence?: Record<string, LineupTeamEvidence>; source_version?: string | null; observed_at?: string | null; pregame_evidence?: { is_play_ball?: string; fetched_at?: string; first_started_at?: string | null } } };
  comparison?: ReportComparison | null;
  coverage?: { games: number; with_pitching: number; with_batting: number };
};
export type ReportView = { report: Report; journey: PostseasonJourney | null; updating: boolean };
/** 第一讀只取 journey context；完整讀帶同 context_hash，有正式 Y 時另帶 Y 身分。 */
export type ReportRequest = { contextOnly: true } | { contextHash: string } | { kind: ReportKind; sno: number; contextHash: string };

/** X回顧維持頂層；正式Y未完賽亦可有獨立系列背景，不替換X身分。 */
export type ReportComparison = Pick<Report, "players" | "population" | "teams" | "watch_points" | "field_candidates" | "announcements" | "coverage" | "regular_coverage"> & {
  game: NonNullable<Report["next_game"]>; kind_code: ReportKind;
  series_game_keys: string[]; usage_cutoff_label: string;
};

/** Y 觀戰報告入口只取截至場 X 身分；不含 Y 判定。 */
export type ReportAnchor = { status: "ok" | "final" | "not_found" | "no_anchor"; season: number; kind_code: ReportKind; game_sno: number; anchor?: { kind_code: ReportKind; game_sno: number } };
