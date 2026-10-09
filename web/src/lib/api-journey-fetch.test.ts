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

// #237 單場賽況入口：首頁與日曆在伺服器端查公告場號的單場狀態，只用來決定要不要給連結。
// 必須 no-store、時間有界，任何失敗（4xx／5xx／例外／逾時／壞 JSON）都回 null，不拋到頁面。

test("單場入口狀態：no-store、帶逾時訊號、網址帶 kind 與 season", async () => {
  stubFetch();
  await api.liveEntryStatus(1, "E", 2026);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url.replace(/^https?:\/\/[^/]+/, ""), "/api/v1/games/1/status?kind_code=E&season=2026");
  assert.equal(calls[0].init.cache, "no-store");
  assert.equal(calls[0].init.next, undefined);
  assert.ok(calls[0].init.signal instanceof AbortSignal, "要有逾時訊號");
});

test("單場入口狀態：4xx／5xx／例外／壞 JSON 都回 null", async () => {
  for (const status of [404, 500, 503]) {
    globalThis.fetch = (async () => new Response("{}", { status })) as typeof fetch;
    assert.equal(await api.liveEntryStatus(1, "E", 2026), null, `HTTP ${status}`);
  }
  globalThis.fetch = (async () => { throw new TypeError("fetch failed"); }) as typeof fetch;
  assert.equal(await api.liveEntryStatus(1, "E", 2026), null, "連線例外");
  globalThis.fetch = (async () => new Response("not json", { status: 200 })) as typeof fetch;
  assert.equal(await api.liveEntryStatus(1, "E", 2026), null, "壞 JSON");
});

test("單場入口狀態：逾時即放棄並回 null", async () => {
  globalThis.fetch = ((_url: string, init: RequestInit) => new Promise((_, reject) => {
    init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
  })) as typeof fetch;
  // 拿掉逾時訊號時 fetch 永不結束：用哨兵讓測試自己有界並明確轉紅，而不是掛住。
  const HUNG = Symbol("hung");
  let timer: ReturnType<typeof setTimeout> | undefined;
  const got = await Promise.race([
    api.liveEntryStatus(1, "E", 2026, 50),
    new Promise<typeof HUNG>((resolve) => { timer = setTimeout(() => resolve(HUNG), 1000); }),
  ]);
  clearTimeout(timer);
  assert.notEqual(got, HUNG, "逾時應有界");
  assert.equal(got, null);
});
