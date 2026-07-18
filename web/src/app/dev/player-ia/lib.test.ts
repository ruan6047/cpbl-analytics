import assert from "node:assert/strict";
import test from "node:test";
import { anchorHashForRoleSwitch, anchorLayerFromHash } from "./anchor.ts";

test("anchorLayerFromHash 只接受四層 IA 的合法 hash", () => {
  assert.equal(anchorLayerFromHash("#splits"), "splits");
  assert.equal(anchorLayerFromHash("#career"), "career");
  assert.equal(anchorLayerFromHash("#unknown"), null);
  assert.equal(anchorLayerFromHash(""), null);
});

test("role query 轉換後仍以 URL hash 作為 anchors 變體的定位真相", () => {
  const nextUrl = "/dev/player-ia/anchors/twoway?role=pitching#splits";
  assert.equal(anchorLayerFromHash(new URL(nextUrl, "http://localhost").hash), "splits");
});

test("切換 role 時優先保留既有 hash，不受 Hero 按鈕自動捲回頁首影響", () => {
  assert.equal(anchorHashForRoleSwitch("#splits", "overview"), "#splits");
  assert.equal(anchorHashForRoleSwitch("", "career"), "#career");
});
