import assert from "node:assert/strict";
import test from "node:test";

import { isTouchActivation, shouldCloseOnTouch, tooltipPortalTarget } from "./tooltip.tsx";

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

// #300 R7：同一下觸控裡 hover／focus 可能先把提示打開（delayIn=0 的能力值軸名在 iOS 實測如此），
// click 不能把「這一下才打開的」當成「再點同一個」收掉；只有觸控開始前就已打開才收。
test("觸控開始前已打開：收起（再點同一個）", () => {
  assert.equal(shouldCloseOnTouch(true, true), true);
  assert.equal(shouldCloseOnTouch(true, false), true);
});

test("觸控開始時還沒打開：即使 click 當下已被 hover／focus 打開也不收", () => {
  assert.equal(shouldCloseOnTouch(false, true), false);
  assert.equal(shouldCloseOnTouch(false, false), false);
});

test("沒有觸控開始的記錄：看當下是否打開（原行為）", () => {
  assert.equal(shouldCloseOnTouch(null, true), true);
  assert.equal(shouldCloseOnTouch(null, false), false);
});

// #467 Q1：開啟中的 modal <dialog> 在 top layer，portal 到 body 的提示會被畫在它底下且因 inert 點不到。
// 觸發元素在開啟中的 dialog 內 ⇒ portal 進該 dialog；否則照舊進 body。
test("提示 portal 目標：觸發元素在開啟中的 dialog 內 ⇒ 該 dialog；否則 body；觸發元素未掛上 ⇒ body", () => {
  const body = { id: "body" } as unknown as HTMLElement;
  const dialog = { id: "dialog" } as unknown as HTMLElement;
  const inDialog = { closest: (sel: string) => (sel === "dialog[open]" ? dialog : null) } as unknown as HTMLElement;
  const outside = { closest: () => null } as unknown as HTMLElement;
  assert.equal(tooltipPortalTarget(inDialog, body), dialog);
  assert.equal(tooltipPortalTarget(outside, body), body);
  assert.equal(tooltipPortalTarget(null, body), body);
});
