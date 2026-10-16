import assert from "node:assert/strict";
import test from "node:test";

import { DRAWER_COPY, drawerState, pickAbility, playerHref, rosterPlayerPath, trapFocus,
  type RosterMember, type RosterPlayerDetail } from "./playoffs-roster.ts";

// #286 S05 WP4：抽屜純邏輯（焦點陷阱、版本固定、能力卡取用、深讀連結）。DOM 行為另以實際瀏覽器驗。

const detail = (cv: string | null, season = true, career = true): RosterPlayerDetail => ({
  contract: "playoffs-roster-player/v1", context_version: cv, roster_version: "rv", series: "C", year: 2026,
  team_code: "AAA011",
  player: { player_id: "0000000001", name: "甲", official_position: "投手", tactical_role: null, role: "pitching", level: "A" },
  ability: { season: { available: season, role: "pitching", axes: season ? [] : undefined },
    career: { available: career, role: "pitching", axes: career ? [] : undefined } },
  trend: null,
});

test("焦點陷阱：Tab 在最後回第一、Shift+Tab 在第一到最後；中間交給瀏覽器；焦點在外 ⇒ 拉回", () => {
  assert.equal(trapFocus(4, 5, false), 0);
  assert.equal(trapFocus(0, 5, true), 4);
  assert.equal(trapFocus(2, 5, false), null);
  assert.equal(trapFocus(2, 5, true), null);
  assert.equal(trapFocus(-1, 5, false), 0);
  assert.equal(trapFocus(-1, 5, true), 4);
  assert.equal(trapFocus(0, 0, false), null);
  assert.equal(trapFocus(0, 1, false), 0);
});

test("版本固定：詳情 context_version ≠ 區資料 ⇒ stale「資料已更新，請重開」；失敗、載入中各自狀態", () => {
  assert.equal(drawerState(null, false, "v1").kind, "loading");
  assert.equal(drawerState(null, true, "v1").kind, "error");
  assert.equal(drawerState(detail("v1"), false, "v1").kind, "ready");
  assert.equal(drawerState(detail("v1"), false, "v2").kind, "stale");
  assert.equal(DRAWER_COPY.stale, "資料已更新，請重開。");
});

test("能力卡：本季優先、否則生涯、都沒有 ⇒ null", () => {
  assert.equal(pickAbility(detail("v"))?.label, DRAWER_COPY.abilitySeason);
  assert.equal(pickAbility(detail("v", false))?.label, DRAWER_COPY.abilityCareer);
  assert.equal(pickAbility(detail("v", false, false)), null);
});

test("深讀連結帶相同角色與層級；詳情路徑", () => {
  const m = (level: "A" | "D" | "none", role: "batting" | "pitching") => ({ player_id: "0000000001", role,
    background: { level } }) as unknown as RosterMember;
  assert.equal(playerHref(m("A", "pitching")), "/players/0000000001?scope=season&view=overview&role=pitching&level=A");
  assert.equal(playerHref(m("D", "batting")), "/players/0000000001?scope=season&view=overview&role=batting&level=D");
  assert.equal(rosterPlayerPath(2026, "C", "0000000001"),
    "/api/v1/playoffs/roster/player?season=2026&series=C&player_id=0000000001");
});
