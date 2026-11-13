import assert from "node:assert/strict";
import test from "node:test";

import {
  baselineCell, completedPaSummary, countTag, currentPaPitches, dynamicAt, indicatorAt, inclusionOf,
  lastPitchContext, situationAt, statusOf,
} from "./accumulate.ts";
import { DEMO_EVENTS, DEMO_MIN_N, DEMO_REFERENCE, REPLAY_START } from "./demo-data.ts";
import type { PitchEvent } from "./model.ts";
import { DEMO_RULES, TACTICS } from "./tactics.config.ts";

const OH = TACTICS.find((t) => t.id === "outside-high-fastball")!;
const OL = TACTICS.find((t) => t.id === "outside-low-slider")!;
const LAST = DEMO_EVENTS.length - 1;
const idxOf = (id: string) => DEMO_EVENTS.findIndex((e) => e.id === id);
const ind = (id: string, t = OH) => indicatorAt(DEMO_EVENTS, idxOf(id), t, DEMO_REFERENCE);

test("countTag：五類互斥，0-0 只標首球", () => {
  assert.equal(countTag(0, 0), "首球");
  assert.equal(countTag(0, 1), "球數領先");
  assert.equal(countTag(1, 0), "球數落後");
  assert.equal(countTag(2, 2), "平球數");
  assert.equal(countTag(3, 2), "滿球數");
});

test("baselineCell：缺值／樣本不足／觀察到 0 次／一般，分母是符合條件來球數", () => {
  assert.deepEqual(baselineCell(null, "swing", DEMO_MIN_N), { state: "missing" });
  assert.equal(baselineCell([5, 3, 1, 1, 0, 0, 0], "swing", DEMO_MIN_N).state, "insufficient");
  assert.equal(baselineCell([20, 12, 3, 3, 2, 0, 0], "hard", DEMO_MIN_N).state, "zero");
  const weak = baselineCell([20, 12, 3, 3, 2, 0, 0], "weak", DEMO_MIN_N);
  assert.deepEqual(weak, { state: "ok", k: 2, n: 20, rate: 0.1 });
  const swing = baselineCell([20, 12, 3, 3, 2, 0, 0], "swing", DEMO_MIN_N);
  if (swing.state === "ok") assert.equal(swing.k, 8); // 出棒＝來球數減未出棒
});

test("statusOf：距離尚遠／接近區內／已超過", () => {
  assert.equal(statusOf(62, 80, DEMO_RULES.nearBand).status, "far");
  assert.equal(statusOf(74, 80, DEMO_RULES.nearBand).status, "near");
  assert.deepEqual(statusOf(82, 80, DEMO_RULES.nearBand), { status: "over", distance: -2 });
});

test("劇本：打者 A 上場距離尚遠，之後依序接近、超過、回落，2-2 變 3-2 時參考線改變", () => {
  const start = indicatorAt(DEMO_EVENTS, REPLAY_START, OH, DEMO_REFERENCE);
  assert.equal(situationAt(DEMO_EVENTS, REPLAY_START).situation.batter, "打者 A");
  assert.deepEqual([start.value, start.reference, start.status], [62, 80, "far"]);
  assert.deepEqual(start.dyn.priorInnings, [1, 4]); // 只含打者 A 自己先前打席
  assert.deepEqual([ind("ev-61").value, ind("ev-61").status, ind("ev-61").delta], [74, "near", 12]);
  assert.deepEqual([ind("ev-62").value, ind("ev-62").status], [82, "over"]);
  assert.deepEqual([ind("ev-63").value, ind("ev-63").status, ind("ev-63").delta], [70, "near", -12]); // 回落
  const e = ind("ev-65");
  assert.deepEqual(e.refChange, { kind: "count", from: "2-2", to: "3-2", fromRef: 78 });
  assert.equal(e.reference, 74);
  const ctx = lastPitchContext(DEMO_EVENTS, idxOf("ev-65"));
  assert.equal(`${ctx?.pre.balls}-${ctx?.pre.strikes}`, "2-2");
  assert.equal(e.dyn.observations[e.dyn.observations.length - 1].count, "2-2"); // 觀察記在投出前的球數
});

test("不符合條件的球不更新，並說明未納入原因", () => {
  const before = ind("ev-63");
  const after = ind("ev-64"); // 速球・內角高
  assert.equal(after.value, before.value);
  assert.equal(after.delta, null);
  assert.equal(after.dyn.last.kind, "excluded");
  if (after.dyn.last.kind === "excluded") assert.equal(after.dyn.last.text, "本球未納入：區域不符（內角高）");
  const e61 = DEMO_EVENTS[idxOf("ev-61")] as PitchEvent;
  assert.deepEqual(inclusionOf(e61, DEMO_EVENTS[idxOf("ev-61") - 1].after, OH), { included: true });
  assert.equal(inclusionOf(e61, DEMO_EVENTS[idxOf("ev-61") - 1].after, OL).included, false);
});

test("換打者：打者 C 用自己的累積，不帶走打者 A 的；保留剛結束打席摘要", () => {
  const c = ind("ev-66");
  assert.equal(c.dyn.batter, "打者 C");
  assert.deepEqual([c.value, c.reference, c.status], [24, 88, "far"]);
  assert.deepEqual(c.dyn.observations.map((o) => o.seq), [6, 45]);
  assert.equal(c.dyn.last.kind, "other_batter");
  assert.deepEqual(c.refChange, { kind: "batter", from: "打者 A", to: "打者 C" });
  assert.equal(dynamicAt(DEMO_EVENTS, idxOf("ev-66"), OH, "打者 A").value, 82); // 打者 A 的累積仍在
  assert.deepEqual(c.dyn.teammates.batters, ["打者 A", "打者 D"]); // 隊友另計，不含打者 C
  const s = completedPaSummary(DEMO_EVENTS, idxOf("ev-66"), OH);
  assert.deepEqual([s?.batter, s?.pitches, s?.includedCount, s?.valueBefore, s?.valueAfter], ["打者 A", 6, 4, 62, 82]);
  assert.equal(completedPaSummary(DEMO_EVENTS, REPLAY_START, OH), null);
  assert.deepEqual([ind("ev-67").value, ind("ev-69").value], [36, 24]); // 打者 C 自己上升後回落
});

test("切換戰術與上一事件回放：不重置、不重複計入", () => {
  const a1 = ind("ev-63");
  const b = ind("ev-63", OL);
  assert.deepEqual(ind("ev-63"), a1); // 切到別的戰術再切回
  assert.notEqual(b.value, a1.value); // 各戰術有自己的累積與參考線
  assert.notEqual(b.reference, a1.reference);
  ind("ev-64");
  assert.deepEqual(ind("ev-63"), a1); // 下一事件再上一事件
  // 每一筆觀察對應一個事件，沒有重複；每次增減相加等於最後的動態值
  const all = dynamicAt(DEMO_EVENTS, LAST, OH, "打者 A").observations;
  assert.equal(new Set(all.map((o) => o.eventId)).size, all.length);
  assert.equal(all.reduce((sum, o) => sum + o.delta, 0), 82);
  // 反應種類的計數：互斥六類相加等於符合條件來球數
  const t = dynamicAt(DEMO_EVENTS, LAST, OH, "打者 A").tally;
  assert.equal(t.take + t.whiff + t.foul + t.weak + t.solid + t.hard, t.opp);
  assert.equal(t.swing, t.opp - t.take);
});

test("本打席逐球：只含目前打者這個打席", () => {
  assert.deepEqual(currentPaPitches(DEMO_EVENTS, idxOf("ev-65"), OH).map((p) => p.event.seq), [61, 62, 63, 64, 65]);
  assert.equal(currentPaPitches(DEMO_EVENTS, idxOf("ev-66"), OH).length, 0);
});
