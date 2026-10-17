import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { SeriesSection } from "@/components/playoffs/series-section";
import { PlayoffsLive } from "@/components/playoffs/playoffs-live";
import { isAllowedSourceUrl } from "./playoffs-notes.ts";
import { SERIES_COPY, seriesNotes } from "./playoffs-series-view.ts";
import type { PlayoffsOverview } from "./playoffs-types.ts";

// #285 批次 C WP-C1：第 1 區既有就地說明搬到頁尾（6194706200；PLAN plan-4 §2.1 S1–S3）。
// 一律注入 `areas`（6205544611：⛔ 斷言正式 registry 內容）。

const REAL = JSON.parse(readFileSync(new URL("./__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const clone = (): PlayoffsOverview => structuredClone(REAL);
const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");
const LONG = ["比分以本站已同步的為準", "公告）"];

test("seriesNotes：null 或 covered ⇒ 空陣列（正常狀態無頁尾免責小字）；官方連結白名單照常", () => {
  assert.deepEqual(seriesNotes(null), []);
  assert.deepEqual(seriesNotes(REAL), []);
  assert.ok(isAllowedSourceUrl(REAL.schedule_source!.url));
});

test("seriesNotes：pending_update／unknown 各出動態說明；⛔ common.*", () => {
  const p = clone(); p.coverage = "pending_update";
  assert.deepEqual(seriesNotes(p).map((x) => [x.key, x.text]), [
    ["series.coverage_pending_update", "最新完賽結果更新中，比分以本站已同步的為準。"],
  ]);
  const u = clone(); u.coverage = "unknown"; u.schedule_source = null;
  assert.deepEqual(seriesNotes(u).map((x) => [x.key, x.text]), [["series.coverage_unknown", "本站資料完整度未知，比分以本站已同步的為準。"]]);
  for (const o of [REAL, p, u]) for (const x of seriesNotes(o)) assert.match(x.key, /^series\.[a-z_]+$/);
});

test("SeriesSection 格內只留短狀態，三句說明原文都不在第 1 區", () => {
  for (const cov of ["covered", "pending_update", "unknown"] as const) {
    const o = clone(); o.coverage = cov;
    const t = text(html(<SeriesSection overview={o} />));
    for (const s of LONG) assert.ok(!t.includes(s), `${cov}: ${s}`);
    if (cov === "pending_update") assert.match(t, new RegExp(SERIES_COPY.pendingUpdate));
    if (cov === "unknown") assert.match(t, new RegExp(SERIES_COPY.coverageUnknown));
  }
});

test("PlayoffsLive 頁尾：series 群組依序 seriesNotes → #288 seriesSummaryNotes；頁尾在所有區塊之後", () => {
  const o = clone(); o.coverage = "pending_update";
  o.series_summary = { contract: "x", algorithm: "x", current: null, previous: null } as never;   // 無累計榜 ⇒ #288 無條目
  const out = html(<PlayoffsLive initial={o} year={2026} game={null} areas={[]} />);
  const ids = [...out.matchAll(/<li id="note-([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, ["series.coverage_pending_update"]);
  // 頁尾在所有區塊之後
  assert.ok(out.indexOf('id="watch"') < out.indexOf("page-notes-heading"));
});
