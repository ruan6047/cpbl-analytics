// deep-link 編碼契約（UX-MATCHUP2）：球員頁「在投打對決頁開啟」產生的網址
// 必須與 matchups-client 的 URL 解析對得起來——預設值不寫進 URL、
// range 才帶年份、opp 優先於 pick。
import assert from "node:assert/strict";
import test from "node:test";

import { CURRENT_YEAR, DEFAULT_CONTROLS, matchupsHref } from "./controls.ts";

test("預設控制只帶 pid（打者視角、本季、例行賽都是預設值）", () => {
  assert.equal(matchupsHref("0000000001", "batting", DEFAULT_CONTROLS), "/matchups?pid=0000000001");
});

test("投手視角與對某隊寫進 URL", () => {
  const href = matchupsHref("0000000002", "pitching", { ...DEFAULT_CONTROLS, team: "ACN011" });
  const p = new URLSearchParams(href.split("?")[1]);
  assert.equal(p.get("role"), "pitching");
  assert.equal(p.get("pid"), "0000000002");
  assert.equal(p.get("team"), "ACN011");
  assert.equal(p.get("scope"), null);
});

test("range 範圍帶 from/to；season/career 不帶年份", () => {
  const range = matchupsHref("X", "batting", {
    ...DEFAULT_CONTROLS, scope: "range", fromYear: 2020, toYear: 2024,
  });
  const p = new URLSearchParams(range.split("?")[1]);
  assert.equal(p.get("scope"), "range");
  assert.equal(p.get("from"), "2020");
  assert.equal(p.get("to"), "2024");

  const career = matchupsHref("X", "batting", { ...DEFAULT_CONTROLS, scope: "career" });
  const q = new URLSearchParams(career.split("?")[1]);
  assert.equal(q.get("scope"), "career");
  assert.equal(q.get("from"), null);
  assert.equal(q.get("to"), null);
});

test("選定 opp 時不再帶 pick；僅搜尋中才帶 pick=1", () => {
  const withOpp = matchupsHref("X", "batting", { ...DEFAULT_CONTROLS, opp: "Y", pick: true });
  const p = new URLSearchParams(withOpp.split("?")[1]);
  assert.equal(p.get("opp"), "Y");
  assert.equal(p.get("pick"), null);

  const picking = matchupsHref("X", "batting", { ...DEFAULT_CONTROLS, pick: true });
  const q = new URLSearchParams(picking.split("?")[1]);
  assert.equal(q.get("pick"), "1");
});

test("非預設排序寫進 URL；賽事類型非例行賽寫進 URL", () => {
  const href = matchupsHref("X", "batting", {
    ...DEFAULT_CONTROLS, kind: "E", sort: "ops", order: "asc",
  });
  const p = new URLSearchParams(href.split("?")[1]);
  assert.equal(p.get("kind"), "E");
  assert.equal(p.get("sort"), "ops");
  assert.equal(p.get("order"), "asc");
});

test("預設年度範圍界線合理（防止 CURRENT_YEAR 計算被改壞）", () => {
  assert.ok(DEFAULT_CONTROLS.fromYear === CURRENT_YEAR - 1);
  assert.ok(DEFAULT_CONTROLS.toYear === CURRENT_YEAR);
});
