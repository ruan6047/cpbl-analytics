import assert from "node:assert/strict";
import test from "node:test";

import { streakLabel, streakZh } from "./team-streak.ts";

// 自球隊頁抽出（#287 E9）：行為逐案與原 inline 實作相同。
test("streakZh keeps the team page wording", () => {
  assert.equal(streakZh(null), "—");
  assert.equal(streakZh("勝2"), "二連勝");
  assert.equal(streakZh("敗 3"), "三連敗");
  assert.equal(streakZh("負1"), "1敗");
  assert.equal(streakZh("和1"), "1和");
  assert.equal(streakZh("勝12"), "十二連勝");
  assert.equal(streakZh("勝20"), "二十連勝");
  assert.equal(streakZh("勝0"), "勝0");
  assert.equal(streakZh("其他"), "其他");
});

test("streakLabel maps backend trailing streak through the same wording", () => {
  assert.equal(streakLabel({ result: "W", len: 2, through: "2025/C/5" }), "二連勝");
  assert.equal(streakLabel({ result: "L", len: 1, through: "2025/A/314" }), "1敗");
  assert.equal(streakLabel({ result: "T", len: 1, through: "2025/A/1" }), "1和");
  assert.equal(streakLabel(null), "—");
});
