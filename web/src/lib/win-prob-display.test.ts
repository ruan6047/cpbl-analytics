import assert from "node:assert/strict";
import { test } from "node:test";
import {
  WP_DISPLAY_MAX, WP_DISPLAY_MIN,
  displayWp, displayWpPct, displayWpPctInt, isTerminalWpPoint,
} from "./win-prob-display.ts";

test("非終點的勝率顯示夾到 [1%, 99%]，不出現 100%／0%", () => {
  assert.equal(displayWpPctInt(0.9997), 99);
  assert.equal(displayWpPctInt(1), 99);
  assert.equal(displayWpPctInt(0.0003), 1);
  assert.equal(displayWpPctInt(0), 1);
  assert.equal(displayWpPct(0.99999), 99);
  assert.equal(displayWpPct(0.00001), 1);
});

test("終場點豁免夾層（勝負已定，可顯示 100%／0%）", () => {
  assert.equal(displayWpPctInt(1, true), 100);
  assert.equal(displayWpPctInt(0, true), 0);
  assert.equal(displayWpPct(1, true), 100);
  assert.equal(displayWpPct(0.5, true), 50);
});

test("夾層不動中段值（只切極端，不整體壓縮）", () => {
  for (const wp of [0.01, 0.12, 0.5, 0.734, 0.99]) {
    assert.equal(displayWp(wp), wp);
  }
  assert.equal(displayWpPct(0.7345), 73.5);
});

test("界線值本身不被再夾", () => {
  assert.equal(displayWp(WP_DISPLAY_MIN), WP_DISPLAY_MIN);
  assert.equal(displayWp(WP_DISPLAY_MAX), WP_DISPLAY_MAX);
});

test("非有限值原樣回傳，不靜默補 0.5", () => {
  assert.ok(Number.isNaN(displayWp(Number.NaN)));
  assert.ok(Number.isNaN(displayWpPct(Number.NaN)));
});

test("終場點＝序列末端沒有打席身分的收斂點（evt 與 inning 皆 null）", () => {
  assert.equal(isTerminalWpPoint({ evt: null, inning: null }), true);
  assert.equal(isTerminalWpPoint({ evt: "0110001000", inning: 1 }), false);
  assert.equal(isTerminalWpPoint({ evt: null, inning: 9 }), false);
  assert.equal(isTerminalWpPoint({}), true);   // 兩欄皆缺＝視同收斂點
});

test("夾層只是顯示層：原值不被改寫（呼叫端拿到的是新數字，來源不動）", () => {
  const point = { evt: null, inning: null, wp: 1 };
  const shown = displayWpPct(point.wp, isTerminalWpPoint(point));
  assert.equal(shown, 100);
  assert.equal(point.wp, 1);          // 來源物件未被改動
  const midGame = { evt: "0910011000", inning: 9, wp: 0.9998 };
  assert.equal(displayWpPct(midGame.wp, isTerminalWpPoint(midGame)), 99);
  assert.equal(midGame.wp, 0.9998);   // 儲存值／可重現雜湊用的仍是原值
});
