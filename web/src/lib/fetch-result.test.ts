import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { api } from "./api.ts";
import { dataOf, failed, fetchApiJson, notFoundResult, settle, unavailableCopy } from "./fetch-result.ts";
import { ApiError } from "./http-error.ts";

// #441：SSR 取數失敗要保留成可辨識的結果（不整頁錯誤、不冒充空資料、不轉 404），
// 且不經跨請求快取（API 恢復後下一次請求即恢復）。

type Init = RequestInit & { next?: { revalidate?: number } };
const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function respond(make: () => Response | Promise<Response>) {
  const calls: { url: string; init: Init }[] = [];
  globalThis.fetch = (async (url: string, init: Init) => {
    calls.push({ url: String(url), init });
    return make();
  }) as typeof fetch;
  return calls;
}

test("失敗分類：404＝not_found；5xx／斷線／逾時／壞 JSON 都是暫時無法取得", async () => {
  const cases: [string, () => Response | Promise<Response>, string, number][] = [
    ["404", () => new Response("{}", { status: 404 }), "not_found", 404],
    ["500", () => new Response("{}", { status: 500 }), "http", 500],
    ["503", () => new Response("{}", { status: 503 }), "http", 503],
    ["斷線", () => { throw new TypeError("fetch failed"); }, "network", 0],
    ["壞 JSON", () => new Response("not json", { status: 200 }), "parse", 0],
  ];
  for (const [label, make, failure, status] of cases) {
    respond(make);
    const r = await settle(fetchApiJson("http://api", "/x"));
    assert.deepEqual(r, { ok: false, failure, status }, label);
    assert.equal(dataOf(r), null, label);
    assert.equal(failed(r), failure !== "not_found", label);
    assert.equal(notFoundResult(r), failure === "not_found", label);
  }
});

test("逾時：有界放棄並分類為 timeout，不會掛住", async () => {
  globalThis.fetch = ((_url: string, init: RequestInit) => new Promise((_, reject) => {
    init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
  })) as typeof fetch;
  const HUNG = Symbol("hung");
  let timer: ReturnType<typeof setTimeout> | undefined;
  const got = await Promise.race([
    settle(fetchApiJson("http://api", "/slow", 50)),
    new Promise<typeof HUNG>((resolve) => { timer = setTimeout(() => resolve(HUNG), 1000); }),
  ]);
  clearTimeout(timer);
  assert.notEqual(got, HUNG, "逾時應有界");
  assert.deepEqual(got, { ok: false, failure: "timeout", status: 0 });
});

test("成功：原 payload 原樣保留（空陣列仍是成功，由區塊判斷真空態）", async () => {
  respond(() => new Response(JSON.stringify({ items: [] }), { status: 200 }));
  const r = await settle(fetchApiJson<{ items: unknown[] }>("http://api", "/empty"));
  assert.deepEqual(r, { ok: true, data: { items: [] } });
  assert.equal(failed(r), false);
});

test("settle 只吸收 ApiError；其他例外（頁面程式錯誤）照常拋出", async () => {
  const bug = new RangeError("render bug");
  await assert.rejects(settle(Promise.reject(bug)), (e) => e === bug);
  const r = await settle(Promise.reject(new ApiError("/p", 502)));
  assert.deepEqual(r, { ok: false, failure: "http", status: 502 });
});

test("所有伺服器 API 取用都是 no-store＋逾時訊號，不帶 next.revalidate", async () => {
  const calls = respond(() => new Response("{}", { status: 200 }));
  await Promise.all([
    api.records(), api.franchises(), api.championships(), api.postseason(), api.teamRecords(),
    api.seasons("A"), api.officialStandings(0), api.battingLeaders("ops"), api.pitchingLeaders("era"),
    api.venues(), api.venueFactors("洲際"), api.teamEras("AAA011"), api.outcomeBenchmark(),
    api.postseasonSummary(2025, "A"), api.gamesCalendar(2025, "D"), api.dailySummary(), api.pregameBacktest(),
  ]);
  assert.equal(calls.length, 17);
  for (const c of calls) {
    assert.equal(c.init.cache, "no-store", c.url);
    assert.equal(c.init.next, undefined, c.url);
    assert.ok(c.init.signal instanceof AbortSignal, `${c.url} 要有逾時訊號`);
  }
});

test("恢復：同一路徑失敗後下一次呼叫重新請求並取得新值（本層不保存失敗）", async () => {
  let up = false;
  const calls = respond(() => up
    ? new Response(JSON.stringify({ records: [{ label: "恢復值" }] }), { status: 200 })
    : new Response("{}", { status: 500 }));
  const down = await settle(api.teamRecords());
  assert.equal(failed(down), true);
  up = true;
  const back = await settle(api.teamRecords());
  assert.deepEqual(dataOf(back), { records: [{ label: "恢復值" }] });
  assert.equal(calls.length, 2);
});

test("api 方法失敗時拋帶分類的 ApiError（不是裸 TypeError），頁面才能 settle", async () => {
  respond(() => { throw new TypeError("fetch failed"); });
  await assert.rejects(api.records(), (e) => e instanceof ApiError && e.failure === "network");
});

test("區塊文案固定格式，不含內部細節", () => {
  assert.equal(unavailableCopy("紀錄集錦"), "紀錄集錦資料暫時無法取得，請稍後重新整理。");
});
