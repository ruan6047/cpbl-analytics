import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildHighlights as fromPage } from "@/app/games/[sno]/game-summary";

// 黃金值（#288 WP-K3 搬移前產生）：2026 E1–E4 以舊碼 game-summary.ts 的 buildHighlights(live, true) 跑出的「本場焦點」。
// input 只存 E1 規則實際讀取的欄位投影；E2–E4 的期望標籤由執行階段對帳 artifact 以整包 /live 與投影各跑一次確認相同。
const GOLD = JSON.parse(readFileSync(new URL("./__fixtures__/game-highlights_2026E.json", import.meta.url), "utf8")) as {
  expected: Record<string, { text: string; team: string | null }[]>;
  input_game: string;
  input: Record<string, unknown>;
};

test("單場頁 buildHighlights：E1 精簡輸入跑出的標籤＝黃金值（文字、隊別、順序）", () => {
  assert.equal(GOLD.input_game, "E1");
  assert.deepEqual(fromPage(GOLD.input as never, true), GOLD.expected.E1);
});

test("黃金值形狀：E1–E4 都有期望值、每場 ≤12 個", () => {
  assert.deepEqual(Object.keys(GOLD.expected).sort(), ["E1", "E2", "E3", "E4"]);
  for (const [k, v] of Object.entries(GOLD.expected)) assert.ok(v.length <= 12, k);
});

test("未完賽不產生賽事級／球迷用語焦點（completed=false）", () => {
  const out = fromPage(GOLD.input as never, false).map((h) => h.text);
  assert.ok(!out.some((t) => /中計|連續解決|問天|魯閣|煮粥/.test(t)), out.join("/"));
});
