import assert from "node:assert/strict";
import test from "node:test";

import { filterPlayers, roleLabel, toSearchItems } from "./player-search-filter.ts";

const roster = {
  season: 2026,
  batters: [
    { id: "0000000001", name: "林立", team: "中信兄弟" },
    { id: "0000000002", name: "王柏融", team: "味全龍" },
    { id: "0000000003", name: "二刀流", team: "統一獅" },
    { id: "0000000004", name: null, team: "樂天桃猿" },
  ],
  pitchers: [
    { id: "0000000005", name: "羅戈", team: "中信兄弟" },
    { id: "0000000003", name: "二刀流", team: "統一獅" },
  ],
};

test("toSearchItems 把二刀流球員合併為單一項並保留兩種角色", () => {
  const items = toSearchItems(roster);
  const twoWay = items.filter((p) => p.id === "0000000003");
  assert.equal(twoWay.length, 1);
  assert.deepEqual(twoWay[0].roles, ["batter", "pitcher"]);
});

test("toSearchItems 略過無姓名球員：無法被姓名搜尋到", () => {
  assert.equal(
    toSearchItems(roster).some((p) => p.id === "0000000004"),
    false
  );
});

test("filterPlayers 以姓名或球隊比對", () => {
  const items = toSearchItems(roster);
  assert.deepEqual(
    filterPlayers(items, "林立").map((p) => p.id),
    ["0000000001"]
  );
  assert.deepEqual(
    filterPlayers(items, "中信兄弟")
      .map((p) => p.id)
      .sort(),
    ["0000000001", "0000000005"]
  );
});

test("filterPlayers 空白 query 不回結果：搜尋只做導航，不列任意球員", () => {
  const items = toSearchItems(roster);
  assert.deepEqual(filterPlayers(items, ""), []);
  assert.deepEqual(filterPlayers(items, "   "), []);
});

test("filterPlayers 找不到時回空陣列，供空狀態使用", () => {
  assert.deepEqual(filterPlayers(toSearchItems(roster), "不存在的人"), []);
});

test("filterPlayers 限制回傳筆數", () => {
  const many = {
    season: 2026,
    batters: Array.from({ length: 30 }, (_, i) => ({
      id: String(i).padStart(10, "0"),
      name: `測試${i}`,
      team: "中信兄弟",
    })),
    pitchers: [],
  };
  assert.equal(filterPlayers(toSearchItems(many), "測試").length, 8);
  assert.equal(filterPlayers(toSearchItems(many), "測試", 3).length, 3);
});

test("roleLabel 顯示中文角色，二刀流兩者並列", () => {
  assert.equal(roleLabel(["batter"]), "打者");
  assert.equal(roleLabel(["pitcher"]), "投手");
  assert.equal(roleLabel(["batter", "pitcher"]), "打者／投手");
});
