// PitchMind 示意頁的純函式（#452）：局面、情境標籤、參考界線、動態累積與三段狀態。
//
// 動態累積一律由「事件序列＋目前事件索引＋戰術」重新推導，不存任何可變計數器——
// 切換戰術、上一事件／下一事件、重複渲染都不會重置或重複計入。
//
// 示意規則（展演說明區逐條列出，非已驗證方法）：
//   1. 只有「符合戰術條件（球種＋區域＋壘上無人）」的實際來球會更新該戰術的動態值。
//   2. 每次更新加上設定檔中該反應的示意點數，結果夾在 0–100。
//   3. 球數改變、換打者都不重置累積；參考界線依目前球數：兩好球時用兩好球界線，否則用一般界線。
//   4. 動態值 ≥ 參考值＝已超過；差距在 nearBand 以內＝正在接近；其餘＝距離尚遠。
//   5. 方向＝最近一次更新相對前一次的增減。

import type { GameEvent, PitchEvent, Situation } from "./model.ts";
import { DEMO_RULES, type Tactic } from "./tactics.config.ts";

export type CountTag = "首球" | "球數領先" | "球數落後" | "平球數" | "滿球數";
export const COUNT_TAGS: readonly CountTag[] = ["首球", "球數領先", "球數落後", "平球數", "滿球數"];

/** 情境標籤（投手觀點），五類互斥、依序判定：0-0 首球（不另標平球數）、3-2 滿球數、
 *  好多於壞＝領先、壞多於好＝落後、其餘好壞相等（1-1、2-2）＝平球數。 */
export function countTag(balls: number, strikes: number): CountTag {
  if (balls === 0 && strikes === 0) return "首球";
  if (balls === 3 && strikes === 2) return "滿球數";
  if (strikes > balls) return "球數領先";
  if (balls > strikes) return "球數落後";
  return "平球數";
}

const clampIdx = (events: readonly GameEvent[], idx: number) => Math.max(0, Math.min(idx, events.length - 1));

/** idx 事件發生後、下一球投出前的局面，以及「資料截至」的事件。 */
export function situationAt(events: readonly GameEvent[], idx: number): { situation: Situation; cutoff: GameEvent } {
  const e = events[clampIdx(events, idx)];
  return { situation: e.after, cutoff: e };
}

const basesEmpty = (s: Situation) => !s.bases.first && !s.bases.second && !s.bases.third;

export function matchesTactic(p: PitchEvent, pre: Situation, t: Tactic): boolean {
  return basesEmpty(pre) && p.pitch === t.condition.pitch && t.condition.h.includes(p.h) && t.condition.v.includes(p.v);
}

/** 參考界線（示意規則 3）。 */
export function referenceFor(t: Tactic, s: Situation): number {
  return s.strikes >= 2 ? t.reference.twoStrike : t.reference.preTwoStrike;
}

export type Status = "far" | "near" | "over";
/** distance＝參考值 − 動態值（正＝尚未到界線，≤0＝已超過）。 */
export function statusOf(value: number, reference: number, nearBand: number): { status: Status; distance: number } {
  const distance = reference - value;
  return { status: distance <= 0 ? "over" : distance <= nearBand ? "near" : "far", distance };
}

export type SeriesPoint = { eventIdx: number; value: number; delta: number; reference: number };

/** 截至 idx，此戰術每一次更新後的動態值（只含符合條件的事件）。 */
export function dynamicSeries(events: readonly GameEvent[], idx: number, t: Tactic): SeriesPoint[] {
  const end = clampIdx(events, idx);
  const out: SeriesPoint[] = [];
  let v = DEMO_RULES.min;
  for (let i = 1; i <= end; i++) {
    const e = events[i];
    const pre = events[i - 1].after;
    if (e.kind !== "pitch" || !matchesTactic(e, pre, t)) continue;
    const next = Math.max(DEMO_RULES.min, Math.min(DEMO_RULES.max, v + t.points[e.reaction]));
    out.push({ eventIdx: i, value: next, delta: next - v, reference: referenceFor(t, e.after) });
    v = next;
  }
  return out;
}

export type Direction = "up" | "down" | "flat" | "none";
export function dynamicAt(events: readonly GameEvent[], idx: number, t: Tactic):
  { value: number; delta: number; direction: Direction; updates: number; lastEventIdx: number | null } {
  const s = dynamicSeries(events, idx, t);
  const last = s[s.length - 1];
  if (!last) return { value: DEMO_RULES.min, delta: 0, direction: "none", updates: 0, lastEventIdx: null };
  return {
    value: last.value, delta: last.delta, updates: s.length, lastEventIdx: last.eventIdx,
    direction: last.delta > 0 ? "up" : last.delta < 0 ? "down" : "flat",
  };
}

/** 快讀區一次需要的全部數值。 */
export function quickRead(events: readonly GameEvent[], idx: number, t: Tactic) {
  const { situation } = situationAt(events, idx);
  const reference = referenceFor(t, situation);
  const d = dynamicAt(events, idx, t);
  const st = statusOf(d.value, reference, DEMO_RULES.nearBand);
  return { reference, ...d, ...st };
}

export type PaPitch = { event: PitchEvent; pre: Situation; matched: boolean };

/** 目前（或剛結束的）打席內我方投手的實際來球，標示是否符合目前戰術條件。 */
export function currentPaPitches(events: readonly GameEvent[], idx: number, t: Tactic): PaPitch[] {
  const end = clampIdx(events, idx);
  let start = end;
  // 往回找到這個打席的第一球：遇到打者上場事件，或前一球的打者不同即停
  const batterOf = (i: number) => (i > 0 ? events[i - 1].after.batter : null);
  const target = events[end].kind === "pitch" ? batterOf(end) : null;
  if (target == null) return [];
  while (start - 1 > 0 && events[start - 1].kind === "pitch" && batterOf(start - 1) === target) start--;
  const out: PaPitch[] = [];
  for (let i = start; i <= end; i++) {
    const e = events[i];
    const pre = events[i - 1].after;
    if (e.kind === "pitch") out.push({ event: e, pre, matched: matchesTactic(e, pre, t) });
  }
  return out;
}
