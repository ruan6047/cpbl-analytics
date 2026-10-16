import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { SeriesSection } from "./series-section.tsx";
import { SeriesSummaryBlock } from "./series-summary.tsx";
import type { SeriesSummary } from "@/lib/playoffs-series-summary";
import type { PlayoffsOverview } from "@/lib/playoffs-types";

// 真實樣本：#285 的 2026-10-15 overview＋本機唯讀取得的 2026-10-16 series_summary（E1–E4 4/4、C 未開打）。
const OVERVIEW = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const SUMMARY = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-series-summary_2026-10-16.json", import.meta.url), "utf8")) as SeriesSummary;
const sum = (): SeriesSummary => structuredClone(SUMMARY);

const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");

test("真實樣本：挑戰賽累計榜預設收合（details 無 open）、C 0 場整塊不渲染", () => {
  const out = html(<SeriesSummaryBlock summary={SUMMARY} />);
  assert.match(out, /<details[^>]*data-summary="E"/);
  assert.doesNotMatch(out, /<details[^>]*\bopen\b/);
  assert.doesNotMatch(out, /data-summary="C"/);
  const t = text(out);
  assert.match(t, /季後挑戰賽累計榜/);
  // 打者前 3、投手前 2（真實值；排序後端已定）
  for (const s of ["詹子賢", "PA 5", "相對局面得分期望，累計 +2.4 分", "江坤宇", "PA 17", "陳俊秀"]) assert.ok(t.includes(s), s);
  for (const s of ["喬登", "BF 24", "壓制貢獻，累計 +3.4 分", "獅帝芬", "BF 18", "壓制貢獻，累計 +3.0 分"]) assert.ok(t.includes(s), s);
  assert.equal((out.match(/<li[^>]*data-player=/g) ?? []).length, 5);
  // 官方單場 MVP 次數（含不在榜上的人）照常；本卡不顯示官方系列獎項（6217030580）
  for (const n of ["勝騎士", "鄭浩均"]) assert.match(t, new RegExp(`${n}×1`));
  assert.match(t, /單場 MVP ×1/);
  assert.doesNotMatch(t, /官方系列獎項|系列獎項/);
});

test("WP-CLEAN：API 仍帶 awards 欄（舊版相容）時照常渲染、不出現獎項格；MVP 次數格跨兩欄", () => {
  const raw = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-series-summary_2026-10-16.json", import.meta.url), "utf8"));
  assert.deepEqual(raw.previous.awards, { status: "pending_source" });   // fixture 是 16b64634 前的真實 payload
  const out = html(<SeriesSummaryBlock summary={raw as SeriesSummary} />);
  assert.doesNotMatch(text(out), /官方系列獎項/);
  assert.match(out, /<div class="min-w-0 md:col-span-2"><h4[^>]*>單場 MVP 次數<\/h4>/);
});

test("RE24 第一不稱 MVP；格內不放說明句（只有「—」「待更新」）", () => {
  const out = text(html(<SeriesSummaryBlock summary={SUMMARY} />));
  assert.doesNotMatch(out, /最有價值|系列 MVP|領先|第一名/);
  assert.doesNotMatch(out, /尚未送達|無法讀取|不完整/);
});

test("當前系列有完賽場：最下方展開（不在 details 內），前一系列仍收合在上方", () => {
  const s = sum();
  s.current = { ...structuredClone(s.previous!), kind_code: "C" };
  const out = html(<SeriesSummaryBlock summary={s} />);
  assert.match(out, /data-summary="E"[\s\S]*data-summary="C"/);
  assert.match(out, /<div[^>]*data-summary="C"[^>]*><h3[^>]*>台灣大賽累計榜<\/h3>/);
});

test("pending_pa／unavailable：榜格待更新，MVP 次數照常；空投手榜 ⇒ —", () => {
  const s = sum();
  Object.assign(s.previous!, { status: "pending_pa", games_covered: 0, batters: [], pitchers: [] });
  let t = text(html(<SeriesSummaryBlock summary={s} />));
  assert.equal((t.match(/待更新/g) ?? []).length, 2);   // 打者、投手（獎項格已拿掉）
  assert.match(t, /勝騎士×1/);
  Object.assign(s.previous!, { status: "partial", games_covered: 3, missing_games: [2], batters: SUMMARY.previous!.batters, pitchers: [] });
  t = text(html(<SeriesSummaryBlock summary={s} />));
  assert.match(t, /投手—/);
  assert.match(t, /詹子賢/);   // partial 照排
});

test("MVP 全缺 ⇒ 待更新；無缺也無次數 ⇒ —", () => {
  const s = sum();
  Object.assign(s.previous!, { mvp_counts: [], mvp_missing_games: [1, 2, 3, 4] });
  assert.match(text(html(<SeriesSummaryBlock summary={s} />)), /單場 MVP 次數待更新/);
  Object.assign(s.previous!, { mvp_missing_games: [] });
  assert.match(text(html(<SeriesSummaryBlock summary={s} />)), /單場 MVP 次數—/);
});

test("掛進第 1 區：在下一場預告之後；overview 沒有 series_summary 時第 1 區與既有輸出相同", () => {
  const with_ = { ...structuredClone(OVERVIEW), series_summary: SUMMARY };
  const out = html(<SeriesSection overview={with_} />);
  assert.match(out, /data-next-game[\s\S]*data-series-summary/);
  const plain = html(<SeriesSection overview={OVERVIEW} />);
  assert.doesNotMatch(plain, /data-series-summary/);
  assert.equal(html(<SeriesSection overview={{ ...structuredClone(OVERVIEW), series_summary: null }} />), plain);
});

test("觸控目標：列、收合鈕、單格皆 min-h-11（44px）", () => {
  const out = html(<SeriesSummaryBlock summary={SUMMARY} />);
  assert.match(out, /<summary class="[^"]*min-h-11/);
  for (const li of out.match(/<li[^>]*data-player=[^>]*>/g) ?? []) assert.match(li, /min-h-11/);
});
