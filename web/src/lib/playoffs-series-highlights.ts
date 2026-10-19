// `/playoffs` 第 1 區「逐場焦點」（#288 S07 WP-K3）：端點型別鏡像＋純函式（列模型、版本比對、重抓鍵）。
// 唯一來源是 `src/cpbl/playoffs/series_highlights.py`（只投影欄位）；標籤由單場頁同一個函式
// `buildHighlights`（`./game-highlights.ts`）在瀏覽器算，⛔ 在這裡或後端複製任何條件。
// 例外：判決標籤（#285 批次 G）由後端判定，每場 `umpire_call` 併進 input 後交同一個 buildHighlights 排字。
//
// 需求方裁定（#288 6218173554）：系列總結區逐場列出該場「本場焦點」標籤（含球迷用語），沒有標籤顯示「—」。
// 資料未到（data_status=pending）或讀取失敗／版本不一致且沒有上一份 ⇒「待更新」。未完賽場不列。

import { buildHighlights, type Highlight, type HighlightInput } from "./game-highlights.ts";
import { gameHref } from "./playoffs-series-view.ts";
import type { PlayoffsSeriesCode } from "./playoffs-types.ts";

export type HighlightsGame = {
  series_game_no: number;
  game_key: { year: number; kind_code: PlayoffsSeriesCode; game_sno: number };
  data_status: "ok" | "pending";
  input: HighlightInput | null;
  /** 判決標籤後端結果（#285 批次 G；舊 API 沒有）。 */
  umpire_call?: { team_code: string | null; reason?: string | null } | null;
};

export type HighlightsPayload = {
  contract: "playoffs-highlights/v1";
  context_version: string;
  series: PlayoffsSeriesCode;
  status: "ok" | "no_completed_games";
  games: HighlightsGame[];
};

export const HIGHLIGHTS_COPY = {
  heading: "逐場焦點",
  pending: "待更新",
  none: "—",
} as const;

export function highlightsPath(year: number, series: PlayoffsSeriesCode): string {
  return `/api/v1/playoffs/highlights?season=${year}&series=${series}`;
}

/** 重抓鍵：該系列 block 的版本與涵蓋任一改變才重抓（隨 overview 30 秒輪詢更新；⛔ 元件自己開計時器）。 */
export function highlightsKey(contextVersion: string | null | undefined, b: {
  kind_code: string; games_total: number; games_covered: number; source: { pa_build_ids_hash: string | null };
}): string {
  return [b.kind_code, contextVersion ?? "", b.games_total, b.games_covered, b.source.pa_build_ids_hash ?? ""].join("|");
}

export type HighlightsState =
  | { kind: "idle" }
  | { kind: "data"; data: HighlightsPayload }
  | { kind: "failed"; previous: HighlightsPayload | null };

/** 收到回應：版本與畫面上 overview 相同才採用；否則保留上一份（⛔ 拼接不同版本），沒有上一份 ⇒ failed。 */
export function acceptHighlights(prev: HighlightsState, payload: HighlightsPayload | null,
                                 contextVersion: string | null | undefined): HighlightsState {
  const previous = prev.kind === "data" ? prev.data : prev.kind === "failed" ? prev.previous : null;
  if (payload && payload.contract === "playoffs-highlights/v1" && contextVersion
      && payload.context_version === contextVersion) {
    return { kind: "data", data: payload };
  }
  return previous ? { kind: "data", data: previous } : { kind: "failed", previous: null };
}

export type HighlightsRow = {
  key: string;
  label: string;
  href: string;
  status: "ok" | "pending";
  tags: Highlight[];
};

/** 列模型：每個已完賽場一列；ok ⇒ 跑單場頁同一個 buildHighlights(input, true)；pending ⇒ 不算。 */
export function highlightsRows(data: HighlightsPayload): HighlightsRow[] {
  return data.games.map((g) => ({
    key: `${g.game_key.kind_code}-${g.game_key.game_sno}`,
    label: `G${g.series_game_no}`,
    href: gameHref(g),
    status: g.data_status === "ok" && g.input ? "ok" : "pending",
    tags: g.data_status === "ok" && g.input ? buildHighlights({ ...g.input, umpire_call: g.umpire_call ?? null }, true) : [],
  }));
}

/** 頁尾固定一條（契約 §9；依資料的缺資料原因無法在頁尾純函式取得，併入同一條說明，見 WP-K3 報告）。 */
export const HIGHLIGHTS_NOTE = {
  key: "series.highlights_method",
  text: "逐場焦點沿用單場賽況頁的「本場焦點」標籤（含球迷用語）；沒有符合條件的場次顯示「—」，資料未到或暫時無法讀取顯示「待更新」。",
} as const;
