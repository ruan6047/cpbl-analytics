import assert from "node:assert/strict";
import test from "node:test";

import { indexWpCurve, joinPaSwing } from "./pa-wp-join.ts";

const pt = (evt: string | null, wp: number, inning: number | null = 1) => ({ evt, inning, wp });

// 一場 4 個打席 + 終場收斂點（主隊勝）
const CURVE = [pt("10", 0.5), pt("20", 0.55), pt("30", 0.48), pt("40", 0.7), pt(null, 1, null)];

test("indexWpCurve 依事件號排序並分離終場收斂點", () => {
  const idx = indexWpCurve([pt("30", 0.48), pt(null, 1, null), pt("10", 0.5)]);
  assert.deepEqual(idx.points.map((p) => p.evt), [10, 30]);
  assert.equal(idx.terminal, 1);
});

test("indexWpCurve 丟掉非有限值與缺事件號的點（不猜）", () => {
  const idx = indexWpCurve([pt("10", Number.NaN), pt(null, 0.6, 3), pt("20", 0.55)]);
  assert.deepEqual(idx.points.map((p) => p.evt), [20]);
  assert.equal(idx.terminal, null);   // inning 非 null → 不是終場收斂點
});

test("joinPaSwing：before＝區間內首點、after＝區間後首點", () => {
  const idx = indexWpCurve(CURVE);
  const s = joinPaSwing(idx, 20, 20);
  assert.deepEqual(s, { before: 0.55, after: 0.48, terminal: false,
    delta: 0.55 - 0.55 + (0.48 - 0.55) });
  assert.equal(s?.terminal, false);
});

test("joinPaSwing：canonical 打席併掉兩個近似點時，涵蓋整個打席", () => {
  // 打席事件號 20–30（打席中途代打，曲線在 20 與 30 各有一點）
  const s = joinPaSwing(indexWpCurve(CURVE), 20, 30);
  assert.equal(s?.before, 0.55);   // 取區間內**第一**點
  assert.equal(s?.after, 0.7);     // 取區間**之後**第一點，而非區間內的 30
});

test("joinPaSwing：最後一個打席收斂到終場結果並標 terminal", () => {
  const s = joinPaSwing(indexWpCurve(CURVE), 40, 40);
  assert.deepEqual(s, { before: 0.7, after: 1, terminal: true, delta: 1 - 0.7 });
});

test("joinPaSwing：曲線對不到（區間內無點且區間前無點）回 null，不猜", () => {
  assert.equal(joinPaSwing(indexWpCurve(CURVE), 1, 5), null);
});

test("joinPaSwing：比賽未完賽時最後一個打席沒有 after → null", () => {
  const live = indexWpCurve([pt("10", 0.5), pt("20", 0.55)]);
  assert.equal(joinPaSwing(live, 20, 20), null);
  assert.equal(joinPaSwing(live, 10, 10)?.after, 0.55);
});

test("joinPaSwing：事件號非數字回 null", () => {
  const idx = indexWpCurve(CURVE);
  assert.equal(joinPaSwing(idx, null, null), null);
  assert.equal(joinPaSwing(idx, "x", "y"), null);
});

test("joinPaSwing：區間內無點時退回區間前最後一點（換人列自成一段的情形）", () => {
  const s = joinPaSwing(indexWpCurve(CURVE), 25, 26);
  assert.equal(s?.before, 0.55);   // 區間前最後一點（evt 20）
  assert.equal(s?.after, 0.48);    // 區間後第一點（evt 30）
});
