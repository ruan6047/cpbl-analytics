import assert from "node:assert/strict";
import test from "node:test";

import { gameMetadata, gameMetadataPath, gameStatusPath } from "./entity-metadata.ts";

const LIVE_0_0 = { game: { away_team_name: "樂天桃猿", home_team_name: "統一7-ELEVEn獅", away_score: 0, home_score: 0 } };

async function titleWith(status: unknown, statusOk = true): Promise<unknown> {
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/live?")) return new Response(JSON.stringify(LIVE_0_0));
    if (url.includes("/status?")) return new Response(JSON.stringify(status), { status: statusOk ? 200 : 500 });
    throw new Error(`unexpected fetch ${url}`);
  }) as typeof fetch;
  try {
    return (await gameMetadata("254", { kind: "A", year: "2026" })).title;
  } finally {
    globalThis.fetch = original;
  }
}

test("標題比分：官方未完成狀態或非 final 即時快照不宣稱 0：0（#186）", async () => {
  for (const official of ["scheduled", "postponed", "reserved"]) {
    assert.equal(
      await titleWith({ official_game_status: { status: official }, live_snapshot: null }),
      "樂天桃猿 vs 統一7-ELEVEn獅",
      official,
    );
  }
  assert.equal(
    await titleWith({ official_game_status: { status: "final" }, live_snapshot: { phase: "live" } }),
    "樂天桃猿 vs 統一7-ELEVEn獅",
  );
});

test("標題比分：真 0:0 和局、無排程紀錄的歷史場與狀態讀取失敗維持原顯示", async () => {
  const shown = "樂天桃猿 vs 統一7-ELEVEn獅 0：0";
  assert.equal(await titleWith({ official_game_status: { status: "final" }, live_snapshot: null }), shown);
  assert.equal(await titleWith({ official_game_status: { status: "final" }, live_snapshot: { phase: "final" } }), shown);
  assert.equal(await titleWith({ official_game_status: { status: "unknown" }, live_snapshot: null }), shown);
  assert.equal(await titleWith(null, false), shown);
});

test("狀態查詢與賽況查詢指向同一筆實體", () => {
  assert.equal(gameStatusPath("1", { kind: "D", year: "2026" }), "/api/v1/games/1/status?kind_code=D&season=2026");
});

test("賽事 metadata 依 URL 年度與賽別查詢同一筆實體", () => {
  assert.equal(
    gameMetadataPath("1", { kind: "A", year: "2025" }),
    "/api/v1/games/1/live?kind_code=A&season=2025",
  );
  assert.equal(
    gameMetadataPath("1", { kind: "D", year: "2026" }),
    "/api/v1/games/1/live?kind_code=D&season=2026",
  );
});

test("賽事 metadata 預設一軍，拒絕不合法年度", () => {
  assert.equal(gameMetadataPath("1"), "/api/v1/games/1/live?kind_code=A");
  assert.equal(
    gameMetadataPath("1", { year: "not-a-year" }),
    "/api/v1/games/1/live?kind_code=A",
  );
});
