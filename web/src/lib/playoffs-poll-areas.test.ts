import assert from "node:assert/strict";
import test from "node:test";

import { PlayoffsPoller, areaDecision, type AreaRefresh, type VersionedArea, type WatchState } from "./playoffs-poll.ts";

// #285 續做 WP1：第 2／3 區（registry 登記的區）在共用輪詢控制器中的行為（PLAN r6 §4 WP1 ②–⑦）。
// ① 由既有 playoffs-poll.test.ts 不改即通過負責。

type O = { context_version: string; default_series: string; sections: { watch: { status: string; series: string; game: number | null } } };
type W = { context_version: string; status: string };
type A = VersionedArea & { tag: string };

const ov = (v: string): O => ({ context_version: v, default_series: "C", sections: { watch: { status: "ok", series: "C", game: 1 } } });
const ar = (v: string | null, tag = String(v)): A => ({ context_version: v, tag });

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

type Call = { kind: string; series?: string; signal: AbortSignal; d: ReturnType<typeof deferred<unknown>> };

function harness(areas: { id: string; refresh: AreaRefresh }[], opts: { watch?: boolean } = {}) {
  const timers: { fn: () => void; ms: number; id: number }[] = [];
  let nextId = 0;
  const calls: Call[] = [];
  const shown = { overview: [] as string[], watch: [] as WatchState<W>[], area: {} as Record<string, WatchState<VersionedArea>[]>, rounds: [] as { ok: boolean; overviewOk: boolean }[] };
  let visible = true;
  const mk = (kind: string, series?: string) => (signal: AbortSignal) => {
    const d = deferred<unknown>(); calls.push({ kind, series, signal, d }); return d.promise;
  };
  const poller = new PlayoffsPoller<O, W>({
    fetchOverview: (signal) => mk("overview")(signal) as Promise<O>,
    fetchWatch: opts.watch === false ? undefined : (_t, signal) => mk("watch")(signal) as Promise<W>,
    areas: areas.map((a) => ({ ...a, fetch: (series: string, signal: AbortSignal) => mk(a.id, series)(signal) as Promise<A> })),
    isVisible: () => visible,
    setTimer: (fn, ms) => { const id = ++nextId; timers.push({ fn, ms, id }); return id; },
    clearTimer: (h) => { const i = timers.findIndex((t) => t.id === h); if (i >= 0) timers.splice(i, 1); },
    onOverview: (o) => shown.overview.push(o.context_version),
    onWatch: (s) => shown.watch.push(s),
    onArea: (id, s) => { (shown.area[id] ??= []).push(s); },
    onRound: (r) => shown.rounds.push({ ok: r.ok, overviewOk: r.overviewOk }),
  });
  const pending = (kind: string) => calls.filter((c) => c.kind === kind);
  const last = (kind: string) => pending(kind).at(-1)!;
  return {
    poller, calls, shown, timers, last, pending,
    setVisible: (v: boolean) => { visible = v; poller.visibilityChanged(); },
    fire: async () => { const t = timers.shift(); assert.ok(t); t.fn(); await flush(); },
    /** 依序回應：overview → watch（版本同 v）。 */
    answerRound: async (v: string) => {
      last("overview").d.resolve(ov(v)); await flush();
      last("watch").d.resolve({ context_version: v, status: "ok" }); await flush();
    },
  };
}

const kinds = (calls: Call[]) => calls.map((c) => c.kind);

test("② activate 前該區請求數 0；啟用後立即一輪，順序 overview → watch → 區", async () => {
  const h = harness([{ id: "roster", refresh: "every_round" }]);
  h.poller.start(true);
  await h.answerRound("v1");
  await h.fire();
  await h.answerRound("v1");
  assert.equal(h.pending("roster").length, 0);
  h.poller.activate("roster");
  await flush();
  assert.deepEqual(kinds(h.calls).slice(-1), ["overview"]);
  await h.answerRound("v1");
  assert.deepEqual(kinds(h.calls).slice(-3), ["overview", "watch", "roster"]);
  assert.equal(h.last("roster").series, "C");
  h.last("roster").d.resolve(ar("v1", "r1"));
  await flush();
  assert.deepEqual(h.shown.area.roster.map((s) => s.kind), ["data"]);
});

test("同一 microtask 內兩區啟用只跑一輪", async () => {
  const h = harness([{ id: "roster", refresh: "every_round" }, { id: "teams", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("roster");
  h.poller.activate("teams");
  h.poller.activate("roster");
  await flush();
  assert.equal(h.pending("overview").length, 1);
  await h.answerRound("v1");
  assert.equal(h.pending("roster").length, 1);
  assert.equal(h.pending("teams").length, 1);
});

test("③ every_round 每輪重取；on_context_change 只在 context_version 變時重取", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }, { id: "roster", refresh: "on_context_change" }]);
  h.poller.start(false);
  h.poller.activate("teams");
  h.poller.activate("roster");
  await flush();
  await h.answerRound("v1");
  h.last("teams").d.resolve(ar("v1")); h.last("roster").d.resolve(ar("v1"));
  await flush();
  await h.fire();
  await h.answerRound("v1");
  assert.equal(h.pending("teams").length, 2);
  assert.equal(h.pending("roster").length, 1);   // 版本沒變：不重取
  h.last("teams").d.resolve(ar("v1"));
  await flush();
  await h.fire();
  await h.answerRound("v2");
  assert.equal(h.pending("teams").length, 3);
  assert.equal(h.pending("roster").length, 2);   // 版本變了：重取
});

test("④ 區版本不一致 ⇒ 重取 overview 一次 ⇒ 重取該區一次 ⇒ 一致即接受", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("teams");
  await flush();
  await h.answerRound("v1");
  h.last("teams").d.resolve(ar("v2", "newer"));
  await flush();
  assert.deepEqual(kinds(h.calls), ["overview", "watch", "teams", "overview"]);
  h.last("overview").d.resolve(ov("v2"));
  await flush();
  assert.deepEqual(kinds(h.calls), ["overview", "watch", "teams", "overview", "teams"]);
  h.last("teams").d.resolve(ar("v2", "ok"));
  await flush();
  assert.deepEqual(h.shown.overview, ["v1", "v2"]);
  assert.deepEqual(h.shown.area.teams.map((s) => s.kind), ["data"]);
  assert.equal((h.shown.area.teams[0] as unknown as { data: A }).data.tag, "ok");
});

test("④ 重取後仍不一致 ⇒ stale 保留上一份；兩區同時錯版只重取 overview 一次", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }, { id: "roster", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("teams"); h.poller.activate("roster");
  await flush();
  await h.answerRound("v1");
  h.last("teams").d.resolve(ar("v1", "good-t")); h.last("roster").d.resolve(ar("v1", "good-r"));
  await flush();
  await h.fire();
  await h.answerRound("v1");
  h.last("teams").d.resolve(ar("vX")); h.last("roster").d.resolve(ar("vY"));
  await flush();
  assert.equal(h.pending("overview").length, 3);              // 第 2 輪 1 次＋共用重取 1 次
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  h.last("teams").d.resolve(ar("vX")); h.last("roster").d.resolve(ar("vY"));
  await flush();
  for (const id of ["teams", "roster"]) {
    const s = h.shown.area[id].at(-1)!;
    assert.equal(s.kind, "stale");
    assert.equal((s as unknown as { previous: A }).previous.tag, `good-${id[0]}`);
    assert.ok(!h.shown.area[id].some((x) => x.kind === "data" && x.data.context_version !== "v1"));
  }
});

test("⑤ 一區失敗只改該區（error＋上一份），不影響其他區、第 1 區提示與退避", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }, { id: "roster", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("teams"); h.poller.activate("roster");
  await flush();
  await h.answerRound("v1");
  h.last("teams").d.resolve(ar("v1", "t1")); h.last("roster").d.resolve(ar("v1", "r1"));
  await flush();
  await h.fire();
  await h.answerRound("v1");
  h.last("teams").d.reject(new Error("503")); h.last("roster").d.resolve(ar("v1", "r2"));
  await flush();
  const t = h.shown.area.teams.at(-1)!;
  assert.equal(t.kind, "error");
  assert.equal((t as unknown as { previous: A }).previous.tag, "t1");
  assert.equal((h.shown.area.roster.at(-1) as unknown as { data: A }).data.tag, "r2");
  assert.deepEqual(h.shown.rounds.at(-1), { ok: true, overviewOk: true });
  assert.equal(h.poller.failureCount, 0);
});

test("⑥ 新一輪開始時上一輪各區請求被 abort，晚到回應丟棄", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }, { id: "roster", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("teams"); h.poller.activate("roster");
  await flush();
  await h.answerRound("v1");
  const oldT = h.last("teams"), oldR = h.last("roster");
  await h.fire();                                   // 30 秒到：上一輪區請求還沒回
  assert.equal(oldT.signal.aborted, true);
  assert.equal(oldR.signal.aborted, true);
  await h.answerRound("v1");
  h.last("teams").d.resolve(ar("v1", "new-t")); h.last("roster").d.resolve(ar("v1", "new-r"));
  await flush();
  oldT.d.resolve(ar("v1", "old-t")); oldR.d.resolve(ar("v1", "old-r"));
  await flush();
  assert.deepEqual(h.shown.area.teams.map((s) => s.kind === "data" ? (s.data as A).tag : s.kind), ["new-t"]);
  assert.deepEqual(h.shown.area.roster.map((s) => s.kind === "data" ? (s.data as A).tag : s.kind), ["new-r"]);
});

test("⑦ 隱藏不排程、區請求中止；回前景立即一輪（含已啟用的區）", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("teams");
  await flush();
  await h.answerRound("v1");
  const t = h.last("teams");
  h.setVisible(false);
  assert.equal(t.signal.aborted, true);
  assert.equal(h.timers.length, 0);
  const n = h.calls.length;
  h.poller.activate("roster");                      // 未登記的 id：無效果
  await flush();
  assert.equal(h.calls.length, n);
  h.setVisible(true);
  await h.answerRound("v1");
  assert.deepEqual(kinds(h.calls).slice(-3), ["overview", "watch", "teams"]);
});

test("沒有第 4 區（fetchWatch 未給）時區照常；areaDecision 不看區層級 status", async () => {
  const h = harness([{ id: "teams", refresh: "every_round" }], { watch: false });
  h.poller.start(false);
  h.poller.activate("teams");
  await flush();
  h.last("overview").d.resolve(ov("v1"));
  await flush();
  assert.deepEqual(kinds(h.calls), ["overview", "teams"]);
  assert.equal(areaDecision("v1", { context_version: "v1" }, { retried: false }), "accept");
  assert.equal(areaDecision("v1", { context_version: null }, { retried: false }), "refetch_overview");
  assert.equal(areaDecision("v1", { context_version: "v2" }, { retried: true }), "keep_previous");
});

test("審核 F1：一區跨輪未回，另一區照常即時上畫面；第 1／4 區不退避、間隔維持 30 秒", async () => {
  const h = harness([{ id: "roster", refresh: "every_round" }, { id: "teams", refresh: "every_round" }]);
  h.poller.start(false);
  h.poller.activate("roster"); h.poller.activate("teams");
  await flush();
  const delays: number[] = [];
  const stuck: Call[] = [];
  for (let round = 1; round <= 4; round++) {
    await h.answerRound("v1");
    stuck.push(h.last("roster"));                     // roster 永遠不回
    h.last("teams").d.resolve(ar("v1", `t${round}`));
    await flush();
    // 正常區不等慢區：本輪 teams 立即上畫面
    const t = h.shown.area.teams.at(-1)!;
    assert.equal(t.kind, "data");
    assert.equal((t as unknown as { data: A }).data.tag, `t${round}`);
    assert.deepEqual(h.shown.rounds.at(-1), { ok: true, overviewOk: true });
    delays.push(h.timers[0].ms);
    await h.fire();                                   // 下一輪：慢區請求被中止、不計失敗
    assert.equal(stuck.at(-1)!.signal.aborted, true);
    assert.equal(h.poller.failureCount, 0);
  }
  assert.deepEqual(delays, [30_000, 30_000, 30_000, 30_000]);
  assert.equal(h.shown.area.roster, undefined);       // 慢區從未回應：維持占位，不被標成錯誤
});
