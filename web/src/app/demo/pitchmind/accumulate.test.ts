import assert from "node:assert/strict";
import test from "node:test";

import {
  accumulateAt, baselineCell, countTag, currentPaPitches, situationAt,
} from "./accumulate.ts";
import { DEMO_BASELINES, DEMO_EVENTS, DEMO_MIN_N, REPLAY_START } from "./demo-data.ts";
import { TACTICS } from "./tactics.config.ts";

const OH = TACTICS.find((t) => t.id === "outside-high")!;
const IL = TACTICS.find((t) => t.id === "inside-low")!;
const last = DEMO_EVENTS.length - 1;
const idxOfCount = (b: number, s: number) =>
  DEMO_EVENTS.findIndex((_, i) => i >= REPLAY_START && situationAt(DEMO_EVENTS, i).situation.balls === b
    && situationAt(DEMO_EVENTS, i).situation.strikes === s);

test("countTag：首球／領先／落後／滿球數／平球數，五類互斥", () => {
  assert.equal(countTag(0, 0), "首球");
  assert.equal(countTag(0, 1), "球數領先");
  assert.equal(countTag(1, 0), "球數落後");
  assert.equal(countTag(3, 1), "球數落後");
  assert.equal(countTag(3, 2), "滿球數");
  // 0-0 只標首球，不同時標平球數
  assert.equal(countTag(1, 1), "平球數");
  assert.equal(countTag(2, 2), "平球數");
});

test("載入情境：打者 A、壘上無人、0-0", () => {
  const { situation, cutoff } = situationAt(DEMO_EVENTS, REPLAY_START);
  assert.equal(situation.batter, "打者 A");
  assert.deepEqual(situation.bases, { first: false, second: false, third: false });
  assert.equal(situation.balls, 0);
  assert.equal(situation.strikes, 0);
  assert.equal(cutoff.kind, "pa_start");
});

test("事件序列含 2-2 → 3-2，且資料截至事件隨推進", () => {
  const i22 = idxOfCount(2, 2);
  const i32 = idxOfCount(3, 2);
  assert.ok(i22 > REPLAY_START);
  assert.equal(i32, i22 + 1);
  assert.notEqual(situationAt(DEMO_EVENTS, i22).cutoff.id, situationAt(DEMO_EVENTS, i32).cutoff.id);
});

test("baselineCell 區分缺值／樣本不足／觀察到 0 次／一般", () => {
  assert.deepEqual(baselineCell(null, "swing", DEMO_MIN_N), { state: "missing" });
  assert.equal(baselineCell([5, 3, 0, 2], "swing", DEMO_MIN_N).state, "insufficient");
  assert.equal(baselineCell([11, 0, 0, 0], "swing", DEMO_MIN_N).state, "zero");
  // 分母為出棒數、出棒 0 次 → 分母不足，不是 0%
  assert.equal(baselineCell([11, 0, 0, 0], "whiff", DEMO_MIN_N).state, "insufficient");
  const ok = baselineCell([27, 15, 6, 1], "swing", DEMO_MIN_N);
  assert.equal(ok.state, "ok");
  if (ok.state === "ok") { assert.equal(ok.k, 15); assert.equal(ok.n, 27); }
});

test("3-2 打者長期基準樣本不足，不沿用 2-2 數值", () => {
  const at22 = baselineCell(DEMO_BASELINES[OH.id].long["2-2"] ?? null, "swing", DEMO_MIN_N);
  const at32 = baselineCell(DEMO_BASELINES[OH.id].long["3-2"] ?? null, "swing", DEMO_MIN_N);
  assert.equal(at22.state, "ok");
  assert.equal(at32.state, "insufficient");
  assert.ok(!("rate" in at32));
});

test("累積由事件序列＋索引推導：重算、切換戰術、上一球下一球皆不重複也不清除", () => {
  const i = REPLAY_START + 2;
  const a1 = accumulateAt(DEMO_EVENTS, i, OH, DEMO_BASELINES, DEMO_MIN_N);
  // 切到另一戰術再切回
  accumulateAt(DEMO_EVENTS, i, IL, DEMO_BASELINES, DEMO_MIN_N);
  const a2 = accumulateAt(DEMO_EVENTS, i, OH, DEMO_BASELINES, DEMO_MIN_N);
  assert.deepEqual(a2, a1);
  // 下一球再上一球
  accumulateAt(DEMO_EVENTS, i + 1, OH, DEMO_BASELINES, DEMO_MIN_N);
  const a3 = accumulateAt(DEMO_EVENTS, i, OH, DEMO_BASELINES, DEMO_MIN_N);
  assert.deepEqual(a3, a1);
  // 載入時已含前幾局的累積（不因展演起點而清除）
  assert.ok(accumulateAt(DEMO_EVENTS, REPLAY_START, OH, DEMO_BASELINES, DEMO_MIN_N).batter.opp > 0);
});

test("累積機會數隨索引單調不減，終點等於逐筆手算", () => {
  for (const t of [OH, IL]) {
    let prev = -1;
    for (let i = REPLAY_START; i <= last; i++) {
      const a = accumulateAt(DEMO_EVENTS, i, t, DEMO_BASELINES, DEMO_MIN_N, "打者 A");
      assert.ok(a.batter.opp >= prev);
      prev = a.batter.opp;
    }
  }
  const end = accumulateAt(DEMO_EVENTS, last, OH, DEMO_BASELINES, DEMO_MIN_N, "打者 A");
  // 外角高・速球・壘上無人，打者 A：h1 h3 a2 p1 p3 p5 共 6 球；出棒 h1 h3 p3 共 3 次；揮空 h3 1 次
  assert.equal(end.batter.opp, 6);
  assert.equal(end.batter.reactions.swing.k, 3);
  assert.equal(end.batter.reactions.whiff.k, 1);
  assert.equal(end.batter.reactions.whiff.den, 3);
  // 隊友：c1 d1 d2
  assert.equal(end.teammates.opp, 3);
  // 打席結束後局面換到打者 C；預設關注目前打者：打者 C 本場只有 1 局的 c1 一球符合
  assert.equal(situationAt(DEMO_EVENTS, last).situation.batter, "打者 C");
  assert.equal(accumulateAt(DEMO_EVENTS, last, OH, DEMO_BASELINES, DEMO_MIN_N).batter.opp, 1);
});

test("相對預期：基準樣本不足的機會不納入預期並如實計數", () => {
  const end = accumulateAt(DEMO_EVENTS, last, IL, DEMO_BASELINES, DEMO_MIN_N, "打者 A");
  // 內角低打者 A：h2(0-1) a1(0-0) p2(1-0) p6(3-2)；3-2 長期基準不足
  assert.equal(end.batter.opp, 4);
  assert.equal(end.expected.swing.used, 3);
  assert.equal(end.expected.swing.skipped, 1);
});

test("我方投手本打席來球：只含目前打席，並標示是否符合戰術條件", () => {
  const i = idxOfCount(3, 2);
  const list = currentPaPitches(DEMO_EVENTS, i, OH);
  assert.equal(list.length, 5);
  assert.deepEqual(list.map((p) => p.matched), [true, false, true, false, true]);
  assert.equal(list[0].speedDiff, null);
});
