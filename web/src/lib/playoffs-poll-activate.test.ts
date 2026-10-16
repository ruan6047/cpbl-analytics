import assert from "node:assert/strict";
import test from "node:test";

import { PlayoffsPoller, type AreaRefresh, type VersionedArea } from "./playoffs-poll.ts";

// #285 批次 B WP-F1（發現 1）：本輪進行中、尚未發出區請求時啟用的區併入本輪，⛔ 開新一輪；
// 以及 WP-S2：區的 series 取 overview `selected_series`（缺時退回 default_series → sections.watch.series）。
// 既有 activate 行為（沒有進行中的一輪時啟用 ⇒ microtask 合併後立即一輪）由 playoffs-poll-areas.test.ts 不改即通過負責。

type O = { context_version: string; selected_series?: string; default_series?: string;
  sections: { watch: { status: string; series: string; game: number | null } } };
type W = { context_version: string; status: string };

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
/** 一個 microtask checkpoint：瀏覽器在兩個 IntersectionObserver 回呼之間會跑完 microtask 佇列（plan-3 探針 §2.1）。 */
const checkpoint = flush;

type Call = { kind: string; series?: string; signal: AbortSignal; d: ReturnType<typeof deferred<unknown>> };

function harness(areas: { id: string; refresh: AreaRefresh }[]) {
  const timers: { fn: () => void; ms: number; id: number }[] = [];
  let nextId = 0;
  const calls: Call[] = [];
  const area: Record<string, string[]> = {};
  const mk = (kind: string, series?: string) => (signal: AbortSignal) => {
    const d = deferred<unknown>(); calls.push({ kind, series, signal, d }); return d.promise;
  };
  const poller = new PlayoffsPoller<O, W>({
    fetchOverview: (signal) => mk("overview")(signal) as Promise<O>,
    fetchWatch: (t, signal) => mk("watch", t.series)(signal) as Promise<W>,
    areas: areas.map((a) => ({ ...a, fetch: (series: string, signal: AbortSignal) => mk(a.id, series)(signal) as Promise<VersionedArea> })),
    isVisible: () => true,
    setTimer: (fn, ms) => { const id = ++nextId; timers.push({ fn, ms, id }); return id; },
    clearTimer: (h) => { const i = timers.findIndex((t) => t.id === h); if (i >= 0) timers.splice(i, 1); },
    onOverview: () => {},
    onArea: (id, s) => { (area[id] ??= []).push(s.kind); },
  });
  const of = (kind: string) => calls.filter((c) => c.kind === kind);
  const last = (kind: string) => of(kind).at(-1)!;
  return { poller, calls, of, last, area };
}

const ov = (v: string, extra: Partial<O> = {}): O =>
  ({ context_version: v, selected_series: "C", default_series: "C", sections: { watch: { status: "ok", series: "C", game: 1 } }, ...extra });

const AREAS = [{ id: "roster", refresh: "every_round" as const }, { id: "teams", refresh: "every_round" as const }];

test("首輪 overview 在路上時兩區先後啟用（中間隔 microtask checkpoint）⇒ overview 1、首輪不中止、兩區各 1", async () => {
  const h = harness(AREAS);
  h.poller.start(true);
  const first = h.last("overview");
  h.poller.activate("roster");
  await checkpoint();
  h.poller.activate("teams");
  await checkpoint();
  assert.equal(h.of("overview").length, 1);
  assert.equal(first.signal.aborted, false);
  first.d.resolve(ov("v1")); await flush();
  h.last("watch").d.resolve({ context_version: "v1", status: "ok" }); await flush();
  assert.equal(h.of("overview").length, 1);
  assert.equal(h.of("roster").length, 1);
  assert.equal(h.of("teams").length, 1);
  assert.ok(h.calls.every((c) => !c.signal.aborted));
  h.last("roster").d.resolve({ context_version: "v1" }); h.last("teams").d.resolve({ context_version: "v1" });
  await flush();
  assert.deepEqual(h.area, { roster: ["data"], teams: ["data"] });
});

test("第 4 區還在路上時啟用 ⇒ 仍併入本輪（區請求在 watch 之後才發）", async () => {
  const h = harness(AREAS);
  h.poller.start(true);
  h.last("overview").d.resolve(ov("v1")); await flush();
  assert.equal(h.of("watch").length, 1);
  h.poller.activate("roster");
  await checkpoint();
  assert.equal(h.of("overview").length, 1);
  h.last("watch").d.resolve({ context_version: "v1", status: "ok" }); await flush();
  assert.deepEqual(h.calls.map((c) => c.kind), ["overview", "watch", "roster"]);
});

test("本輪已發出區請求後才啟用 ⇒ 下一個 microtask 開新一輪並取到該區", async () => {
  const h = harness(AREAS);
  h.poller.start(false);
  h.poller.activate("roster");
  await flush();
  h.last("overview").d.resolve(ov("v1")); await flush();
  h.last("watch").d.resolve({ context_version: "v1", status: "ok" });
  // 本輪 round() 已進入 roundAreas（roster 已發），tick 的 finally 還沒清 inflight：此刻啟用 teams
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.equal(h.of("roster").length, 1);
  h.poller.activate("teams");
  await flush();
  assert.equal(h.of("overview").length, 2);   // 新一輪
  h.last("overview").d.resolve(ov("v1")); await flush();
  h.last("watch").d.resolve({ context_version: "v1", status: "ok" }); await flush();
  assert.equal(h.of("teams").length, 1);
});

test("round() 剛結束、inflight 尚未清空時啟用 ⇒ 不會漏取該區", async () => {
  // 逐個 microtask 推進，每一步都試著啟用：無論落在哪個間隙，teams 最終都會被取到一次以上，且只有一輪新的 overview
  for (let steps = 0; steps <= 8; steps++) {
    const h = harness(AREAS);
    h.poller.start(false);
    h.poller.activate("roster");
    await flush();
    h.last("overview").d.resolve(ov("v1")); await flush();
    h.last("watch").d.resolve({ context_version: "v1", status: "ok" });
    for (let i = 0; i < steps; i++) await Promise.resolve();
    h.poller.activate("teams");
    await flush();
    if (h.of("overview").length === 2) {
      h.last("overview").d.resolve(ov("v1")); await flush();
      h.last("watch").d.resolve({ context_version: "v1", status: "ok" }); await flush();
    }
    assert.ok(h.of("teams").length >= 1, `steps=${steps}`);
    assert.ok(h.of("overview").length <= 2, `steps=${steps}`);
  }
});

test("首輪 overview 失敗 ⇒ 併入的區不在本輪取，下一輪照常取（不另開一輪）", async () => {
  const h = harness(AREAS);
  h.poller.start(true);
  h.poller.activate("roster");
  await checkpoint();
  h.last("overview").d.reject(new Error("503")); await flush();
  assert.equal(h.of("roster").length, 0);
  assert.equal(h.of("overview").length, 1);
});

test("區的 series：selected_series → default_series → sections.watch.series", async () => {
  const cases: [Partial<O>, string][] = [
    [{ selected_series: "E", default_series: "C", sections: { watch: { status: "ok", series: "E", game: 4 } } }, "E"],
    [{ selected_series: undefined, default_series: "E" }, "E"],
    [{ selected_series: undefined, default_series: undefined, sections: { watch: { status: "ok", series: "E", game: 4 } } }, "E"],
  ];
  for (const [extra, want] of cases) {
    const h = harness([AREAS[0]]);
    h.poller.start(false);
    h.poller.activate("roster");
    await flush();
    h.last("overview").d.resolve(ov("v1", extra)); await flush();
    h.last("watch").d.resolve({ context_version: "v1", status: "ok" }); await flush();
    assert.equal(h.last("roster").series, want, JSON.stringify(extra));
  }
});
