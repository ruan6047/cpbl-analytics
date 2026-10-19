// 單場頁「本場焦點」的資料來源（#337 plan-1 方案 A、WP1）。
//
// 焦點標籤**只**用 `/api/v1/games/{sno}/live` 回應中 live snapshot 覆蓋**前**的 DB 列（同一份回應本來就帶），
// 與 `/playoffs` 逐場焦點吃同一份資料、同一個到齊判準、同一個函式 `buildHighlights(…, true)`：
//   * 已完賽＋DB 到齊   ⇒ ok：與 /playoffs 同一份標籤（48h 內有 snapshot 時也一樣，含失誤類）
//   * 已完賽＋DB 未到齊 ⇒ pending：不出任何標籤，焦點位置顯示「待更新」（與 /playoffs 同字樣）
//   * 未完賽            ⇒ none：不顯示焦點（現行行為不變）
// ⛔ 不要把 `applyLiveSnapshot` 之後的資料傳進來：snapshot 的打者列沒有 errors、記分板 error_cnt 為 null，
// 失誤類標籤會因此消失，兩頁就會不一致（#337 的根因）。其他區塊照舊吃覆蓋後的資料。
// 「已完賽」由呼叫端沿用頁面既有的 `canShowPostgameConclusions`，本檔不做任何完賽判定。
// 判決標籤（#338，#285 批次 G）：後端判定、不在 `/live` 內；呼叫端以第三參數傳 `/facts` 的 `umpire_call`，
// 併進同一份輸入（/playoffs 側是 highlights 每場的 `umpire_call`），仍交同一個 `buildHighlights` 排字。

import { buildHighlights, type Highlight, type HighlightInput } from "./game-highlights.ts";
import { HIGHLIGHTS_COPY } from "./playoffs-series-highlights.ts";

/** 到齊判準的四表，逐字對應 `src/cpbl/playoffs/series_highlights.py` 的 `ready`（另需 game 列存在）。
 *  ⛔ 兩邊必須同步改；`highlights-parity.test.ts` 會讀後端原始碼比對這份清單。 */
export const HIGHLIGHTS_READY_TABLES = ["scoreboard", "livelog", "batting", "pitching"] as const;

/** 焦點「待更新」字樣：沿用 /playoffs 逐場焦點的同一常數，⛔ 另寫一份。 */
export const HIGHLIGHTS_PENDING_TEXT = HIGHLIGHTS_COPY.pending;

export type GameHighlightsSource =
  | { status: "ok"; tags: Highlight[] }
  | { status: "pending"; tags: [] }
  | { status: "none"; tags: [] };

export type UmpireCallInput = HighlightInput["umpire_call"];

/** DB 列到齊才回規則輸入（只取規則讀的五表＋decisions，加上呼叫端給的判決標籤）；未到齊回 null。 */
export function dbHighlightInput(raw: HighlightInput | null | undefined,
  umpireCall: UmpireCallInput = null): HighlightInput | null {
  if (!raw || !raw.game) return null;
  if (!HIGHLIGHTS_READY_TABLES.every((t) => Array.isArray(raw[t]) && raw[t].length > 0)) return null;
  return {
    game: raw.game,
    scoreboard: raw.scoreboard,
    livelog: raw.livelog,
    batting: raw.batting,
    pitching: raw.pitching,
    decisions: raw.decisions ?? {},
    umpire_call: umpireCall ?? null,
  };
}

/** `raw`＝`/live` 原始回應（snapshot 覆蓋前）；`completed`＝頁面既有完賽判定的結果；
 *  `umpireCall`＝`/facts` 的 `umpire_call`（未取得／舊 API ⇒ 不出判決標籤）。 */
export function gameHighlightsSource(raw: HighlightInput | null | undefined, completed: boolean,
  umpireCall: UmpireCallInput = null): GameHighlightsSource {
  if (!completed) return { status: "none", tags: [] };
  const input = dbHighlightInput(raw, umpireCall);
  return input ? { status: "ok", tags: buildHighlights(input, true) } : { status: "pending", tags: [] };
}
