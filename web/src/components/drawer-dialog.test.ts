import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// #467：季後賽名單抽屜改用原生 <dialog>＋showModal()，Escape、焦點限制與 top layer 交給瀏覽器。
// （行動選單依需求方裁定維持舊實作，不在本守衛範圍：issuecomment-7237196681。）
// 抽屜是 client-only 互動（showModal 在 layout effect 內呼叫），node 內無 DOM 可驗行為，行為另以實際瀏覽器／
// iOS 模擬器驗；這裡在原文層級守住「不再走 portal、不再自寫 Escape／焦點陷阱、body.style 只在帶理由的捲動鎖內」。
const roster = readFileSync(new URL("./playoffs/roster-drawer.tsx", import.meta.url), "utf8");
// 註解不算（說明舊作法的註解可以留著）。
const code = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

test('roster-drawer：改用 <dialog>＋showModal()，不再 createPortal、不再自寫 role="dialog"／aria-modal（驗收 3）', () => {
  const c = code(roster);
  assert.doesNotMatch(c, /createPortal/);
  assert.doesNotMatch(c, /role="dialog"/);
  assert.doesNotMatch(c, /aria-modal/);
  assert.match(c, /<dialog\b/);
  assert.match(c, /\.showModal\(\)/);
});

test("roster-drawer：Escape 走原生 cancel、點背景以 target===dialog 判斷，不再監聽 keydown、不再自寫焦點陷阱", () => {
  const c = code(roster);
  assert.match(c, /onCancel=/);
  assert.match(c, /e\.target === e\.currentTarget/);
  assert.doesNotMatch(c, /addEventListener\("keydown"/);
  assert.doesNotMatch(c, /trapFocus|e\.key === "Tab"/);
});

// 驗收 3 放寬條款：名單抽屜依 iOS 實測保留 JS 捲動鎖（L3），只允許在帶理由註解的 useBodyScrollLock 內改 body.style。
test("roster-drawer：body.style 只出現在帶 iOS 實測理由註解的 useBodyScrollLock 內（驗收 3 放寬條款）", () => {
  const c = code(roster);
  const start = c.indexOf("function useBodyScrollLock()");
  assert.ok(start >= 0, "找不到 useBodyScrollLock");
  const end = c.indexOf("\nexport function RosterDrawer(");
  assert.ok(end > start);
  // 鎖以外的範圍完全不得碰 body 或 .style（含 `const { style } = document.body`、`const { body } = document` 這類別名寫法）。
  assert.doesNotMatch(c.slice(0, start) + c.slice(end), /document\.body|\bbody\b|\.style\b/);
  const doc = roster.slice(0, roster.indexOf("function useBodyScrollLock()"));
  assert.match(doc.slice(doc.lastIndexOf("/**")), /刻意保留[\s\S]*iOS[\s\S]*26\.5[\s\S]*27\.2/);
});
