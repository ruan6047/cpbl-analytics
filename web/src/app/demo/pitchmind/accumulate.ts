// PitchMind 示意頁的純函式（#452 修正二）：局面、情境標籤、基準格、是否納入、本場相關觀察。
//
// 本場相關觀察一律由「事件序列＋目前事件索引＋戰術＋打者」重新推導，不存任何可變計數器——
// 切換戰術、上一事件／下一事件、重複渲染都不會重置或重複計入。
//
// 示意用的簡化（展演說明區逐條列出，都不是已驗證方法）：
//   1. 一球要「球種、區域都符合所選戰術，且壘上無人」才納入；否則回報未納入的原因。
//   2. 觀察只算目前打者自己的球（含他本場先前打席）；其他打者另計在隊友欄位，不混入。
//   3. 每筆觀察記在「投出前」的精確球數；之後球數改變不搬動它。
//   4. 本場變化＝已觀察到的關注反應次數 − 依各球所屬球數的打者長期比例加總的預期次數。
//      跨球數直接相加是為了示意而做的簡化；跨情境如何共享累積尚未定案。

import type {
  BaselineEntry, BaselineTable, CountKey, GameEvent, PitchEvent, ReactionKey, Situation, SourceKey,
} from "./model.ts";
import { H_ZH, V_ZH, type Tactic } from "./tactics.config.ts";

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

export const countKey = (balls: number, strikes: number) => `${balls}-${strikes}` as CountKey;
const countOf = (s: Situation) => countKey(s.balls, s.strikes);
const clampIdx = (events: readonly GameEvent[], idx: number) => Math.max(0, Math.min(idx, events.length - 1));
const basesEmpty = (s: Situation) => !s.bases.first && !s.bases.second && !s.bases.third;

/** idx 事件發生後、下一球投出前的局面，以及「資料截至」的事件。 */
export function situationAt(events: readonly GameEvent[], idx: number): { situation: Situation; cutoff: GameEvent } {
  const e = events[clampIdx(events, idx)];
  return { situation: e.after, cutoff: e };
}

// ───────── 是否納入所選戰術 ─────────
export type Inclusion = { included: true } | { included: false; reasons: string[]; text: string };

export function inclusionOf(p: PitchEvent, pre: Situation, t: Tactic): Inclusion {
  const reasons: string[] = [];
  if (!basesEmpty(pre)) reasons.push("壘上有人");
  if (p.pitch !== t.condition.pitch) reasons.push(`球種不符（${p.pitch}）`);
  if (!t.condition.h.includes(p.h) || !t.condition.v.includes(p.v)) reasons.push(`區域不符（${H_ZH[p.h]}${V_ZH[p.v]}）`);
  return reasons.length ? { included: false, reasons, text: `本球未納入：${reasons.join("、")}` } : { included: true };
}

// ───────── 情蒐基準格 ─────────
export function baselineEntry(
  table: BaselineTable, tacticId: string, source: SourceKey, batter: string, ck: CountKey,
): BaselineEntry {
  const t = table[tacticId];
  if (!t) return null;
  if (source === "league") return t.league[ck] ?? null;
  if (source === "pitcher") return t.pitcher[ck] ?? null;
  return t.batters[batter]?.[source]?.[ck] ?? null;
}

export type Cell =
  | { state: "missing" }
  | { state: "insufficient"; k: number; n: number }
  | { state: "zero"; k: 0; n: number }
  | { state: "ok"; k: number; n: number; rate: number };

/** 基準格 → 顯示狀態。缺值、樣本不足、觀察到 0 次、一般四態互斥；分母＝符合條件來球數。 */
export function baselineCell(entry: BaselineEntry, reaction: ReactionKey, minN: number): Cell {
  if (entry == null) return { state: "missing" };
  const [n, swing, whiff, grounder] = entry;
  const k = reaction === "swing" ? swing : reaction === "whiff" ? whiff : grounder;
  if (n < minN) return { state: "insufficient", k, n };
  if (k === 0) return { state: "zero", k: 0, n };
  return { state: "ok", k, n, rate: k / n };
}

const reacted = (p: PitchEvent, r: ReactionKey) => (r === "swing" ? p.swing : r === "whiff" ? p.whiff : p.grounder);

// ───────── 打席邊界 ─────────
/** 目前打者這個打席已投出的球（事件索引）。打者剛上場、尚未面對投球時為空。 */
function currentPaIndices(events: readonly GameEvent[], end: number): number[] {
  const cur = events[end].after;
  const out: number[] = [];
  for (let i = end; i >= 1; i--) {
    const e = events[i];
    const pre = events[i - 1].after;
    if (e.kind !== "pitch" || pre.batter !== cur.batter || pre.inning !== cur.inning || e.after.batter !== cur.batter) break;
    out.unshift(i);
  }
  return out;
}

// ───────── 本場相關觀察 ─────────
export type Observation = {
  eventIdx: number; eventId: string; seq: number; inning: number;
  /** 投出前的精確球數（這筆觀察所屬的情境） */
  count: CountKey;
  /** 是否出現所選戰術的首要關注反應 */
  reacted: boolean;
  /** 該情境的打者長期比例；無可用基準時為 null */
  expectedRate: number | null;
  /** 本次增減＝（有反應 1／無反應 0）− 長期比例 */
  delta: number | null;
  /** 納入這筆之後的本場變化 */
  cumulative: number;
  inCurrentPa: boolean;
  resultText: string;
};

type Tally = { opp: number; swing: number; whiff: number; grounder: number };
const emptyTally = (): Tally => ({ opp: 0, swing: 0, whiff: 0, grounder: 0 });
function addTo(t: Tally, p: PitchEvent) {
  t.opp += 1;
  if (p.swing) t.swing += 1;
  if (p.whiff) t.whiff += 1;
  if (p.grounder) t.grounder += 1;
}

export type LastEvent =
  | { kind: "none" }
  | { kind: "other_batter"; batter: string }
  | { kind: "included"; observation: Observation }
  | { kind: "excluded"; reasons: string[]; text: string };

export type DynamicState = {
  batter: string;
  /** 目前打者自己、符合所選戰術條件的來球數（含本場先前打席） */
  opp: number;
  tally: Tally;
  /** 首要關注反應：觀察次數、預期次數、本場變化＝觀察 − 預期 */
  observed: number;
  expected: number;
  value: number;
  /** 有／無可用基準的觀察筆數 */
  used: number;
  skipped: number;
  observations: Observation[];
  /** 先前打席的觀察來自哪幾局（來源說明用） */
  priorInnings: number[];
  currentPaOpp: number;
  /** 截止事件對「目前打者＋所選戰術」的意義 */
  last: LastEvent;
  /** 同場其他打者對同一投手、符合條件的來球（獨立欄位，不計入打者本人） */
  teammates: Tally & { batters: string[] };
};

export function dynamicAt(
  events: readonly GameEvent[], idx: number, t: Tactic, table: BaselineTable, minN: number,
  /** 關注打者；省略＝目前局面的打者。 */
  focusBatter?: string,
): DynamicState {
  const end = clampIdx(events, idx);
  const cur = events[end].after;
  const who = focusBatter ?? cur.batter;
  const primary = t.reactions[0];
  const inPa = new Set(who === cur.batter ? currentPaIndices(events, end) : []);
  const tally = emptyTally();
  const teammates = { ...emptyTally(), batters: [] as string[] };
  const observations: Observation[] = [];
  let observed = 0, expected = 0, value = 0, used = 0, skipped = 0;
  for (let i = 1; i <= end; i++) {
    const e = events[i];
    const pre = events[i - 1].after;
    if (e.kind !== "pitch" || pre.pitcher !== cur.pitcher || !inclusionOf(e, pre, t).included) continue;
    if (pre.batter !== who) {
      addTo(teammates, e);
      if (!teammates.batters.includes(pre.batter)) teammates.batters.push(pre.batter);
      continue;
    }
    addTo(tally, e);
    const did = reacted(e, primary);
    const cell = baselineCell(baselineEntry(table, t.id, "long", who, countOf(pre)), primary, minN);
    const rate = cell.state === "ok" ? cell.rate : cell.state === "zero" ? 0 : null;
    const delta = rate == null ? null : (did ? 1 : 0) - rate;
    if (did) observed += 1;
    if (rate == null) skipped += 1; else { expected += rate; used += 1; value += delta ?? 0; }
    observations.push({
      eventIdx: i, eventId: e.id, seq: e.seq, inning: pre.inning, count: countOf(pre), reacted: did,
      expectedRate: rate, delta, cumulative: value, inCurrentPa: inPa.has(i), resultText: e.resultText,
    });
  }
  const priorInnings = [...new Set(observations.filter((o) => !o.inCurrentPa).map((o) => o.inning))];
  const cutoff = events[end];
  let last: LastEvent = { kind: "none" };
  if (cutoff.kind === "pitch" && end > 0) {
    const pre = events[end - 1].after;
    if (pre.batter !== who) last = { kind: "other_batter", batter: pre.batter };
    else {
      const inc = inclusionOf(cutoff, pre, t);
      last = inc.included
        ? { kind: "included", observation: observations[observations.length - 1] }
        : { kind: "excluded", reasons: inc.reasons, text: inc.text };
    }
  }
  return {
    batter: who, opp: tally.opp, tally, observed, expected, value, used, skipped, observations, priorInnings,
    currentPaOpp: observations.filter((o) => o.inCurrentPa).length, last, teammates,
  };
}

// ───────── 上一球所屬情境 vs 目前情境 ─────────
export function lastPitchContext(events: readonly GameEvent[], idx: number):
  { event: PitchEvent; pre: Situation; cur: Situation; sameBatter: boolean } | null {
  const end = clampIdx(events, idx);
  const e = events[end];
  if (e.kind !== "pitch" || end === 0) return null;
  const pre = events[end - 1].after;
  return { event: e, pre, cur: e.after, sameBatter: pre.batter === e.after.batter };
}

// ───────── 打席 ─────────
export type PaPitch = { event: PitchEvent; pre: Situation; inclusion: Inclusion; speedDiff: number | null };

function toPaPitches(events: readonly GameEvent[], indices: number[], t: Tactic): PaPitch[] {
  const out: PaPitch[] = [];
  for (const i of indices) {
    const e = events[i];
    if (e.kind !== "pitch") continue;
    const pre = events[i - 1].after;
    const prev = out[out.length - 1];
    out.push({ event: e, pre, inclusion: inclusionOf(e, pre, t), speedDiff: prev ? e.speed - prev.event.speed : null });
  }
  return out;
}

/** 目前打者這個打席我方投手的實際來球。 */
export function currentPaPitches(events: readonly GameEvent[], idx: number, t: Tactic): PaPitch[] {
  const end = clampIdx(events, idx);
  return toPaPitches(events, currentPaIndices(events, end), t);
}

export type PaSummary = {
  batter: string; inning: number; pitches: number; resultText: string;
  /** 該打席中符合所選戰術條件的球數，以及其中出現首要關注反應的球數 */
  includedCount: number; reactedCount: number;
  /** 該打者的本場變化在這個打席前後的值 */
  valueBefore: number; valueAfter: number;
  list: PaPitch[];
};

/** 同一個半局內剛結束、且不是目前打者的那個打席（供轉達）；沒有則為 null。 */
export function completedPaSummary(
  events: readonly GameEvent[], idx: number, t: Tactic, table: BaselineTable, minN: number,
): PaSummary | null {
  const end = clampIdx(events, idx);
  const cur = events[end].after;
  let k = -1;
  for (let i = end; i >= 1; i--) {
    const e = events[i];
    if (e.kind === "pitch" && e.after.batter !== events[i - 1].after.batter) { k = i; break; }
  }
  if (k < 0) return null;
  const batter = events[k - 1].after.batter;
  const inning = events[k - 1].after.inning;
  if (inning !== cur.inning || batter === cur.batter) return null;
  const indices: number[] = [];
  for (let i = k; i >= 1; i--) {
    const pre = events[i - 1].after;
    if (events[i].kind !== "pitch" || pre.batter !== batter || pre.inning !== inning) break;
    indices.unshift(i);
  }
  const list = toPaPitches(events, indices, t);
  const primary = t.reactions[0];
  const included = list.filter((p) => p.inclusion.included);
  const last = events[k] as PitchEvent;
  return {
    batter, inning, pitches: list.length, resultText: last.resultText,
    includedCount: included.length, reactedCount: included.filter((p) => reacted(p.event, primary)).length,
    valueBefore: dynamicAt(events, indices[0] - 1, t, table, minN, batter).value,
    valueAfter: dynamicAt(events, k, t, table, minN, batter).value,
    list,
  };
}

/** 本場某打者已結束的打席結果（對戰紀錄用）。 */
export function batterPaResults(events: readonly GameEvent[], idx: number, batter: string): { inning: number; text: string }[] {
  const end = clampIdx(events, idx);
  const out: { inning: number; text: string }[] = [];
  for (let i = 1; i <= end; i++) {
    const e = events[i];
    const pre = events[i - 1].after;
    if (e.kind === "pitch" && pre.batter === batter && e.after.batter !== batter) out.push({ inning: pre.inning, text: e.resultText });
  }
  return out;
}

// ───────── 我方投手量測（只描述球速與位置） ─────────
export type PitcherMeasure = {
  pitch: string; count: number; avgSpeed: number | null; lastSpeed: number | null;
  /** 實際進壘位置落在所選戰術區域的球數（只是位置描述，不是執行到位率） */
  inTargetZone: number;
  points: PitchEvent[];
};

export function pitcherMeasure(events: readonly GameEvent[], idx: number, t: Tactic): PitcherMeasure {
  const end = clampIdx(events, idx);
  const cur = events[end].after;
  const points: PitchEvent[] = [];
  for (let i = 1; i <= end; i++) {
    const e = events[i];
    if (e.kind === "pitch" && events[i - 1].after.pitcher === cur.pitcher && e.pitch === t.condition.pitch) points.push(e);
  }
  const sum = points.reduce((a, p) => a + p.speed, 0);
  return {
    pitch: t.condition.pitch, count: points.length,
    avgSpeed: points.length ? Math.round((sum / points.length) * 10) / 10 : null,
    lastSpeed: points.length ? points[points.length - 1].speed : null,
    inTargetZone: points.filter((p) => t.condition.h.includes(p.h) && t.condition.v.includes(p.v)).length,
    points,
  };
}
