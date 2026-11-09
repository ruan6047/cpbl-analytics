import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

import { gameMetadata, gameMetadataPath, gameStatusPath, playerMetadata } from "./entity-metadata.ts";
import { setSharedCacheForTest } from "./api-cache.ts";
import { memorySharedCache } from "./api-cache.testkit.ts";

// metadata 的成功資料依原 300 秒共享（#441 規劃 v2）；node:test 以記憶體替身代入 Next 資料快取。
afterEach(() => setSharedCacheForTest(null));

const LIVE_0_0 = { game: { away_team_name: "樂天桃猿", home_team_name: "統一7-ELEVEn獅", away_score: 0, home_score: 0 } };

async function titleWith(status: unknown, statusOk = true): Promise<unknown> {
  setSharedCacheForTest(memorySharedCache().impl);   // 每個情境各自冷起點
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

// #441：SSR metadata 取數失敗只退回中性標題，不拋到頁面；壞 JSON 也要接住（原本未 await 會漏接）。
// 失敗不進共享快取：恢復後下一次請求就取新標題；成功標題之後依 TTL 共用（內層 fetch 仍 no-store）。
test("球員 metadata：500／斷線／壞 JSON 都退回中性標題，恢復後下一次即取新名，之後共用成功值", async () => {
  const shared = memorySharedCache();
  setSharedCacheForTest(shared.impl);
  const original = globalThis.fetch;
  const inits: RequestInit[] = [];
  let mode: "500" | "down" | "badjson" | "ok" = "500";
  globalThis.fetch = (async (_input: string | URL | Request, init: RequestInit) => {
    inits.push(init);
    if (mode === "down") throw new TypeError("fetch failed");
    if (mode === "500") return new Response("{}", { status: 500 });
    if (mode === "badjson") return new Response("<html>", { status: 200 });
    return new Response(JSON.stringify({ player: { name: "恢復姓名" } }));
  }) as typeof fetch;
  try {
    for (const m of ["500", "down", "badjson"] as const) {
      mode = m;
      assert.deepEqual(await playerMetadata("0000000001"), { title: "球員資料" }, m);
    }
    mode = "ok";
    assert.deepEqual(await playerMetadata("0000000001"), { title: "恢復姓名｜球員" });
    const before = inits.length;
    mode = "500";   // 已有成功值：TTL 內照常顯示成功標題，不再發 API
    assert.deepEqual(await playerMetadata("0000000001"), { title: "恢復姓名｜球員" });
    assert.equal(inits.length, before);
    assert.deepEqual(shared.keys.at(-1)?.[3], "ttl=300");
    for (const init of inits) {
      assert.equal(init.cache, "no-store");
      assert.equal((init as { next?: unknown }).next, undefined);
    }
  } finally {
    globalThis.fetch = original;
  }
});
