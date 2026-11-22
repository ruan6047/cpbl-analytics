import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { calendarPostseasonIndex, calendarPostseasonLabel } from "./calendar-postseason.ts";
import { calendarNotNeeded } from "./calendar-status.ts";
import { postseasonJourneyFromContext } from "./postseason-journey.ts";
import type { PostseasonSeriesContextV2 } from "./postseason-series-contract.ts";

// #459：月曆格（桌機）與日期清單（手機）共用 calendarPostseasonIndex＋calendarPostseasonLabel。
// 讀 Python 產生的同一份 golden（tests/test_postseason_context_golden.py），前端不重算場序。
function golden(name: string): PostseasonSeriesContextV2 {
  return JSON.parse(readFileSync(new URL(`./__golden__/series-context/${name}.json`, import.meta.url), "utf8"));
}

function indexOf(name: string) {
  const j = postseasonJourneyFromContext(golden(name), null);
  assert.ok(j);
  return calendarPostseasonIndex(j.slots);
}

test("2026 台灣大賽延賽補賽實況：已完賽補賽列標實際場次，不標同日原排場次", () => {
  const { slotByRow, announcedByDate } = indexOf("2026-c-makeup-real");
  const row = (sno: number) => slotByRow.get(`C-${sno}`);
  // 官方 G5 補在公告 G7 原定日：仍是 G5、完賽；G6 完賽；G7 系列已分勝負未舉行 ⇒ 依條件不需進行
  assert.equal(row(5)?.date, "2026-10-25");
  assert.equal(calendarPostseasonLabel("C", row(5)), "台灣大賽 G5");
  assert.equal(row(5)?.status, "final");
  assert.equal(calendarPostseasonLabel("C", row(6)), "台灣大賽 G6");
  assert.equal(row(6)?.status, "final");
  assert.equal(calendarPostseasonLabel("C", row(7)), "台灣大賽 G7");
  assert.equal(calendarNotNeeded({ not_needed: false }, row(7)?.status, false), true);
  for (let n = 1; n <= 7; n++) assert.equal(row(n)?.seq, n);
  // 已在別天打完的公告格不另畫「依條件不需進行」卡
  for (const d of ["2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"]) {
    assert.deepEqual(announcedByDate.get(d) ?? [], [], d);
  }
});

test("賽程未異動：公告格與官方場次同日同序（既有 golden 標籤不變）", () => {
  const { slotByRow } = indexOf("2026-c-swept-injected");
  for (const [key, s] of slotByRow) {
    assert.equal(calendarPostseasonLabel(s.kind, s), `${s.kind === "C" ? "台灣大賽" : "季後挑戰賽"} G${Number(key.split("-")[1])}`);
  }
});

test("非季後賽列無標籤；季後賽列沒有對到格時只標層級", () => {
  assert.equal(calendarPostseasonLabel("A", undefined), null);
  assert.equal(calendarPostseasonLabel("D", undefined), null);
  assert.equal(calendarPostseasonLabel("F", undefined), "二軍季後");
  assert.equal(calendarPostseasonLabel("C", undefined), "台灣大賽");
});
