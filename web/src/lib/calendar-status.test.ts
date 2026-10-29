import assert from "node:assert/strict";
import test from "node:test";

import { calendarNotNeeded } from "./calendar-status.ts";

// #391 審核 F1：二軍沒有公告旅程（slotStatus 恆為 undefined），只能讀 calendar 端點的 `not_needed`
// （後端 `cpbl.season_close.farm.not_needed_keys`）。
// 樣本：2026 F1–F3 為真實已完賽列；**F4 是構造的**未舉行列（2026 實際沒有 F4）。

test("二軍已收官：構造的未舉行 F4 判為不需進行", () => {
  assert.equal(calendarNotNeeded({ not_needed: true }, undefined, false), true);
});

test("真實已完賽 F1–F3 與未收官的未完賽列都不是不需進行", () => {
  assert.equal(calendarNotNeeded({ not_needed: false }, undefined, true), false);
  assert.equal(calendarNotNeeded({ not_needed: true }, undefined, true), false, "已完賽優先");
  assert.equal(calendarNotNeeded({}, undefined, false), false, "舊 API 沒有欄位＝不標");
});

test("一軍公告旅程的 not_needed 照舊生效", () => {
  assert.equal(calendarNotNeeded({}, "not_needed", false), true);
  assert.equal(calendarNotNeeded({}, "result_pending", false), false);
});
