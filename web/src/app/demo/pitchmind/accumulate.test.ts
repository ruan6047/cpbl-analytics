import assert from "node:assert/strict";
import test from "node:test";

import {
  baselineCell, baselineEntry, completedPaSummary, countTag, currentPaPitches, dynamicAt, inclusionOf,
  lastPitchContext, pitcherMeasure, situationAt,
} from "./accumulate.ts";
import { DEMO_BASELINES, DEMO_EVENTS, DEMO_MIN_N, REPLAY_START } from "./demo-data.ts";
import type { CountKey, PitchEvent } from "./model.ts";
import { TACTICS } from "./tactics.config.ts";

const OH = TACTICS.find((t) => t.id === "outside-high-fastball")!;
const OL = TACTICS.find((t) => t.id === "outside-low-slider")!;
const idxOf = (id: string) => DEMO_EVENTS.findIndex((e) => e.id === id);
const dyn = (id: string, t = OH, batter?: string) =>
  dynamicAt(DEMO_EVENTS, idxOf(id), t, DEMO_BASELINES, DEMO_MIN_N, batter);
/** 打者長期在某球數的出棒比例（測試用，直接取自示意基準）。 */
const rate = (batter: string, ck: CountKey, t = OH) => {
  const c = baselineCell(baselineEntry(DEMO_BASELINES, t.id, "long", batter, ck), "swing", DEMO_MIN_N);
  assert.equal(c.state, "ok");
  return c.state === "ok" ? c.rate : NaN;
};
const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} ≠ ${b}`);

test("countTag：五類互斥，0-0 只標首球", () => {
  assert.equal(countTag(0, 0), "首球");
  assert.equal(countTag(0, 1), "球數領先");
  assert.equal(countTag(1, 0), "球數落後");
  assert.equal(countTag(1, 1), "平球數");
  assert.equal(countTag(2, 2), "平球數");
  assert.equal(countTag(3, 2), "滿球數");
});

test("baselineCell 區分缺值／樣本不足／觀察到 0 次／一般", () => {
  assert.deepEqual(baselineCell(null, "swing", DEMO_MIN_N), { state: "missing" });
  assert.equal(baselineCell([5, 3, 0, 2], "swing", DEMO_MIN_N).state, "insufficient");
  assert.equal(baselineCell([11, 0, 0, 0], "swing", DEMO_MIN_N).state, "zero");
  const ok = baselineCell([27, 15, 6, 1], "swing", DEMO_MIN_N);
  assert.equal(ok.state, "ok");
  if (ok.state === "ok") { assert.equal(ok.k, 15); assert.equal(ok.n, 27); }
});

test("A 打者上場：帶入打者 A、壘上無人、0-0；本場資訊只含他自己先前打席並標明來源", () => {
  const { situation, cutoff } = situationAt(DEMO_EVENTS, REPLAY_START);
  assert.equal(situation.batter, "打者 A");
  assert.deepEqual(situation.bases, { first: false, second: false, third: false });
  assert.equal(`${situation.balls}-${situation.strikes}`, "0-0");
  assert.equal(cutoff.kind, "pa_start");
  const d = dyn("pa-6a");
  assert.equal(d.batter, "打者 A");
  assert.deepEqual(d.observations.map((o) => o.seq), [1, 3, 42]); // 1 局兩球、4 局一球，都是打者 A 自己的
  assert.deepEqual(d.priorInnings, [1, 4]);
  assert.equal(d.currentPaOpp, 0);
  assert.equal(d.last.kind, "none");
});

test("C 符合條件的新一球：更新觀察，增減對應該事件與其所屬球數的長期比例", () => {
  const before = dyn("pa-6a");
  const after = dyn("ev-61");
  assert.equal(after.opp, before.opp + 1);
  assert.equal(after.observed, before.observed + 1);
  near(after.value - before.value, 1 - rate("打者 A", "0-0"));
  assert.equal(after.last.kind, "included");
  if (after.last.kind === "included") {
    assert.equal(after.last.observation.eventId, "ev-61");
    near(after.last.observation.delta ?? NaN, 1 - rate("打者 A", "0-0"));
  }
});

test("D 不符合條件的新一球：累積不變，並說明未納入原因", () => {
  const a = dyn("ev-61");
  const b = dyn("ev-62"); // 滑球・外角低
  assert.equal(b.opp, a.opp);
  near(b.value, a.value);
  assert.equal(b.last.kind, "excluded");
  if (b.last.kind === "excluded") assert.equal(b.last.text, "本球未納入：球種不符（滑球）、區域不符（外角低）");
  const c = dyn("ev-63"); // 速球・內角高
  near(c.value, a.value);
  if (c.last.kind === "excluded") assert.equal(c.last.text, "本球未納入：區域不符（內角高）");
  // inclusionOf 單獨驗：符合條件
  const e61 = DEMO_EVENTS[idxOf("ev-61")] as PitchEvent;
  assert.deepEqual(inclusionOf(e61, DEMO_EVENTS[idxOf("ev-61") - 1].after, OH), { included: true });
});

test("E 2-2 變 3-2：上一球留在 2-2，目前參考改用 3-2 且兩者基準不同", () => {
  const i = idxOf("ev-65");
  const ctx = lastPitchContext(DEMO_EVENTS, i);
  assert.ok(ctx);
  assert.equal(`${ctx.pre.balls}-${ctx.pre.strikes}`, "2-2");
  assert.equal(`${ctx.cur.balls}-${ctx.cur.strikes}`, "3-2");
  assert.equal(ctx.sameBatter, true);
  const d = dyn("ev-65");
  const lastObs = d.observations[d.observations.length - 1];
  assert.equal(lastObs.eventId, "ev-65");
  assert.equal(lastObs.count, "2-2"); // 觀察記在投出前的情境
  // 增減用 2-2 的長期比例，不是 3-2 的
  near(d.value - dyn("ev-64").value, -rate("打者 A", "2-2"));
  assert.notEqual(rate("打者 A", "2-2"), rate("打者 A", "3-2"));
});

test("G 回落：未出棒的新證據讓本場變化下降，不是只增不減", () => {
  const up = dyn("ev-64");
  const down = dyn("ev-65");
  assert.ok(up.value > dyn("ev-61").value);
  assert.ok(down.value < up.value);
  if (down.last.kind === "included") assert.ok((down.last.observation.delta ?? 0) < 0);
});

test("F 換打者：打者 C 用自己的觀察，不帶走打者 A 的累積；保留剛結束打席摘要", () => {
  const c = dyn("ev-66");
  assert.equal(c.batter, "打者 C");
  assert.deepEqual(c.observations.map((o) => o.seq), [5, 44]); // 只有打者 C 自己先前的兩球
  near(c.value, -2 * rate("打者 C", "0-0"));
  assert.equal(c.last.kind, "other_batter"); // 上一球屬於打者 A 的打席
  // 打者 A 的累積沒有消失，也沒有因為換人而改變（第 66 球不是外角高速球）
  near(dyn("ev-66", OH, "打者 A").value, dyn("ev-65").value);
  // 隊友共同反應是獨立欄位：不含打者 C 自己
  assert.equal(c.teammates.opp, 8); // 打者 A 六球＋打者 D 兩球
  assert.equal(dyn("ev-61").teammates.opp, 4); // 對打者 A 而言：打者 C 兩球＋打者 D 兩球
  const s = completedPaSummary(DEMO_EVENTS, idxOf("ev-66"), OH, DEMO_BASELINES, DEMO_MIN_N);
  assert.ok(s);
  assert.equal(s.batter, "打者 A");
  assert.equal(s.pitches, 6);
  assert.equal(s.resultText, "三壘滾地出局");
  assert.equal(s.includedCount, 3);
  assert.equal(s.reactedCount, 2);
  near(s.valueAfter, dyn("ev-65").value);
  assert.equal(completedPaSummary(DEMO_EVENTS, REPLAY_START, OH, DEMO_BASELINES, DEMO_MIN_N), null);
  // 打者 C 之後自己的符合條件來球會更新他自己的數字
  near(dyn("ev-67").value - c.value, -rate("打者 C", "0-0"));
  near(dyn("ev-69").value - dyn("ev-67").value, 1 - rate("打者 C", "1-1"));
});

test("B 切換戰術與上一事件回放：不重置、不重複計入", () => {
  const a1 = dyn("ev-64");
  const b = dyn("ev-64", OL);
  const a2 = dyn("ev-64");
  assert.deepEqual(a2, a1);
  assert.deepEqual(b.observations.map((o) => o.seq), [2, 41, 62]); // 另一個戰術有自己的觀察
  // 下一事件再上一事件
  dyn("ev-65");
  assert.deepEqual(dyn("ev-64"), a1);
  // 每一筆觀察對應一個事件，沒有重複
  const all = dyn("ev-69", OH, "打者 A").observations.map((o) => o.eventId);
  assert.equal(new Set(all).size, all.length);
  assert.deepEqual(all, ["ev-1", "ev-3", "ev-42", "ev-61", "ev-64", "ev-65"]);
});

test("本打席逐球：只含目前打者這個打席，並帶納入與否", () => {
  const list = currentPaPitches(DEMO_EVENTS, idxOf("ev-65"), OH);
  assert.deepEqual(list.map((p) => p.event.seq), [61, 62, 63, 64, 65]);
  assert.deepEqual(list.map((p) => p.inclusion.included), [true, false, false, true, true]);
  assert.equal(currentPaPitches(DEMO_EVENTS, idxOf("ev-66"), OH).length, 0); // 打者 C 尚未面對投球
  assert.deepEqual(currentPaPitches(DEMO_EVENTS, idxOf("ev-68"), OH).map((p) => p.event.seq), [67, 68]);
});

test("我方投手量測：只算球速與位置，依戰術球種統計本場來球", () => {
  const m = pitcherMeasure(DEMO_EVENTS, idxOf("ev-61"), OH);
  // 速球：1 3 5 7 42 43 44 46 48 61
  assert.equal(m.count, 10);
  assert.equal(m.inTargetZone, 8); // 43（中間）、46（內角中）不在外角高
  assert.equal(m.lastSpeed, 147);
  assert.ok(m.avgSpeed != null && m.avgSpeed > 140 && m.avgSpeed < 150);
});
