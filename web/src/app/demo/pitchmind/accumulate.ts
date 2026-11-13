// PitchMind 示意頁的純函式（#452 修正三）：局面、情境標籤、基準格、是否納入、示意指標。
//
// 示意指標的動態值一律由「事件序列＋目前事件索引＋戰術＋打者」重新推導，不存任何可變計數器——
// 切換戰術、上一事件／下一事件、重複渲染都不會重置或重複計入。
//
// 示意用的簡化（都不是已驗證方法，正式指標待研究）：
//   1. 一球要「球種、區域都符合所選戰術，且壘上無人」才納入；否則回報未納入的原因。
//   2. 只算目前打者自己的球（含他本場先前打席）；其他打者另計在隊友欄位。
//   3. 每納入一球，動態值依該球的反應加減設定檔裡的示意點數，限制在 0–100。
//   4. 動態值達到或高於參考線＝已超過；差距在 nearBand 以內＝接近區內；其餘＝距離尚遠。
//   5. 觀察記在「投出前」的精確球數；參考線依目前球數取值，球數改變時參考線可能跟著變。

import type {
  BaselineEntry, BaselineTable, CountKey, GameEvent, Outcome, PitchEvent, ReactionKey, ReferenceTable,
  Situation, SourceKey,
} from "./model.ts";
import { DEMO_RULES, H_ZH, V_ZH, type Tactic } from "./tactics.config.ts";

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

// ───────── 情蒐基準格與參考線 ─────────
export function baselineEntry(
  table: BaselineTable, tacticId: string, source: SourceKey, batter: string, ck: CountKey,
): BaselineEntry {
  const t = table[tacticId];
  if (!t) return null;
  if (source === "league") return t.league[ck] ?? null;
  if (source === "pitcher") return t.pitcher[ck] ?? null;
  return t.batters[batter]?.[source]?.[ck] ?? null;
}

/** 基準格裡某類反應的次數；出棒＝來球數減未出棒。 */
export function reactionCount(entry: NonNullable<BaselineEntry>, r: ReactionKey): number {
  const [n, take, whiff, foul, weak, solid, hard] = entry;
  return { swing: n - take, take, whiff, foul, weak, solid, hard }[r];
}

export type Cell =
  | { state: "missing" }
  | { state: "insufficient"; k: number; n: number }
  | { state: "zero"; k: 0; n: number }
  | { state: "ok"; k: number; n: number; rate: number };

/** 基準格 → 顯示狀態。缺值、樣本不足、觀察到 0 次、一般四態互斥；分母＝符合條件來球數。 */
export function baselineCell(entry: BaselineEntry, reaction: ReactionKey, minN: number): Cell {
  if (entry == null) return { state: "missing" };
  const n = entry[0];
  const k = reactionCount(entry, reaction);
  if (n < minN) return { state: "insufficient", k, n };
  if (k === 0) return { state: "zero", k: 0, n };
  return { state: "ok", k, n, rate: k / n };
}

/** 參考線（示意）：戰術＋打者＋目前精確球數；沒有資料時為 null（不補零）。 */
export function referenceFor(refs: ReferenceTable, tacticId: string, batter: string, ck: CountKey): number | null {
  return refs[tacticId]?.[batter]?.[ck] ?? null;
}

export type Status = "far" | "near" | "over";
/** distance＝參考線 − 動態值（正＝還沒到，≤0＝已達到或超過）。 */
export function statusOf(value: number, reference: number, nearBand: number): { status: Status; distance: number } {
  const distance = reference - value;
  return { status: distance <= 0 ? "over" : distance <= nearBand ? "near" : "far", distance };
}

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

// ───────── 本場相關觀察與示意指標的動態值 ─────────
export type Observation = {
  eventIdx: number; eventId: string; seq: number; inning: number;
  /** 投出前的精確球數（這筆觀察所屬的情境） */
  count: CountKey;
  outcome: Outcome;
  /** 本次增減（已套用 0–100 上下限後的實際變動） */
  delta: number;
  /** 納入這筆之後的動態值 */
  value: number;
  inCurrentPa: boolean;
  resultText: string;
};

export type Tally = Record<ReactionKey, number> & { opp: number };
const emptyTally = (): Tally => ({ opp: 0, swing: 0, take: 0, whiff: 0, foul: 0, weak: 0, solid: 0, hard: 0 });
function addTo(t: Tally, o: Outcome) {
  t.opp += 1;
  t[o] += 1;
  if (o !== "take") t.swing += 1;
}

export type LastEvent =
  | { kind: "none" }
  | { kind: "other_batter"; batter: string }
  | { kind: "included"; observation: Observation }
  | { kind: "excluded"; reasons: string[]; text: string };

export type DynamicState = {
  batter: string;
  /** 示意指標的動態值（0–100） */
  value: number;
  /** 目前打者自己、符合所選戰術條件的來球與各類反應次數（含本場先前打席） */
  tally: Tally;
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
  events: readonly GameEvent[], idx: number, t: Tactic,
  /** 關注打者；省略＝目前局面的打者。 */
  focusBatter?: string,
): DynamicState {
  const end = clampIdx(events, idx);
  const cur = events[end].after;
  const who = focusBatter ?? cur.batter;
  const inPa = new Set(who === cur.batter ? currentPaIndices(events, end) : []);
  const tally = emptyTally();
  const teammates = { ...emptyTally(), batters: [] as string[] };
  const observations: Observation[] = [];
  let value = DEMO_RULES.min;
  for (let i = 1; i <= end; i++) {
    const e = events[i];
    const pre = events[i - 1].after;
    if (e.kind !== "pitch" || pre.pitcher !== cur.pitcher || !inclusionOf(e, pre, t).included) continue;
    if (pre.batter !== who) {
      addTo(teammates, e.outcome);
      if (!teammates.batters.includes(pre.batter)) teammates.batters.push(pre.batter);
      continue;
    }
    addTo(tally, e.outcome);
    const next = Math.max(DEMO_RULES.min, Math.min(DEMO_RULES.max, value + t.points[e.outcome]));
    observations.push({
      eventIdx: i, eventId: e.id, seq: e.seq, inning: pre.inning, count: countOf(pre), outcome: e.outcome,
      delta: next - value, value: next, inCurrentPa: inPa.has(i), resultText: e.resultText,
    });
    value = next;
  }
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
    batter: who, value, tally, observations,
    priorInnings: [...new Set(observations.filter((o) => !o.inCurrentPa).map((o) => o.inning))],
    currentPaOpp: observations.filter((o) => o.inCurrentPa).length, last, teammates,
  };
}

/** 比較區間一次需要的全部數值：參考線、動態值、狀態、距離，以及參考線是否因情境或換人而改變。 */
export function indicatorAt(events: readonly GameEvent[], idx: number, t: Tactic, refs: ReferenceTable) {
  const end = clampIdx(events, idx);
  const cur = events[end].after;
  const dyn = dynamicAt(events, end, t);
  const ck = countOf(cur);
  const reference = referenceFor(refs, t.id, cur.batter, ck);
  const st = reference == null ? null : statusOf(dyn.value, reference, DEMO_RULES.nearBand);
  const lastObs = dyn.last.kind === "included" ? dyn.last.observation : null;
  // 參考線變動的原因：同一打者球數改變，或換了打者
  const pre = end > 0 && events[end].kind === "pitch" ? events[end - 1].after : null;
  let refChange: { kind: "count"; from: CountKey; to: CountKey; fromRef: number | null }
    | { kind: "batter"; from: string; to: string } | null = null;
  if (pre && pre.batter !== cur.batter) refChange = { kind: "batter", from: pre.batter, to: cur.batter };
  else if (pre && countOf(pre) !== ck) {
    const fromRef = referenceFor(refs, t.id, cur.batter, countOf(pre));
    if (fromRef !== reference) refChange = { kind: "count", from: countOf(pre), to: ck, fromRef };
  }
  return {
    dyn, count: ck, reference, value: dyn.value,
    status: st?.status ?? null, distance: st?.distance ?? null,
    delta: lastObs ? lastObs.delta : null,
    prevValue: lastObs ? lastObs.value - lastObs.delta : null,
    refChange,
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
  /** 該打席中符合所選戰術條件的球數 */
  includedCount: number;
  /** 該打者的示意指標動態值在這個打席前後 */
  valueBefore: number; valueAfter: number;
  list: PaPitch[];
};

/** 同一個半局內剛結束、且不是目前打者的那個打席（供轉達）；沒有則為 null。 */
export function completedPaSummary(events: readonly GameEvent[], idx: number, t: Tactic): PaSummary | null {
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
  return {
    batter, inning, pitches: list.length, resultText: (events[k] as PitchEvent).resultText,
    includedCount: list.filter((p) => p.inclusion.included).length,
    valueBefore: dynamicAt(events, indices[0] - 1, t, batter).value,
    valueAfter: dynamicAt(events, k, t, batter).value,
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
