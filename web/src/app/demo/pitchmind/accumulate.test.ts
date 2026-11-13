import assert from "node:assert/strict";
import test from "node:test";

import {
  countTag, dynamicAt, dynamicSeries, quickRead, referenceFor, situationAt, statusOf,
} from "./accumulate.ts";
import { DEMO_EVENTS, REPLAY_START, SCRIPTED_ADVERSE_EVENT_ID } from "./demo-data.ts";
import { DEMO_RULES, TACTICS } from "./tactics.config.ts";

const OH = TACTICS.find((t) => t.id === "outside-high-fastball")!;
const OL = TACTICS.find((t) => t.id === "outside-low-slider")!;
const LAST = DEMO_EVENTS.length - 1;
const idxOf = (id: string) => DEMO_EVENTS.findIndex((e) => e.id === id);

test("countTag：五類互斥，0-0 只標首球", () => {
  assert.equal(countTag(0, 0), "首球");
  assert.equal(countTag(0, 1), "球數領先");
  assert.equal(countTag(1, 0), "球數落後");
  assert.equal(countTag(1, 1), "平球數");
  assert.equal(countTag(2, 2), "平球數");
  assert.equal(countTag(3, 2), "滿球數");
});

test("statusOf：三段狀態與界線邊界", () => {
  assert.deepEqual(statusOf(30, 80, DEMO_RULES.nearBand), { status: "far", distance: 50 });
  assert.deepEqual(statusOf(65, 80, DEMO_RULES.nearBand), { status: "near", distance: 15 });
  assert.equal(statusOf(64, 80, DEMO_RULES.nearBand).status, "far");
  assert.deepEqual(statusOf(80, 80, DEMO_RULES.nearBand), { status: "over", distance: 0 });
  assert.deepEqual(statusOf(84, 80, DEMO_RULES.nearBand), { status: "over", distance: -4 });
});

test("referenceFor：兩好球時改用兩好球界線", () => {
  const s = situationAt(DEMO_EVENTS, REPLAY_START).situation;
  assert.equal(referenceFor(OH, s), 80);
  assert.equal(referenceFor(OH, { ...s, balls: 3, strikes: 2 }), 75);
  assert.equal(referenceFor(OH, { ...s, balls: 1, strikes: 2 }), 75);
});

test("動態值由事件序列推導：載入時 30，劇本序列含接近、超過與回落", () => {
  const vals: number[] = [];
  for (let i = REPLAY_START; i <= LAST; i++) vals.push(dynamicAt(DEMO_EVENTS, i, OH).value);
  assert.equal(vals[0], 30);
  const changes = vals.filter((v, i) => i === 0 || v !== vals[i - 1]);
  assert.deepEqual(changes, [30, 42, 50, 62, 70, 82, 94, 82, 70, 60]);
  const states: string[] = [];
  for (let i = REPLAY_START; i <= LAST; i++) states.push(quickRead(DEMO_EVENTS, i, OH).status);
  assert.ok(states.includes("far") && states.includes("near") && states.includes("over"));
  assert.equal(states[states.length - 1], "far");
});

test("方向：回落時標示下降，上升時標示上升", () => {
  const up = dynamicAt(DEMO_EVENTS, idxOf("ev-68"), OH);
  assert.equal(up.direction, "up");
  assert.equal(up.delta, 12);
  const down = dynamicAt(DEMO_EVENTS, idxOf("ev-71"), OH);
  assert.equal(down.direction, "down");
  assert.equal(down.delta, -12);
  // 不符合此戰術的事件不改變值，方向沿用最近一次更新
  assert.equal(dynamicAt(DEMO_EVENTS, idxOf("ev-62"), OH).value, 42);
});

test("提示（接近或超過）排在事先安排的明顯不利結果之前", () => {
  const adverse = idxOf(SCRIPTED_ADVERSE_EVENT_ID);
  let firstAlert = -1;
  for (let i = REPLAY_START; i <= LAST; i++) {
    if (quickRead(DEMO_EVENTS, i, OH).status !== "far") { firstAlert = i; break; }
  }
  assert.ok(firstAlert > REPLAY_START && firstAlert < adverse);
  // 超過也先於不利結果出現
  assert.equal(quickRead(DEMO_EVENTS, adverse - 1, OH).status, "over");
});

test("切換戰術不重置、不重複計入：結果只由（事件、索引、戰術）決定", () => {
  const i = idxOf("ev-66");
  const a1 = quickRead(DEMO_EVENTS, i, OH);
  const b = quickRead(DEMO_EVENTS, i, OL);
  const a2 = quickRead(DEMO_EVENTS, i, OH);
  assert.deepEqual(a2, a1);
  assert.notEqual(b.reference, a1.reference); // 各戰術有自己的參考值
  assert.equal(b.value, 20);
  // 上一事件再下一事件
  quickRead(DEMO_EVENTS, i + 1, OH);
  assert.deepEqual(quickRead(DEMO_EVENTS, i, OH), a1);
  // 每一次更新都對應一個符合條件的事件，沒有重複
  const series = dynamicSeries(DEMO_EVENTS, LAST, OH);
  assert.equal(new Set(series.map((p) => p.eventIdx)).size, series.length);
});

test("球數改變時累積延續（不重置）", () => {
  const before = dynamicAt(DEMO_EVENTS, idxOf("ev-64"), OH); // 2-2
  const after = dynamicAt(DEMO_EVENTS, idxOf("ev-65"), OH); // 3-2
  assert.equal(before.value, 50);
  assert.equal(after.value, 62);
  assert.equal(situationAt(DEMO_EVENTS, idxOf("ev-64")).situation.strikes, 2);
});
