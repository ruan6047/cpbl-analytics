import assert from "node:assert/strict";
import { test } from "node:test";
import {
  SPARSE_PITCHES, createLoadTracker, levelFromParams, loadGroup, playerNavFromParams,
  primaryRole, roleFromParams, scopeFromParams, sparsePitchNote, viewFromParams, viewsFor,
} from "./layers.ts";

const BOTH: ("batting" | "pitching")[] = ["batting", "pitching"];
const BAT: ("batting" | "pitching")[] = ["batting"];
const PIT: ("batting" | "pitching")[] = ["pitching"];

test("新 IA：本季與生涯各自只列該 scope 可用的內容 view", () => {
  assert.deepEqual(viewsFor("season"), ["overview", "tracking", "splits", "fielding"]);
  assert.deepEqual(viewsFor("career"), ["overview", "yearly", "splits", "fielding", "value"]);
});

test("scope：明示參數優先；舊 sec=career 與退役預設能遷移", () => {
  assert.equal(scopeFromParams("season", "career", true), "season");
  assert.equal(scopeFromParams("career", "batting", false), "career");
  assert.equal(scopeFromParams(null, "career", false), "career");
  assert.equal(scopeFromParams(null, null, true), "career");
  assert.equal(scopeFromParams("invalid", null, false), "season");
});

test("role：明示參數優先但不得切到不存在的身分；舊 sec 仍可遷移", () => {
  assert.equal(roleFromParams("pitching", null, BOTH), "pitching");
  assert.equal(roleFromParams("pitching", null, BAT), "batting");
  assert.equal(roleFromParams(null, "pitching", BOTH), "pitching");
  assert.equal(roleFromParams(null, "batting", PIT), "pitching");
});

test("view：新參數須屬於當前 scope；舊 sec deterministic 映射", () => {
  assert.equal(viewFromParams("tracking", null, "season"), "tracking");
  assert.equal(viewFromParams("tracking", null, "career"), "overview");
  assert.equal(viewFromParams(null, "batting", "season"), "tracking");
  assert.equal(viewFromParams(null, "splits", "career"), "splits");
  assert.equal(viewFromParams(null, "career", "career"), "overview");
  assert.equal(viewFromParams("../evil", null, "season"), "overview");
});

test("level：合法 URL 優先；否則二軍球員預設 D、其他預設 A", () => {
  assert.equal(levelFromParams("A", "二軍"), "A");
  assert.equal(levelFromParams("D", "一軍"), "D");
  assert.equal(levelFromParams(null, "二軍"), "D");
  assert.equal(levelFromParams("invalid", "一軍"), "A");
});

test("playerNavFromParams 一次產出整頁唯一 navigation state", () => {
  assert.deepEqual(
    playerNavFromParams({ scope: null, view: null, role: null, level: null, sec: "career" }, BOTH, false, "一軍"),
    { scope: "career", view: "overview", role: "batting", level: "A" },
  );
  assert.deepEqual(
    playerNavFromParams({ scope: "season", view: "tracking", role: "pitching", level: "D", sec: null }, BOTH, false, "二軍"),
    { scope: "season", view: "tracking", role: "pitching", level: "D" },
  );
  assert.deepEqual(
    playerNavFromParams({ scope: null, view: null, role: "pitching", level: null, sec: null }, BOTH, false, "一軍"),
    { scope: "season", view: "tracking", role: "pitching", level: "A" },
    "IA2 舊 ?role= 連結應繼續開啟身分內容頁",
  );
  assert.deepEqual(
    playerNavFromParams({ scope: "season", view: null, role: "pitching", level: null, sec: null }, BOTH, false, "一軍"),
    { scope: "season", view: "overview", role: "pitching", level: "A" },
    "新 scope URL 未給 view 時仍預設總覽",
  );
});

test("主身分：有打擊先打擊，否則投球", () => {
  assert.equal(primaryRole(BOTH), "batting");
  assert.equal(primaryRole(PIT), "pitching");
  assert.equal(primaryRole([]), "batting");
});

test("稀疏警示：有樣本但過少才出現，且帶球數與原因", () => {
  const note = sparsePitchNote(14);
  assert.ok(note && note.includes("14"));
  assert.ok(note!.includes("僅供參考"));
  assert.ok(note!.includes("設備"));
});

test("稀疏警示：樣本充足、全無樣本或未載入都不顯示", () => {
  assert.equal(sparsePitchNote(SPARSE_PITCHES), null);
  assert.equal(sparsePitchNote(0), null);
  assert.equal(sparsePitchNote(null), null);
});

// REVIEW-005 P1 回歸：雙棲切回已看過的身分頁不得重抓
test("依身分抓不同資料的群組，role 必須進組名而非只進 key", () => {
  assert.notEqual(loadGroup("tracking", "batting"), loadGroup("tracking", "pitching"));
  // 與 role 無關的群組不加後綴，避免無謂的快取分裂
  assert.equal(loadGroup("season"), loadGroup("season", null));
});

test("雙棲在打擊↔投球之間來回，切回已看過的頁不得重抓", () => {
  const should = createLoadTracker();
  const visit = (role: "batting" | "pitching") =>
    should(loadGroup("tracking", role), `p1-${role}-A`);

  assert.equal(visit("batting"), true, "首次進打擊頁應抓");
  assert.equal(visit("pitching"), true, "首次進投球頁應抓");
  assert.equal(visit("batting"), false, "切回打擊頁不得重抓");
  assert.equal(visit("pitching"), false, "再切回投球頁不得重抓");
});

test("換球員或換一／二軍鏡頭仍必須重抓（快取不可過度黏著）", () => {
  const should = createLoadTracker();
  assert.equal(should(loadGroup("tracking", "batting"), "p1-batting-A"), true);
  assert.equal(should(loadGroup("tracking", "batting"), "p2-batting-A"), true, "換球員要重抓");
  assert.equal(should(loadGroup("tracking", "batting"), "p2-batting-D"), true, "換二軍鏡頭要重抓");
  assert.equal(should(loadGroup("tracking", "batting"), "p2-batting-D"), false);
});

test("不同 role 的資料各自獨立快取，互不覆蓋", () => {
  const should = createLoadTracker();
  for (const g of ["trend", "splits", "career"] as const) {
    assert.equal(should(loadGroup(g, "batting"), "p1-batting"), true);
    assert.equal(should(loadGroup(g, "pitching"), "p1-pitching"), true);
    assert.equal(should(loadGroup(g, "batting"), "p1-batting"), false, `${g} 切回不得重抓`);
  }
});
