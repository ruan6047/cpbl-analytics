// PitchMind 示意頁的純函式（#452）：局面、情境標籤、基準格狀態與本場累積。
//
// 累積一律由「事件序列＋目前事件索引」重新推導，不存任何可變計數器——
// 所以切換戰術、上一球／下一球、重複渲染都不會重複累積或清除已發生的事件。

import type {
  BaselineEntry, BaselineTable, CountKey, GameEvent, PitchEvent, ReactionKey, Situation,
} from "./model.ts";
import { REACTIONS, type Tactic } from "./tactics.config.ts";

export type CountTag = "首球" | "球數領先" | "球數落後" | "滿球數";
export const COUNT_TAGS: readonly CountTag[] = ["首球", "球數領先", "球數落後", "滿球數"];

/** 情境標籤（投手觀點）：0-0 首球、3-2 滿球數、好多於壞＝領先、壞多於好＝落後；1-1、2-2 不歸類。 */
export function countTag(balls: number, strikes: number): CountTag | null {
  if (balls === 0 && strikes === 0) return "首球";
  if (balls === 3 && strikes === 2) return "滿球數";
  if (strikes > balls) return "球數領先";
  if (balls > strikes) return "球數落後";
  return null;
}

export const countKey = (balls: number, strikes: number) => `${balls}-${strikes}` as CountKey;

/** idx 事件發生後、下一球投出前的局面，以及「資料截至」的事件。 */
export function situationAt(events: readonly GameEvent[], idx: number): { situation: Situation; cutoff: GameEvent } {
  const e = events[Math.max(0, Math.min(idx, events.length - 1))];
  return { situation: e.after, cutoff: e };
}

const before = (events: readonly GameEvent[], i: number): Situation | null => (i > 0 ? events[i - 1].after : null);
const basesEmpty = (s: Situation) => !s.bases.first && !s.bases.second && !s.bases.third;

export function matchesTactic(p: PitchEvent, pre: Situation, t: Tactic): boolean {
  return basesEmpty(pre) && p.family === t.condition.family
    && t.condition.h.includes(p.h) && t.condition.v.includes(p.v);
}

export type Cell =
  | { state: "missing" }
  | { state: "insufficient"; k: number; n: number }
  | { state: "zero"; k: 0; n: number }
  | { state: "ok"; k: number; n: number; rate: number };

/** 基準格 → 顯示狀態。缺值、樣本不足、觀察到 0 次、一般四態互斥。 */
export function baselineCell(entry: BaselineEntry, reaction: ReactionKey, minN: number): Cell {
  if (entry == null) return { state: "missing" };
  const [n, swing, whiff, grounder] = entry;
  const k = reaction === "swing" ? swing : reaction === "whiff" ? whiff : grounder;
  const den = REACTIONS[reaction].den === "n" ? n : swing;
  if (den < minN) return { state: "insufficient", k, n: den };
  if (k === 0) return { state: "zero", k: 0, n: den };
  return { state: "ok", k, n: den, rate: k / den };
}

type Tally = { opp: number; reactions: Record<ReactionKey, { k: number; den: number }> };
const emptyTally = (): Tally => ({
  opp: 0,
  reactions: { swing: { k: 0, den: 0 }, whiff: { k: 0, den: 0 }, grounder: { k: 0, den: 0 } },
});
function addTo(t: Tally, p: PitchEvent) {
  t.opp += 1;
  t.reactions.swing.den += 1;
  if (p.swing) {
    t.reactions.swing.k += 1;
    t.reactions.whiff.den += 1;
    t.reactions.grounder.den += 1;
    if (p.whiff) t.reactions.whiff.k += 1;
    if (p.grounder) t.reactions.grounder.k += 1;
  }
}

export type Accumulation = {
  /** 本場、目前打者、符合戰術條件的來球。 */
  batter: Tally;
  /** 本場、同一投手對其他打者、符合條件的來球（隊友共同反應的原始次數）。 */
  teammates: Tally;
  /** 相對預期：每次機會依該球精確球數的打者長期基準加總；基準不足者不納入並計數。 */
  expected: Record<ReactionKey, { observed: number; expected: number; used: number; skipped: number }>;
};

export function accumulateAt(
  events: readonly GameEvent[], idx: number, t: Tactic, baselines: BaselineTable, minN: number,
  /** 關注打者；省略＝目前局面的打者。 */
  focusBatter?: string,
): Accumulation {
  const end = Math.max(0, Math.min(idx, events.length - 1));
  const cur = events[end].after;
  const who = focusBatter ?? cur.batter;
  const batter = emptyTally();
  const teammates = emptyTally();
  const expected = {
    swing: { observed: 0, expected: 0, used: 0, skipped: 0 },
    whiff: { observed: 0, expected: 0, used: 0, skipped: 0 },
    grounder: { observed: 0, expected: 0, used: 0, skipped: 0 },
  };
  const long = baselines[t.id]?.long ?? {};
  for (let i = 0; i <= end; i++) {
    const e = events[i];
    const pre = before(events, i);
    if (e.kind !== "pitch" || !pre || pre.pitcher !== cur.pitcher || !matchesTactic(e, pre, t)) continue;
    if (pre.batter !== who) { addTo(teammates, e); continue; }
    addTo(batter, e);
    const entry = long[countKey(pre.balls, pre.strikes)] ?? null;
    for (const r of ["swing", "whiff", "grounder"] as const) {
      const inDen = REACTIONS[r].den === "n" || e.swing;
      if (!inDen) continue;
      const hit = r === "swing" ? e.swing : r === "whiff" ? e.whiff : e.grounder;
      expected[r].observed += hit ? 1 : 0;
      const c = baselineCell(entry, r, minN);
      if (c.state === "ok" || c.state === "zero") {
        expected[r].expected += c.state === "ok" ? c.rate : 0;
        expected[r].used += 1;
      } else expected[r].skipped += 1;
    }
  }
  return { batter, teammates, expected };
}

export type PaPitch = {
  event: PitchEvent; pre: Situation; matched: boolean; speedDiff: number | null;
};

/** 目前打席（idx 之前最近一次打者上場起）我方投手的實際來球，標示是否符合目前戰術條件。 */
export function currentPaPitches(events: readonly GameEvent[], idx: number, t: Tactic): PaPitch[] {
  const end = Math.max(0, Math.min(idx, events.length - 1));
  let start = end;
  while (start > 0 && events[start].kind !== "pa_start") start--;
  const out: PaPitch[] = [];
  for (let i = start + 1; i <= end; i++) {
    const e = events[i];
    const pre = before(events, i);
    if (e.kind !== "pitch" || !pre) continue;
    const prev = out[out.length - 1];
    out.push({ event: e, pre, matched: matchesTactic(e, pre, t), speedDiff: prev ? e.speed - prev.event.speed : null });
  }
  return out;
}

/** 本場目前打者已結束的打席結果（對戰紀錄用）。 */
export function batterPaResults(events: readonly GameEvent[], idx: number, batter: string): { inning: number; text: string }[] {
  const end = Math.max(0, Math.min(idx, events.length - 1));
  const out: { inning: number; text: string }[] = [];
  for (let i = 1; i <= end; i++) {
    const e = events[i];
    const pre = before(events, i);
    if (e.kind === "pitch" && pre && pre.batter === batter && e.after.batter !== batter) {
      out.push({ inning: pre.inning, text: e.resultText });
    }
  }
  return out;
}
