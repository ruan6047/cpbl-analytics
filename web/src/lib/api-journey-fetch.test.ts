import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { api } from "./api.ts";

// #237 方案 A：當季已公告季後時，季後摘要與 calendar 不走跨請求快取（no-store）；
// 其他呼叫（歷史年份、二軍）照舊 120 秒快取。判準落在實際送出的 fetch 選項與網址。
// 正式建置實測的舊新快照混用見 ui-r3 production 自檢；這裡只驗快取選項，不代表資料庫原子快照。

type Call = { url: string; init: RequestInit & { next?: { revalidate?: number } } };
const realFetch = globalThis.fetch;
let calls: Call[] = [];

function stubFetch() {
  calls = [];
  globalThis.fetch = (async (url: string, init: Call["init"]) => {
    calls.push({ url: String(url), init });
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
}

afterEach(() => {
  globalThis.fetch = realFetch;
});

test("live：季後摘要與 calendar 走 no-store，不帶 revalidate；網址與原本相同", async () => {
  stubFetch();
  await api.postseasonSummary(2026, "A", { live: true });
  await api.gamesCalendar(undefined, "A", { live: true });
  await api.postseasonSummary(undefined, "A", { live: true });
  assert.deepEqual(calls.map((c) => c.url.replace(/^https?:\/\/[^/]+/, "")), [
    "/api/v1/postseason-summary?kind_code=A&season=2026",
    "/api/v1/games/calendar?kind_code=A",
    "/api/v1/postseason-summary?kind_code=A",
  ]);
  for (const c of calls) {
    assert.equal(c.init.cache, "no-store");
    assert.equal(c.init.next, undefined);
  }
});

test("不傳 live（歷史年份、二軍、未公告）：照舊 120 秒快取", async () => {
  stubFetch();
  await api.postseasonSummary(2025, "A");
  await api.gamesCalendar(2025, "A");
  await api.gamesCalendar(undefined, "D", { live: false });
  assert.equal(calls.length, 3);
  for (const c of calls) {
    assert.equal(c.init.cache, undefined);
    assert.equal(c.init.next?.revalidate, 120);
  }
});
