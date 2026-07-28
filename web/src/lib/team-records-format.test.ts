import assert from "node:assert/strict";
import test from "node:test";

import { isSelfRefresh, splitFranchiseByRole } from "./team-records-format.ts";

// —— isSelfRefresh：原紀錄保持人是否為本人，一律比對 player_id 不比 name ——
//
// 每個情境都刻意讓 name／prior_holder（姓名字串）跟 player_id／prior_holder_id
// 「打架」——姓名字串暗示一個答案、id 暗示另一個答案。若實作退回姓名比對
// （例如 `row.name === row.prior_holder`），下面兩個測試都會給出跟斷言相反的
// 結果，直接證明測試真的釘在「用 id 比對」這件事上，不是巧合通過。

test("同 player_id 判定為本人，即使姓名字串不同（模擬改名/舊資料殘留）", () => {
  const row = {
    player_id: "p1", name: "新名字",
    prior_holder_id: "p1", prior_holder: "舊名字（改名前）",
  };
  assert.equal(isSelfRefresh(row), true);
});

test("不同 player_id 判定為不同人，即使姓名字串相同（同名不同人）", () => {
  const row = {
    player_id: "p1", name: "陳偉",
    prior_holder_id: "p2", prior_holder: "陳偉",
  };
  assert.equal(isSelfRefresh(row), false);
});

test("prior_holder_id 為 null（並列多人）時保守判定為不同人", () => {
  const row = { player_id: "p1", name: "甲", prior_holder_id: null, prior_holder: "甲、乙" };
  assert.equal(isSelfRefresh(row), false);
});

// —— splitFranchiseByRole：隊史紀錄拆野手／投手頁籤，純依 role 分組 ——

test("依 role 分組，不遺漏不重複", () => {
  const items = [
    { role: "batting" as const, stat: "h" },
    { role: "pitching" as const, stat: "so" },
    { role: "batting" as const, stat: "hr" },
  ];
  const { batting, pitching } = splitFranchiseByRole(items);
  assert.deepEqual(batting.map((r) => r.stat), ["h", "hr"]);
  assert.deepEqual(pitching.map((r) => r.stat), ["so"]);
});

test("role 為單一類別時，另一類回傳空陣列（供呼叫端判斷頁籤是否出現）", () => {
  const items = [{ role: "batting" as const, stat: "h" }];
  const { batting, pitching } = splitFranchiseByRole(items);
  assert.equal(batting.length, 1);
  assert.deepEqual(pitching, []);
});

// 變異防呆：證明這個函式**不會**依 `stat`/`state` 做任何抑制判斷——只看
// `role`。若有人誤把「同 stat 已有 refreshed 就抑制」的邏輯搬進這裡（等於
// 讓抑制退化成「同頁籤內才抑制」，違反卡面要求），這個 approaching 列會被
// 誤刪，下面的斷言會失敗。抑制本身的正確性由後端
// `test_franchise_records_approaching_suppressed_when_refreshed_exists_for_same_stat`
// （`tests/test_pure_helpers.py`）覆蓋，這裡只釘住「前端分組不得重新實作
// 抑制」這條邊界。
test("即使同 stat 已有另一 role 的 refreshed，本函式仍原樣保留 approaching（不重新實作抑制）", () => {
  const items = [
    { role: "batting" as const, stat: "x", state: "refreshed" as const },
    { role: "pitching" as const, stat: "x", state: "approaching" as const },
  ];
  const { pitching } = splitFranchiseByRole(items);
  assert.deepEqual(pitching, [{ role: "pitching", stat: "x", state: "approaching" }]);
});
