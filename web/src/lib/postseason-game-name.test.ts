import assert from "node:assert/strict";
import { test } from "node:test";
import { POSTSEASON_2026 } from "./postseason-announcement.ts";
import { announcedSlotOf, reportEntry, taipeiMinute } from "./postseason-game-name.ts";

test("時戳只給讀者需要的精度", () => {
  assert.equal(taipeiMinute("2026-10-14T04:49:44.916317+00:00"), "2026-10-14 12:49（台北）");
  assert.equal(taipeiMinute(null), null);
  assert.equal(taipeiMinute("不是時間"), "不是時間");
});

test("單場頁公告安排：E 以官方場號＋日期、C 只認同日唯一公告，不以場號猜場序", () => {
  assert.equal(announcedSlotOf(POSTSEASON_2026, "C", 1, "2026-10-17")?.key, "C1");
  assert.equal(announcedSlotOf(POSTSEASON_2026, "C", 9, "2026-10-23")?.conditional, true);
  assert.equal(announcedSlotOf(POSTSEASON_2026, "C", 5, "2026-10-19"), null, "補賽日沒有公告場，不以場號 5 猜 G5");
  assert.equal(announcedSlotOf(POSTSEASON_2026, "E", 4, "2026-10-12")?.start, "18:35");
  assert.equal(announcedSlotOf(POSTSEASON_2026, "E", 3, "2026-10-12"), null);
  assert.equal(announcedSlotOf(null, "C", 1, "2026-10-17"), null);
});

test("N38：完賽季後單場頁在下一場目標解析前不給連結，解析後一次定案", () => {
  const base = { recapHref: "/games/4/report?kind=E&year=2026&tab=overview", backendFinal: true, kind: "E", year: 2026 };
  assert.deepEqual(reportEntry({ ...base, previewHref: undefined }), { pending: true });
  assert.deepEqual(reportEntry({ ...base, previewHref: "/games/1/preview?kind=C&year=2026&tab=overview" }),
    { pending: false, href: "/games/1/preview?kind=C&year=2026&tab=overview", text: "下一場觀戰報告" });
  assert.deepEqual(reportEntry({ ...base, previewHref: null }), { pending: false, href: base.recapHref, text: "場間報告：下一場兩隊背景" });
  // 後端尚未定案（只有頁面層完賽）時不會去解析，直接給場間報告，不會卡在空位。
  assert.equal((reportEntry({ ...base, backendFinal: false, previewHref: undefined }) as { pending: boolean }).pending, false);
  assert.equal(reportEntry({ ...base, recapHref: null, previewHref: undefined }), null);
});
