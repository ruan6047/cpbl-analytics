// `/playoffs` 第 1 區系列累計榜（#288 S07 WP-G2）：`playoffs-series-summary/v1` 型別鏡像＋檢視純函式＋頁尾說明。
// 唯一來源是 `src/cpbl/playoffs/series_summary.py`；本檔只排字，⛔ 重算 ΔRE24、排序或涵蓋。
//
// 紅線：
// - 格內缺值只用「—」「待更新」（#281 6194693029）；原因寫頁尾（`seriesSummaryNotes`，MOUNT-CONTRACT r3 §2.4／§2.5）。
// - 排名已由後端以未四捨五入值排好；同展示值 ⛔ 加任何「領先」字樣；RE24 第一 ⛔ 稱 MVP（A05、G07）。
// - 單場 MVP 次數只來自官方單場 MVP；官方系列獎項只來自官方系列獎項窄表（WP-AWARDS），⛔ 由次數推獎項。
//   「官方尚未公布」（not_published，帶本站查核時間）與「本站尚未取得」（pending_source）格內都是「待更新」，
//   原因分寫頁尾；已公布者依官方順序列出完整獎項名稱與全部得主（共同得主不壓成一人）。
// - `seriesSummaryNotes` 純函式、同步：⛔ 讀時鐘、⛔ 發請求、⛔ 讀 window；key 依「同一件事」穩定、不帶索引或時間。
// - 三大轉折（WP-G3）：選取與排序全在後端（全系列母體、|ΔWP| 或整組降級 |ΔRE24|、時間序）；前端只排字。
//   勝率擺動沿用單場 recap 的「受益隊＋整數百分點」呈現（`WpSwingBadge`），⛔ 顯示勝率水平值。

import { marginText, situationText } from "./game-facts.ts";
import type { PlayoffsNote } from "./playoffs-notes.ts";
import { SERIES_NAME } from "./playoffs-series-view.ts";
import type { PlayoffsOverview, PlayoffsSeriesCode } from "./playoffs-types.ts";

export type SeriesSummaryStatus = "ok" | "partial" | "pending_pa" | "no_completed_games" | "unavailable";

export type SeriesSummaryBatter = {
  player_id: string; name: string | null; team_code: string | null;
  pa: number; re24_raw: number; mvp_count: number;
};

export type SeriesSummaryPitcher = {
  player_id: string; name: string | null; team_code: string | null;
  /** 面對打者數 */
  bf: number;
  /** 已轉號（−ΣΔRE24，打者視角轉成投手壓制；正＝壓制）。 */
  value_raw: number;
  mvp_count: number;
};

export type SeriesSummaryBlock = {
  kind_code: PlayoffsSeriesCode;
  status: SeriesSummaryStatus;
  games_total: number;
  games_covered: number;
  /** 未涵蓋場（未送達＋整場排除），系列場序。 */
  missing_games: number[];
  excluded_games: { series_game_no: number; reason: string }[];
  batters: SeriesSummaryBatter[];
  pitchers: SeriesSummaryPitcher[];
  pitcher_unattributed: number;
  mvp_counts: { player_id: string; name: string | null; team_code: string | null; count: number }[];
  mvp_missing_games: number[];
  awards: SeriesAwards;
  /** 三大轉折（WP-G3）；沒有已涵蓋場時 null。舊版 API 沒有此欄（undefined）。 */
  turning_points?: SeriesTurning | null;
  source: { pa_build_ids_hash: string | null; re_span: string };
};

export type SeriesAwardWinner = { player_id: string | null; name: string; team_code: string | null };

export type SeriesAwards =
  | { status: "pending_source" }
  | { status: "not_published"; revision: number; source_url: string; checked_at: string }
  | {
      status: "published"; revision: number; source_url: string; checked_at: string;
      awards: { award_name: string; award_type: "series_mvp" | "other"; winners: SeriesAwardWinner[] }[];
    };

/** 台北時間「M/D HH:mm」（只用 payload 時戳；⛔ 讀時鐘）。 */
export function taipeiShort(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  const m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(new Date(ms + 8 * 3_600_000).toISOString());
  return m ? `${Number(m[1])}/${Number(m[2])} ${m[3]}:${m[4]}` : iso;
}

export type TurningPerson = { player_id: string; name: string | null };

export type TurningPoint = {
  series_game_no: number;
  game_key: { year: number; kind_code: PlayoffsSeriesCode; game_sno: number };
  away_team_code: string;
  home_team_code: string;
  pa_id: string | null;
  pa_index: number;
  inning: number | null;
  half: string | null;
  outs_before: number | null;
  bases_before: string[];
  away_score_before: number | null;
  home_score_before: number | null;
  away_score_after: number | null;
  home_score_after: number | null;
  hitter: TurningPerson | null;
  pitcher: TurningPerson | null;
  result_action: string | null;
  /** 打擊方視角的得分期望變化。 */
  delta_re24: number | null;
  /** 主隊視角的勝率變化（0–1）；降級（|ΔRE24| 選取）時 null。 */
  delta_wp: number | null;
};

export type SeriesTurning = {
  signal: "delta_wp" | "delta_re24";
  min_abs: number;
  degraded: boolean;
  reason: string | null;
  degraded_games: number[];
  /** full＝全系列已完賽場都涵蓋；covered_only＝只有部分場次，只能稱「已涵蓋場次轉折」。 */
  scope: "full" | "covered_only";
  items: TurningPoint[];
};

export type SeriesSummary = {
  contract: "playoffs-series-summary/v1";
  algorithm: string;
  current: SeriesSummaryBlock | null;
  previous: SeriesSummaryBlock | null;
};

export const SUMMARY_COPY = {
  pending: "待更新",
  missing: "—",
  batterHeading: "打者",
  pitcherHeading: "投手",
  batterMetric: "相對局面得分期望累計",
  pitcherMetric: "壓制貢獻累計",
  mvpListHeading: "單場 MVP 次數",
  awardsLabel: "官方系列獎項",
  turningHeading: "三大轉折",
  turningCoveredHeading: "已涵蓋場次轉折",
  turningByWp: "依勝率擺動選出・依時間排列",
  turningByRe24: "依 |ΔRE24| 選出・依時間排列",
} as const;

/** 轉折小標：有未涵蓋場時不稱「三大轉折」（PRD：不能宣稱全系列前三）。 */
export function turningHeading(t: Pick<SeriesTurning, "scope">): string {
  return t.scope === "full" ? SUMMARY_COPY.turningHeading : SUMMARY_COPY.turningCoveredHeading;
}

export function turningCaption(t: Pick<SeriesTurning, "degraded">): string {
  return t.degraded ? SUMMARY_COPY.turningByRe24 : SUMMARY_COPY.turningByWp;
}

/** 局面：「G2・4 局上　1 出局　一壘、三壘有人・0–0」（沿用單場關鍵打席的 `situationText`／`marginText`）。 */
export function turningSituation(t: TurningPoint): string {
  const margin = marginText(t);
  return `G${t.series_game_no}・${situationText(t)}${margin ? `・${margin}` : ""}`;
}

/** 這個打席有沒有改變比分；改變時回前後兩段「客：主」（不做加法，直接取事件後快照）。 */
export function turningScoreChange(t: TurningPoint): { before: string; after: string } | null {
  const { away_score_before: ab, home_score_before: hb, away_score_after: aa, home_score_after: ha } = t;
  if (ab === null || hb === null || aa === null || ha === null) return null;
  if (ab === aa && hb === ha) return null;
  return { before: `${ab}：${hb}`, after: `${aa}：${ha}` };
}

/** 次要數字：打擊方的得分期望變化（一位小數帶號）。 */
export function turningRe24Text(t: TurningPoint): string | null {
  return t.delta_re24 === null ? null : `得分期望 ${signed1(t.delta_re24)}`;
}

/** 該系列是否要渲染累計榜（沒有完賽場就整塊省略，PRD「沒有就省略」）。 */
export function showSummary(b: SeriesSummaryBlock | null | undefined): b is SeriesSummaryBlock {
  return !!b && b.status !== "no_completed_games";
}

/** 榜格是否有數字可排（pending_pa／unavailable ⇒ 榜格「待更新」）。 */
export function boardReady(b: SeriesSummaryBlock): boolean {
  return b.status === "ok" || b.status === "partial";
}

/** 一位小數、帶正負號；四捨五入到 0 時不帶號（避免「-0.0」）。 */
export function signed1(v: number): string {
  const r = Math.round(v * 10) / 10;
  if (r === 0) return "0.0";
  return `${r > 0 ? "+" : "-"}${Math.abs(r).toFixed(1)}`;
}

/** 打者值文案（PRD：「相對局面得分期望，累計 +X.X 分」）。 */
export function batterValueText(v: number): string {
  return `相對局面得分期望，累計 ${signed1(v)} 分`;
}

/** 投手值文案（轉號後的壓制貢獻；方法寫在頁尾）。 */
export function pitcherValueText(v: number): string {
  return `壓制貢獻，累計 ${signed1(v)} 分`;
}

export function mvpBadge(n: number): string | null {
  return n >= 1 ? `單場 MVP ×${n}` : null;
}

export function playerName(p: { name: string | null }): string {
  return p.name ?? SUMMARY_COPY.missing;
}

export function summaryTitle(b: Pick<SeriesSummaryBlock, "kind_code">): string {
  return `${SERIES_NAME[b.kind_code]}累計榜`;
}

function gameList(nos: readonly number[]): string {
  return nos.map((n) => `G${n}`).join("、");
}

/** 未涵蓋場的說法：只有未送達／只有不完整／兩者都有。 */
function gapWord(b: SeriesSummaryBlock): string {
  const excluded = new Set(b.excluded_games.map((e) => e.series_game_no));
  const notArrived = b.missing_games.filter((n) => !excluded.has(n)).length;
  if (excluded.size && notArrived) return "尚未送達或不完整";
  return excluded.size ? "不完整" : "尚未送達";
}

/** 單一系列的頁尾說明（依資料）。key 帶系列代號以區分 E／C 同一類狀態。 */
function blockNotes(b: SeriesSummaryBlock): PlayoffsNote[] {
  const name = SERIES_NAME[b.kind_code];
  const k = (s: string) => `series.${s}.${b.kind_code}`;
  const out: PlayoffsNote[] = [];
  if (b.status === "partial") {
    out.push({ key: k("summary_partial"), text: `${name}累計榜只涵蓋 ${b.games_covered}/${b.games_total} 場；${gameList(b.missing_games)} 逐打席資料${gapWord(b)}，不是完整系列排行。` });
  } else if (b.status === "pending_pa") {
    out.push({ key: k("summary_pending"), text: `${name}已完賽 ${b.games_total} 場，逐打席資料${gapWord(b)}，累計榜待更新。` });
  } else if (b.status === "unavailable") {
    out.push({ key: k("summary_unavailable"), text: `${name}累計榜暫時無法讀取，比分與官方 MVP 不受影響。` });
  }
  if (b.pitcher_unattributed > 0) {
    out.push({ key: k("pitcher_unattributed"), text: `${name}有 ${b.pitcher_unattributed} 個打席中換投後保送的責任投手無法判定，未計入投手榜。` });
  }
  if (b.mvp_missing_games.length) {
    out.push({ key: k("mvp_missing"), text: `${name} ${gameList(b.mvp_missing_games)} 官方單場 MVP 本站尚未取得，次數未計入。` });
  }
  const aw = b.awards;
  if (aw.status === "not_published") {
    out.push({ key: k("awards_not_published"), text: `${name}官方尚未公布本系列獎項（本站 ${taipeiShort(aw.checked_at)} 查核）。` });
  } else if (aw.status === "published") {
    out.push({
      key: k("awards_source"), text: `${name}系列獎項依官方公布（本站 ${taipeiShort(aw.checked_at)} 查核）。`,
      source: { label: "官方公布頁", url: aw.source_url },
    });
  }
  const t = b.turning_points;
  if (t && boardReady(b)) {
    if (t.degraded) {
      out.push({ key: k("turning_degraded_re24"), text: `${name}勝率資料不完整，三大轉折改以得分期望變化絕對值排序。` });
    }
    if (t.scope === "covered_only") {
      out.push({ key: k("turning_partial"), text: `${name}轉折只涵蓋 ${b.games_covered}/${b.games_total} 場，不是全系列前三。` });
    }
  }
  return out;
}

/** 第 1 區累計榜的頁尾說明（契約 §2.5：以畫面上那份 overview 呼叫；null ⇒ 無）。 */
export function seriesSummaryNotes(o: Pick<PlayoffsOverview, "series_summary"> | null): PlayoffsNote[] {
  const s = o?.series_summary;
  if (!s) return [];
  const blocks = [s.current, s.previous].filter(showSummary);
  if (!blocks.length) return [];
  return [
    { key: "series.summary_method", text: "累計榜以本系列已完賽場的逐打席資料計算：打者依相對局面得分期望（ΔRE24）累計，投手依壓制貢獻（打者視角 RE24 轉號）排序；不是官方獎項。" },
    { key: "series.mvp_source", text: "單場 MVP 次數依官方單場 MVP 紀錄；系列 MVP 以官方系列獎項為準，本站不自行推選。" },
    ...(blocks.some((b) => b.awards.status === "pending_source")
      ? [{ key: "series.awards_pending", text: "官方系列獎項本站尚未取得，取得後更新。" }]
      : []),
    ...(blocks.some((b) => b.turning_points && boardReady(b))
      ? [{ key: "series.turning_method", text: "三大轉折取本系列勝率變化絕對值最大的 3 個打席，依時間排列；勝率為參考資訊，不是預測準確率。" }]
      : []),
    ...blocks.flatMap(blockNotes),
  ];
}
