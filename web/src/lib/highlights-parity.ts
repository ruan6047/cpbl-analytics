// #337 機械檢查（plan-1 WP3）：同一場「單場頁本場焦點」與「/playoffs 逐場焦點」是否逐字一致。
//
// 兩邊都跑**頁面實際用的函式**，不另寫規則：
//   * 單場頁：`/live` 原始回應 → 頁面既有完賽判定 → `gameHighlightsSource`（game-live-page.tsx 同一呼叫；
//     判決標籤取 `/facts` 的 `umpire_call` 作第三參數，#338）
//   * /playoffs：highlights 回應 → `highlightsRows`（series-highlights.tsx 同一呼叫）
// 比較 status（ok／待更新）與標籤（text＋team、順序）。純函式：npm test 用夾具跑，
// `web/scripts/check-highlights-parity.ts` 用正式站公開 API 跑。

import { buildHighlights, num, type Highlight, type HighlightInput } from "./game-highlights.ts";
import { gameHighlightsSource, type GameHighlightsSource, type UmpireCallInput } from "./game-highlights-source.ts";
import {
  applyLiveSnapshot, canShowPostgameConclusions, officialCompletionOf, type LiveApiResponse,
} from "./live-game.ts";
import { highlightsRows, type HighlightsPayload, type HighlightsRow } from "./playoffs-series-highlights.ts";

/** 單場頁的「已完賽」：逐字照 game-live-page.tsx（覆蓋後的 game＋snapshot 走 `canShowPostgameConclusions`）。 */
export function pageCompletedOf(raw: LiveApiResponse): boolean {
  const data = applyLiveSnapshot(raw);
  const g = data.game;
  if (!g) return false;
  return canShowPostgameConclusions(data.live_snapshot ?? null,
    num(g.home_score as number | string | null) + num(g.away_score as number | string | null), officialCompletionOf(g));
}

/** 單場頁焦點（現行路徑）：覆蓋前 DB 列＋頁面完賽判定＋`/facts` 的判決標籤（#338）。 */
export function singleGamePageHighlights(raw: LiveApiResponse, umpireCall: UmpireCallInput = null): GameHighlightsSource {
  return gameHighlightsSource(raw as unknown as HighlightInput, pageCompletedOf(raw), umpireCall);
}

/** #337 修正前的單場頁路徑（`buildHighlights(applyLiveSnapshot(raw))`）：只給負控用，證明檢查抓得到原缺陷。 */
export function legacySingleGamePageHighlights(raw: LiveApiResponse): GameHighlightsSource {
  const completed = pageCompletedOf(raw);
  if (!completed) return { status: "none", tags: [] };
  return { status: "ok", tags: buildHighlights(applyLiveSnapshot(raw) as unknown as HighlightInput, true) };
}

export type ParitySide = { status: "ok" | "pending" | "none" | "missing"; tags: string[] };
export type GameParity = {
  key: string;
  label: string;
  game_sno: number;
  equal: boolean;
  page: ParitySide;
  playoffs: ParitySide;
};

const tagText = (h: Highlight) => (h.team ? `${h.text}［${h.team}］` : h.text);

/** 一場比對：status 相同，且 ok 時標籤（text＋team、順序）逐字相同。 */
export function compareGame(page: GameHighlightsSource | null, row: HighlightsRow): GameParity {
  const p: ParitySide = page ? { status: page.status, tags: page.tags.map(tagText) } : { status: "missing", tags: [] };
  const q: ParitySide = { status: row.status, tags: row.tags.map(tagText) };
  const equal = p.status === q.status && JSON.stringify(p.tags) === JSON.stringify(q.tags);
  return { key: row.key, label: row.label, game_sno: Number(row.key.split("-")[1]), equal, page: p, playoffs: q };
}

/** 整個系列：/playoffs 列出的每一場（已完賽場）都要找得到對應 `/live` 回應並一致。
 *  `umpires`＝game_sno → 該場 `/facts` 的 `umpire_call`（#338；未給的場次視為無判決標籤）。 */
export function checkSeriesParity(
  payload: HighlightsPayload,
  lives: ReadonlyMap<number, LiveApiResponse>,
  pageFn: (raw: LiveApiResponse, umpireCall?: UmpireCallInput) => GameHighlightsSource = singleGamePageHighlights,
  umpires: ReadonlyMap<number, UmpireCallInput> = new Map(),
): { ok: boolean; games: GameParity[] } {
  const games = highlightsRows(payload).map((row) => {
    const sno = Number(row.key.split("-")[1]);
    const raw = lives.get(sno);
    return compareGame(raw ? pageFn(raw, umpires.get(sno) ?? null) : null, row);
  });
  return { ok: games.every((g) => g.equal), games };
}
