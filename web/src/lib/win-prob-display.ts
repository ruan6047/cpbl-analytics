// 勝率 [win probability / WP] 的**顯示夾層**（2026-08-06 需求方人工審裁決）。
//
// 規則：**比賽終結前的勝率顯示不得出現 100%／0%**——非終點的顯示值一律夾到
// [1%, 99%]；只有終場那一點豁免，可顯示 100%／0%。
//
// 為什麼：需求方原話「雖然我知道統計數據是 100%」。模型在極端局面確實會算到 0.999+，
// 但把它顯示成 100% 會讀成「已成定局」，而比賽尚未結束——這是**呈現層的誠實**問題，
// 不是模型問題。WP 本身全 scope 時間外驗證 unsupported、只作參考資訊，更沒有理由讓
// 顯示值宣稱確定性。
//
// 邊界（這是本檔的唯一職責，跨檔一致靠這裡）：
//   * **只動顯示層**。儲存值、`/api/v1/games/{sno}/winprob` 與 `/recap-wp` 的回傳、
//     可重現雜湊、任何比較／排序／歸因一律用原值，不得改吃夾過的值。
//   * Y 軸刻度（0/25/50/75/100）是**座標尺規**不是某一點的勝率，維持原樣——夾住尺規
//     反而會讓讀者誤判曲線的參考框架。

/** 非終點顯示值的下界／上界。 */
export const WP_DISPLAY_MIN = 0.01;
export const WP_DISPLAY_MAX = 0.99;

/**
 * 顯示用勝率（0–1）。`terminal=true`＝終場那一點，豁免夾層。
 * 非有限值原樣回傳，交由呼叫端的缺值處理，不靜默補 0.5。
 */
export function displayWp(wp: number, terminal = false): number {
  if (!Number.isFinite(wp)) return wp;
  if (terminal) return wp;
  return Math.min(WP_DISPLAY_MAX, Math.max(WP_DISPLAY_MIN, wp));
}

/** 顯示用百分比（0–100，保留一位小數；整數值不帶小數點）。 */
export function displayWpPct(wp: number, terminal = false): number {
  const value = displayWp(wp, terminal);
  if (!Number.isFinite(value)) return value;
  return Math.round(value * 1000) / 10;
}

/** 顯示用整數百分比（0–100），供只放得下整數的條狀元件使用。 */
export function displayWpPctInt(wp: number, terminal = false): number {
  const value = displayWp(wp, terminal);
  if (!Number.isFinite(value)) return value;
  return Math.round(value * 100);
}

/**
 * 終場點的判定：`/winprob` 的序列末端補一筆沒有打席身分的收斂點
 * （`evt` 與 `inning` 皆為 null），代表勝負已定的結果值 1／0／0.5。
 */
export function isTerminalWpPoint(point: { evt?: string | null; inning?: number | null }): boolean {
  return (point.evt ?? null) === null && (point.inning ?? null) === null;
}
