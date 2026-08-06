// UX-GAME-PA1：逐打席卡片的**即時勝率** [win probability] ——由**曲線既有資料源** join，
// 不新增後端欄位。
//
// WP 守門（沿 UX-GAME-RECAP1 的三階裁決，本卡不擴張）：
//   * 資料源＝`/api/v1/games/{sno}/winprob` 的逐打席序列，**與同頁勝率曲線同一份 response**
//     ——曲線本來就逐打席公開繪製水平值，卡片上的條與曲線上的點是同一個數字的兩種畫法，
//     屬**同資訊類、零新增暴露面**。
//   * 打席事實流（`/facts` 的 `plate_appearances`）**維持零 WP 欄位**：後端守門不動，
//     這裡沒有任何後端改動。
//   * 顯示夾層仍由 `lib/win-prob-display.ts` 單一擁有（本模組只回原值，不夾）。
//
// 為什麼要 join 而不是直接吃曲線的點：曲線的點是**近似分組**（連續同打者）的產物，
// canonical 打席可能把兩個近似點併成一個（打席中途代打），也可能對不到（來源修正）。
// 故一律以「該打席的事件號區間」對曲線取值，取不到就誠實回 null，不猜。

import { isTerminalWpPoint } from "./win-prob-display.ts";

/** 曲線的一個點（`components/win-prob-chart.tsx` 的 `WpPoint` 子集）。 */
export type WpCurvePoint = { evt: string | null; inning: number | null; wp: number };

export type PaSwing = {
  /** 打席前／後的主隊勝率（0–1，原值未夾）。 */
  before: number;
  after: number;
  /** `after` 取自終場收斂點（顯示夾層須豁免）。 */
  terminal: boolean;
  /** 主隊視角的變化量；顯示層再轉受益隊（`wpSwingLabel`）。 */
  delta: number;
};

/** 預先整理曲線點，避免每個打席都重掃整場（單場 ~80 點 × ~80 打席）。 */
export type WpCurveIndex = {
  points: { evt: number; wp: number }[];
  /** 終場收斂點（`evt`／`inning` 皆為 null）；未完賽時為 null。 */
  terminal: number | null;
};

export function indexWpCurve(points: WpCurvePoint[] | null | undefined): WpCurveIndex {
  const out: WpCurveIndex = { points: [], terminal: null };
  for (const p of points ?? []) {
    if (!Number.isFinite(p.wp)) continue;
    if (isTerminalWpPoint(p)) { out.terminal = p.wp; continue; }
    if (p.evt == null) continue;
    const evt = Number(p.evt);
    if (Number.isFinite(evt)) out.points.push({ evt, wp: p.wp });
  }
  out.points.sort((a, b) => a.evt - b.evt);
  return out;
}

/**
 * 以打席的**事件號區間**自曲線取該打席的勝率變化。
 *
 * - `before`＝區間內的**第一個**曲線點（canonical 打席併掉兩個近似點時，取靠前那個，
 *   使 before→after 涵蓋整個打席）；區間內無點時退回區間前最後一點。
 * - `after`＝區間**之後**的第一個曲線點；沒有下一個打席（本場最後一個打席）時取終場
 *   收斂點並標 `terminal`。
 * - 任一端取不到 → 回 `null`（**不以 0 或 0.5 冒充**）。
 */
export function joinPaSwing(
  index: WpCurveIndex, firstEventNo: number | string | null | undefined,
  lastEventNo: number | string | null | undefined,
): PaSwing | null {
  const first = Number(firstEventNo);
  const last = Number(lastEventNo ?? firstEventNo);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  const { points, terminal } = index;

  let before: number | null = null;
  for (const p of points) {
    if (p.evt >= first && p.evt <= last) { before = p.wp; break; }
    if (p.evt < first) before = p.wp;      // 區間內無點時的退路：區間前最後一點
    else break;
  }
  if (before === null) return null;

  const next = points.find((p) => p.evt > last);
  const after = next ? next.wp : terminal;
  if (after === null || after === undefined) return null;

  return { before, after, terminal: !next, delta: after - before };
}
