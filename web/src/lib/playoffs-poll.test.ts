import assert from "node:assert/strict";
import test from "node:test";

import { BACKOFF_MS, POLL_INTERVAL_MS, PlayoffsPoller, nextDelay, watchDecision, type WatchState } from "./playoffs-poll.ts";

type O = { context_version: string; sections: { watch: { status: string; series: string; game: number | null } }; tag: string };
type W = { context_version: string; status: string; tag: string };

const ov = (v: string, game: number | null = 1, tag = v): O => ({ context_version: v, sections: { watch: { status: game ? "ok" : "no_target", series: "C", game } }, tag });
const wt = (v: string, status = "ok", tag = v): W => ({ context_version: v, status, tag });

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

/** 可控的時鐘、可見性與取數；記錄每一次請求與回呼。 */
function harness(opts: { watch?: boolean; game?: number | null } = {}) {
  const timers: { fn: () => void; ms: number; id: number }[] = [];
  let nextId = 0;
  const calls: { kind: "overview" | "watch"; game?: number; signal: AbortSignal; d: ReturnType<typeof deferred<O | W>> }[] = [];
  const shown: { overview: string[]; watch: WatchState<W>[]; rounds: { ok: boolean; overviewOk: boolean }[] } = { overview: [], watch: [], rounds: [] };
  let visible = true;
  const poller = new PlayoffsPoller<O, W>({
    fetchOverview: (signal) => { const d = deferred<O | W>(); calls.push({ kind: "overview", signal, d }); return d.promise as Promise<O>; },
    fetchWatch: opts.watch === false ? undefined : (t, signal) => { const d = deferred<O | W>(); calls.push({ kind: "watch", game: t.game, signal, d }); return d.promise as Promise<W>; },
    isVisible: () => visible,
    setTimer: (fn, ms) => { const id = ++nextId; timers.push({ fn, ms, id }); return id; },
    clearTimer: (h) => { const i = timers.findIndex((t) => t.id === h); if (i >= 0) timers.splice(i, 1); },
    onOverview: (o) => shown.overview.push(o.tag),
    onWatch: (s) => shown.watch.push(s),
    onRound: (r) => shown.rounds.push({ ok: r.ok, overviewOk: r.overviewOk }),
  }, opts.game ?? null);
  return {
    poller, calls, shown, timers,
    setVisible: (v: boolean) => { visible = v; poller.visibilityChanged(); },
    fire: async () => { const t = timers.shift(); assert.ok(t, "沒有排程中的計時器"); t.fn(); await flush(); return t.ms; },
    last: (kind: "overview" | "watch") => [...calls].reverse().find((c) => c.kind === kind)!,
  };
}

test("間隔一律 30 秒；退避 30→60→120→240 封頂", () => {
  assert.equal(POLL_INTERVAL_MS, 30_000);
  assert.deepEqual([0, 1, 2, 3, 4, 9].map(nextDelay), [30_000, 60_000, 120_000, 240_000, 240_000, 240_000]);
  assert.deepEqual([...BACKOFF_MS], [30_000, 60_000, 120_000, 240_000]);
});

test("SSR 已給 overview：不立即取，30 秒後第一輪；只上第 1 區時 watch 請求數 0", async () => {
  const h = harness({ watch: false });
  h.poller.start(false);
  assert.equal(h.calls.length, 0);
  assert.equal(await h.fire(), 30_000);
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  assert.deepEqual(h.shown.overview, ["v1"]);
  assert.equal(h.calls.filter((c) => c.kind === "watch").length, 0);
  assert.equal(h.timers.length, 1);
  assert.equal(h.timers[0].ms, 30_000);
});

test("隱藏即停（中止進行中、無排程）；回前景立即一輪", async () => {
  const h = harness({ watch: false });
  h.poller.start(true);
  const first = h.last("overview");
  h.setVisible(false);
  assert.equal(first.signal.aborted, true);
  assert.equal(h.timers.length, 0);
  first.d.resolve(ov("late"));
  await flush();
  assert.deepEqual(h.shown.overview, []);           // 中止後晚到的回應不上畫面
  h.setVisible(true);
  assert.equal(h.calls.length, 2);                  // 立即一輪
  h.last("overview").d.resolve(ov("v2"));
  await flush();
  assert.deepEqual(h.shown.overview, ["v2"]);
});

test("失敗退避：連續失敗間隔拉長，成功歸零", async () => {
  const h = harness({ watch: false });
  h.poller.start(true);
  const delays: number[] = [];
  for (let i = 0; i < 4; i++) {
    h.last("overview").d.reject(new Error("503"));
    await flush();
    assert.equal(h.timers.length, 1);
    delays.push(h.timers[0].ms);
    await h.fire();
  }
  assert.deepEqual(delays, [60_000, 120_000, 240_000, 240_000]);
  h.last("overview").d.resolve(ov("ok"));
  await flush();
  assert.equal(h.poller.failureCount, 0);
  assert.equal(h.timers[0].ms, 240_000);            // 本輪開始時已排程；下一輪起回到 30 秒
  await h.fire();
  assert.equal(h.timers[0].ms, 30_000);
});

test("輪詢重疊：上一輪 30 秒內沒回來 ⇒ 被中止、晚到回應不上畫面、退避", async () => {
  const h = harness({ watch: false });
  h.poller.start(true);
  const slow = h.last("overview");
  await h.fire();                                   // 30 秒到，下一輪開始
  assert.equal(slow.signal.aborted, true);
  assert.equal(h.poller.failureCount, 1);
  const fresh = h.last("overview");
  fresh.d.resolve(ov("new"));
  await flush();
  slow.d.resolve(ov("old"));                        // 舊輪晚到
  await flush();
  assert.deepEqual(h.shown.overview, ["new"]);
});

test("每輪先 overview 再 watch；版本一致即接受", async () => {
  const h = harness();
  h.poller.start(true);
  assert.deepEqual(h.calls.map((c) => c.kind), ["overview"]);
  h.last("overview").d.resolve(ov("v1", 1));
  await flush();
  assert.deepEqual(h.calls.map((c) => c.kind), ["overview", "watch"]);
  assert.equal(h.last("watch").game, 1);
  h.last("watch").d.resolve(wt("v1"));
  await flush();
  assert.deepEqual(h.shown.watch.map((s) => s.kind), ["data"]);
});

test("版本不一致 ⇒ 先重取 overview、再重取 watch；一致後接受", async () => {
  const h = harness();
  h.poller.start(true);
  h.last("overview").d.resolve(ov("v1", 1));
  await flush();
  h.last("watch").d.resolve(wt("v2"));              // watch 較新
  await flush();
  assert.deepEqual(h.calls.map((c) => c.kind), ["overview", "watch", "overview"]);
  h.last("overview").d.resolve(ov("v2", 2));         // 新 overview：目標換 C2
  await flush();
  assert.deepEqual(h.calls.map((c) => c.kind), ["overview", "watch", "overview", "watch"]);
  assert.equal(h.last("watch").game, 2);
  h.last("watch").d.resolve(wt("v2"));
  await flush();
  assert.deepEqual(h.shown.overview, ["v1", "v2"]);
  assert.deepEqual(h.shown.watch.map((s) => s.kind), ["data"]);
  assert.equal((h.shown.watch[0] as { data: W }).data.tag, "v2");
});

test("重取後仍不一致 ⇒ 保留上一份＋更新中，⛔ 接受錯版", async () => {
  const h = harness();
  h.poller.start(true);
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  h.last("watch").d.resolve(wt("v1", "ok", "good"));
  await flush();
  await h.fire();
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  h.last("watch").d.resolve(wt("v3"));
  await flush();
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  h.last("watch").d.resolve(wt("v3"));
  await flush();
  const lastState = h.shown.watch.at(-1)!;
  assert.equal(lastState.kind, "stale");
  assert.equal((lastState as { previous: W }).previous.tag, "good");
  assert.ok(!h.shown.watch.some((s) => s.kind === "data" && s.data.context_version === "v3"));
});

test("目標取自 overview 時 not_target 視為版本落差；使用者指定 ?game 時照接受", () => {
  assert.equal(watchDecision("v1", wt("v1", "not_target"), { requested: false, retried: false }), "refetch_overview");
  assert.equal(watchDecision("v1", wt("v1", "not_target"), { requested: true, retried: false }), "accept");
  assert.equal(watchDecision("v1", wt("v1", "historical_not_published"), { requested: true, retried: false }), "accept");
  assert.equal(watchDecision("v1", wt("v2"), { requested: true, retried: true }), "keep_previous");
});

test("?game 變更：舊 game 的延遲回應被丟棄，畫面只有新 game", async () => {
  const h = harness({ game: 1 });
  h.poller.start(true);
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  const oldWatch = h.last("watch");
  assert.equal(oldWatch.game, 1);
  h.poller.setGame(3);
  assert.equal(oldWatch.signal.aborted, true);
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  const newWatch = h.last("watch");
  assert.equal(newWatch.game, 3);
  oldWatch.d.resolve(wt("v1", "ok", "game1"));
  newWatch.d.resolve(wt("v1", "not_target", "game3"));
  await flush();
  assert.deepEqual(h.shown.watch.map((s) => s.kind === "data" ? s.data.tag : s.kind), ["game3"]);
  assert.equal(h.poller.failureCount, 0);           // 使用者切換不算失敗
});

test("watch 讀取失敗只標第 4 區錯誤、overview 照常上畫面", async () => {
  const h = harness();
  h.poller.start(true);
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  h.last("watch").d.reject(new Error("503"));
  await flush();
  assert.deepEqual(h.shown.overview, ["v1"]);
  assert.equal(h.shown.watch.at(-1)!.kind, "error");
  // 本輪算失敗（退避），但 overview 已上畫面：第 1 區不顯示「暫時無法更新」
  assert.deepEqual(h.shown.rounds.at(-1), { ok: false, overviewOk: true });
  await h.fire();
  h.last("overview").d.reject(new Error("503"));
  await flush();
  assert.deepEqual(h.shown.rounds.at(-1), { ok: false, overviewOk: false });
});

test("stop 後不再排程、晚到回應不上畫面", async () => {
  const h = harness({ watch: false });
  h.poller.start(true);
  const c = h.last("overview");
  h.poller.stop();
  c.d.resolve(ov("late"));
  await flush();
  assert.deepEqual(h.shown.overview, []);
  assert.equal(h.timers.length, 0);
});
