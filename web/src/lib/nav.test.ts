import assert from "node:assert/strict";
import test from "node:test";

import { METHODOLOGY_PATH } from "./methodology-anchors.ts";
import { MORE_NAV, PRIMARY_NAV, isMoreActive, isNavActive } from "./nav.ts";

test("主導覽為方案 B 的今日／賽程／戰績／球員／對戰", () => {
  assert.deepEqual(
    PRIMARY_NAV.map((n) => n.label),
    ["今日", "賽程", "戰績", "球員", "對戰"]
  );
});

test("「球員」直達打者排行，不建立 /players landing", () => {
  const players = PRIMARY_NAV.find((n) => n.label === "球員");
  assert.equal(players?.href, "/batters");
  assert.equal(
    PRIMARY_NAV.some((n) => n.href === "/players" || n.href === "/explore"),
    false
  );
});

test("「更多」收納紀錄室、球場、方法與待退場的賽事預測", () => {
  assert.deepEqual(
    MORE_NAV.map((n) => n.label),
    ["紀錄室", "球場", "方法", "賽事預測"]
  );
});

test("「方法」路徑與 anchor map 的 METHODOLOGY_PATH 一致，兩處不得各寫字串", () => {
  const method = MORE_NAV.find((n) => n.label === "方法");
  assert.equal(method?.href, METHODOLOGY_PATH);
});

test("「方法」不佔主要導覽（§4.1）", () => {
  assert.equal(
    PRIMARY_NAV.some((n) => n.href === METHODOLOGY_PATH),
    false
  );
});

test("「今日」只在首頁作用中", () => {
  const home = PRIMARY_NAV[0];
  assert.equal(isNavActive(home, "/"), true);
  assert.equal(isNavActive(home, "/games"), false);
});

test("「球員」在打者、投手排行與個人頁都作用中", () => {
  const players = PRIMARY_NAV.find((n) => n.label === "球員")!;
  assert.equal(isNavActive(players, "/batters"), true);
  assert.equal(isNavActive(players, "/pitchers"), true);
  assert.equal(isNavActive(players, "/players/A123456789"), true);
  assert.equal(isNavActive(players, "/standings"), false);
});

test("作用中判定比對路徑邊界，不把 /venues-x 當成 /venues", () => {
  const venues = MORE_NAV.find((n) => n.href === "/venues")!;
  assert.equal(isNavActive(venues, "/venues"), true);
  assert.equal(isNavActive(venues, "/venues/洲際"), true);
  assert.equal(isNavActive(venues, "/venues-x"), false);
});

test("「更多」在收納項作用時一併標示", () => {
  assert.equal(isMoreActive("/records"), true);
  assert.equal(isMoreActive("/predict"), true);
  assert.equal(isMoreActive("/standings"), false);
});
