import assert from "node:assert/strict";
import test from "node:test";

import type { LiveSnapshot } from "./live-game.ts";
import { liveViewFor } from "./not-needed-game.ts";

// #391 退回修正（需求方裁定 issuecomment-6513852806）：正式站 /games/7?kind=C&year=2026 同時顯示
// 「這一場不舉行」與「未開賽」狀態章、「更新中斷」、兩隊先發名單（post-deploy/05-game-C7.jpg）。
//
// 樣本來源：
// - SLOT：正式站 GET /api/v1/postseason-summary?kind_code=A&season=2026（2026-10-30 取得）的
//   series_context.arrangement 中 2026/C/7 那一格，逐字（真實）。
// - SNAPSHOT：⚠️ 構造。事發當下的快照已過 TTL（同日 GET /api/v1/games/7/live 回 live_snapshot=null），
//   取不回原文；欄位依 LiveSnapshot 型別、值依截圖（狀態章「未開賽」＝phase scheduled、「更新中斷」＝stale／
//   source error、「資料可能已過期」先發名單）構造。
const SLOT = {
  slot_id: "C-sno7", kind_code: "C", seq: 7, announced: false, announced_date: null, date: "2026-10-27",
  start: null, away: { code: "ACN011" }, home: { code: "AAA011" }, venue: { name: "樂天桃園" },
  conditional: false, official_sno: null, game_key: { year: 2026, kind_code: "C", game_sno: 7 }, change: null,
  display_status: "not_needed", hidden_not_needed: true,
} as const;

const SNAPSHOT = {
  game_id: "2026-C-7", game_sno: 7, kind_code: "C", phase: "scheduled", raw_status: "SCHEDULED",
  starts_at: "2026-10-27T18:35:00+08:00", inning: null, half: null, event_count: 0, tracking_count: 0,
  tracking_availability: "not_announced", poll_after_seconds: 60, freshness: "stale", source_status: "error",
  stale_after_seconds: 1200, source: { fetched_at: "2026-10-27T17:00:00+08:00" },
  away: { team: { code: "ACN011", name: "中信兄弟" }, score: 0, inning_score: [],
    lineup: { availability: "not_announced", items: [] }, hitters: [], pitchers: [],
    probable_pitcher: { availability: "not_announced" } },
  home: { team: { code: "AAA011", name: "味全龍" }, score: 0, inning_score: [],
    lineup: { availability: "not_announced", items: [] }, hitters: [], pitchers: [],
    probable_pitcher: { availability: "not_announced" } },
  livelog: [],
} as unknown as LiveSnapshot;

test("not_needed：快照不再決定狀態章／先發名單，不顯示更新中斷、不輪詢", () => {
  const view = liveViewFor(SLOT.display_status === "not_needed", SNAPSHOT, "source");
  assert.deepEqual(view, { snapshot: null, interrupted: false, poll: false });
});

test("其他場次：即時行為原樣（快照、中斷判定、輪詢都不變）", () => {
  assert.deepEqual(liveViewFor(false, SNAPSHOT, null), { snapshot: SNAPSHOT, interrupted: true, poll: true });
  assert.deepEqual(liveViewFor(false, null, "network"), { snapshot: null, interrupted: true, poll: true });
  assert.deepEqual(liveViewFor(false, { ...SNAPSHOT, freshness: "fresh" } as LiveSnapshot, null),
    { snapshot: { ...SNAPSHOT, freshness: "fresh" }, interrupted: false, poll: true });
});
