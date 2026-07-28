import assert from "node:assert/strict";
import test from "node:test";

import { isSelfRefresh } from "./team-records-format.ts";

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
