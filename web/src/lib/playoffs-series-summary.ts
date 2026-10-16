// `/playoffs` 第 1 區系列累計榜（#288 S07 WP-G2）：`playoffs-series-summary/v1` 型別鏡像＋檢視純函式＋頁尾說明。
// 唯一來源是 `src/cpbl/playoffs/series_summary.py`；本檔只排字，⛔ 重算 ΔRE24、排序或涵蓋。
//
// 紅線：
// - 格內缺值只用「—」「待更新」（#281 6194693029）；原因寫頁尾（`seriesSummaryNotes`，MOUNT-CONTRACT r3 §2.4／§2.5）。
// - 排名已由後端以未四捨五入值排好；同展示值 ⛔ 加任何「領先」字樣；RE24 第一 ⛔ 稱 MVP（A05、G07）。
// - 單場 MVP 次數只來自官方單場 MVP；官方系列獎項 G2 一律「待更新」（⛔ 由次數推獎項）。
// - `seriesSummaryNotes` 純函式、同步：⛔ 讀時鐘、⛔ 發請求、⛔ 讀 window；key 依「同一件事」穩定、不帶索引或時間。

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
  awards: { status: "pending_source" };
  source: { pa_build_ids_hash: string | null; re_span: string };
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
} as const;

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
    ...blocks.flatMap(blockNotes),
  ];
}
