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
