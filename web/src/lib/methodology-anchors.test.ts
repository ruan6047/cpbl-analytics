import assert from "node:assert/strict";
import test from "node:test";

import { METHODOLOGY_SECTIONS, methodologyHref } from "./methodology-anchors.ts";

test("anchor map 涵蓋 §5.14 列舉的五類模型＋場中 WP 時間外驗證節＋關鍵打席選取節", () => {
  assert.deepEqual(Object.keys(METHODOLOGY_SECTIONS), [
    "pregame",
    "winprob",
    "winprob-validation",
    // UX-GAME-RECAP1：關鍵打席「以勝率擺動選取＋顯示」的統計依據與守門條件
    "key-plays",
    "pa-sim",
    "matchup-credibility",
    "pitch-type",
  ]);
});

test("methodologyHref 產生可 deep-link 的段落連結", () => {
  // §7.1-5 指名 /predict 未來轉址目標為 /methodology#pregame。
  assert.equal(methodologyHref("pregame"), "/methodology#pregame");
  assert.equal(methodologyHref("matchup-credibility"), "/methodology#matchup-credibility");
  // UX-WP-DISCLOSURE1：賽況頁 WP 曲線誠實註記 deep-link 目標。
  assert.equal(methodologyHref("winprob-validation"), "/methodology#winprob-validation");
  // UX-GAME-RECAP1：賽後關鍵打席卡的選取準則 deep-link 目標。
  assert.equal(methodologyHref("key-plays"), "/methodology#key-plays");
});

test("methodologyHref 不帶段落時回頁首", () => {
  assert.equal(methodologyHref(), "/methodology");
});
