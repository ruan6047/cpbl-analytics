import assert from "node:assert/strict";
import test from "node:test";

import { DRAWER_COPY, drawerState, pickAbility, playerHref, rosterPlayerPath,
  type RosterMember, type RosterPlayerDetail } from "./playoffs-roster.ts";

// #286 S05 WP4：抽屜純邏輯（版本固定、能力卡取用、深讀連結）。DOM 行為另以實際瀏覽器驗；
// 焦點限制自 #467 起交給原生 <dialog>.showModal()，不再有自寫的焦點陷阱。

const detail = (cv: string | null, season = true, career = true): RosterPlayerDetail => ({
  contract: "playoffs-roster-player/v1", context_version: cv, roster_version: "rv", series: "C", year: 2026,
  team_code: "AAA011",
  player: { player_id: "0000000001", name: "甲", official_position: "投手", tactical_role: null, role: "pitching", level: "A" },
  ability: { season: { available: season, role: "pitching", axes: season ? [] : undefined },
    career: { available: career, role: "pitching", axes: career ? [] : undefined } },
  trend: null,
});

test("版本固定：詳情 context_version ≠ 區資料 ⇒ stale「資料已更新，請重開」；失敗、載入中各自狀態", () => {
  assert.equal(drawerState(null, false, "v1", "rv").kind, "loading");
  assert.equal(drawerState(null, true, "v1", "rv").kind, "error");
  assert.equal(drawerState(detail("v1"), false, "v1", "rv").kind, "ready");
  assert.equal(drawerState(detail("v1"), false, "v2", "rv").kind, "stale");
  assert.equal(drawerState(detail("v1"), false, "v1", "roles-updated").kind, "stale");
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
