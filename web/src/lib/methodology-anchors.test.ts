import assert from "node:assert/strict";
import test from "node:test";

import { METHODOLOGY_SECTIONS, methodologyHref } from "./methodology-anchors.ts";

test("anchor map 涵蓋 §5.14 列舉的五類模型", () => {
  assert.deepEqual(Object.keys(METHODOLOGY_SECTIONS), [
    "pregame",
    "winprob",
    "pa-sim",
    "matchup-credibility",
    "pitch-type",
  ]);
});

test("methodologyHref 產生可 deep-link 的段落連結", () => {
  // §7.1-5 指名 /predict 未來轉址目標為 /methodology#pregame。
  assert.equal(methodologyHref("pregame"), "/methodology#pregame");
  assert.equal(methodologyHref("matchup-credibility"), "/methodology#matchup-credibility");
});

test("methodologyHref 不帶段落時回頁首", () => {
  assert.equal(methodologyHref(), "/methodology");
});
