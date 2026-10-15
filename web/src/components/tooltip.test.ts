import assert from "node:assert/strict";
import test from "node:test";

import { isTouchActivation } from "./tooltip.tsx";

// #300：觸控「點一下出現、再點收起」的判斷。iOS Safari 點擊時 click 的 pointerType 是 "mouse"
// （前面的 pointerup／touchstart 才是觸控），只看 click.pointerType 會讓 iOS 永遠不切換。

test("觸發點最近記到觸控：即使 click 自稱 mouse 也算觸控（iOS Safari 實測序列）", () => {
  assert.equal(isTouchActivation("touch", "mouse"), true);
});

test("觸發點最近記到滑鼠或筆：不切換（桌機移入已出現，點一下不得把它關掉）", () => {
  assert.equal(isTouchActivation("mouse", "mouse"), false);
  assert.equal(isTouchActivation("pen", "pen"), false);
  assert.equal(isTouchActivation("mouse", "touch"), false);
});

test("沒有記錄：沿用原判斷（click 為 touch 或事件沒有 pointerType 才切換）", () => {
  assert.equal(isTouchActivation(null, "touch"), true);
  assert.equal(isTouchActivation(null, undefined), true);
  assert.equal(isTouchActivation(null, "mouse"), false);
  assert.equal(isTouchActivation(null, ""), false); // 鍵盤觸發的 click
});
