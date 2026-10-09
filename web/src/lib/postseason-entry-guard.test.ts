import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

// #237 驗收 3「三入口沒有互相矛盾的安排」的結構守衛：三個入口都只經由同一個進入點
// 取得季後旅程，不各自讀公告或自行歸併、不各自推讓勝。

const SRC = path.join(import.meta.dirname, "..");
const ENTRIES = ["app/page.tsx", "app/standings/page.tsx", "app/games/page.tsx"];

test("首頁、季後總覽、日曆都經由 postseasonJourneyFor 取得旅程", () => {
  for (const f of ENTRIES) {
    const src = readFileSync(path.join(SRC, f), "utf8");
    assert.match(src, /postseasonJourneyFor\(/, `${f} 必須使用共用旅程模型`);
    assert.doesNotMatch(src, /buildPostseasonJourney\(|POSTSEASON_2026|handicapTeam/,
      `${f} 不得自行建模型、直接讀公告內容或自行決定讓勝`);
  }
});

// 方案 A（需求方 2026-10-08 裁定）：三入口取旅程輸入時都要依「當季已公告」傳 live，
// 否則同一頁會組到不同時間的快照（ui-r3 正式建置實測）。快取選項本身見 api-journey-fetch.test.ts。
test("首頁、季後總覽、日曆取季後摘要與 calendar 時都依當季公告傳 live", () => {
  for (const f of ENTRIES) {
    const src = readFileSync(path.join(SRC, f), "utf8");
    assert.match(src, /announcementFor\(/, `${f} 要以公告判斷是否當季已公告季後`);
    assert.match(src, /const live = \{ live: /, `${f} 要明確組出 live 選項`);
    assert.match(src, /gamesCalendar\([^)]*,\s*live\)/, `${f} 的 calendar 要傳 live`);
    assert.match(src, /postseasonSummary\([^)]*,\s*live\)/, `${f} 的季後摘要要傳 live`);
  }
});

// 單場賽況入口（#237）：首頁與日曆的入口只經由共用模型的 liveEntryProbes／withLiveEntries，
// 查詢以 allSettled 降級；頁面不得自行比對快照或拼單場網址。
test("首頁、日曆的單場賽況入口只經由共用模型，查詢以 allSettled 降級", () => {
  for (const f of ["app/page.tsx", "app/games/page.tsx"]) {
    const src = readFileSync(path.join(SRC, f), "utf8");
    assert.match(src, /liveEntryProbes\(/, `${f} 要用共用的查詢清單`);
    assert.match(src, /withLiveEntries\(/, `${f} 要用共用的身分比對`);
    assert.match(src, /Promise\.allSettled\(probes\.map/, `${f} 的單場狀態查詢要各自降級`);
    assert.doesNotMatch(src, /live_snapshot|officialSno|\/status\?/, `${f} 不得自行比對快照或拼狀態網址`);
  }
});
