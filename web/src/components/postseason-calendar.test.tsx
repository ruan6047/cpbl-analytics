import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AnnouncedCompact, AnnouncedMobile } from "./postseason-calendar.tsx";
import { POSTSEASON_2026 } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, type JourneySlot } from "@/lib/postseason-journey.ts";

// #237 日曆公告格的渲染測試：可讀性修正後，格內只標例外狀態，重要限制仍在。

function text(node: ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const slots = (nowIso: string) => buildPostseasonJourney({
  announcement: POSTSEASON_2026, summary: [], rows: null, nowMs: Date.parse(nowIso), dataAsOf: "2026-10-04",
}).slots;
const byKey = (xs: JourneySlot[], k: string) => xs.find((s) => s.key === k)!;

test("手機公告格：一行主客、一行球場；不逐格掛「公告安排」；如有必要與 G3／G4 球場分支可見", () => {
  const xs = slots("2026-10-08T12:00:00+08:00");
  const e3 = text(<AnnouncedMobile s={byKey(xs, "E3")} asOf="2026-10-04" />);
  assert.match(e3, /^季後挑戰賽 G3 如有必要 17:05 開打 .*統一獅（客） 對 .*中信兄弟（主） 洲際$/);
  assert.doesNotMatch(e3, /公告安排/);
  const c3 = text(<AnnouncedMobile s={byKey(xs, "C3")} asOf="2026-10-04" />);
  assert.match(c3, /味全龍（客） 對 (待 )?挑戰賽勝隊（主） 球場依晉級隊：兄弟晉級→大巨蛋／統一晉級→亞太主/);
  assert.doesNotMatch(c3, /挑戰賽勝隊.*挑戰賽勝隊/, "未定席位只念一次");
  // G5–G7（10/08 核對官方公告）：挑戰賽勝隊為客、味全龍為主、大巨蛋、如有必要。
  const c5 = text(<AnnouncedMobile s={byKey(xs, "C5")} asOf="2026-10-04" />);
  assert.match(c5, /^台灣大賽 G5 如有必要 18:35 開打 (待 )?挑戰賽勝隊（客） 對 .*味全龍（主） 大巨蛋$/);
  assert.doesNotMatch(c5, /本站未取得/);
});

test("公告格的例外狀態仍標示：已過開賽時間 → 賽果待更新與截至；桌面格同樣只標例外", () => {
  const xs = slots("2026-10-09T21:00:00+08:00");
  const m = text(<AnnouncedMobile s={byKey(xs, "E1")} asOf="2026-10-04" />);
  assert.match(m, /季後挑戰賽 G1 賽果待更新 17:05 開打/);
  assert.match(m, /已過預定開賽時間・本站尚無賽果紀錄（本站賽果紀錄至 10\/04）/);
  assert.match(text(<AnnouncedCompact s={byKey(xs, "E1")} />), /賽果待更新/);
  const d2 = renderToStaticMarkup(<AnnouncedCompact s={byKey(xs, "E2")} />);
  assert.match(d2, /data-announced="true"/);
  assert.doesNotMatch(text(<AnnouncedCompact s={byKey(xs, "E2")} />), /公告安排/);
  assert.doesNotMatch(d2, /<a /, "公告格不給單場連結");
});
