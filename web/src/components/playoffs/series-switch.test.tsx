import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { PlayoffsLive } from "./playoffs-live.tsx";
import { SeriesSwitch } from "./series-switch.tsx";
import type { PlayoffsOverview } from "@/lib/playoffs-types";

// #285 批次 B WP-S2：系列切換（B2：第 1 區標題下「挑戰賽｜台灣大賽」）與外殼的系列來源。
// 一律注入 `areas`（6205544611：⛔ 斷言正式 registry 內容）。

const REAL = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const links = (s: string) => [...s.matchAll(/<a ([^>]*)>([\s\S]*?)<\/a>/g)]
  .filter((m) => /href="\/playoffs\?/.test(m[1]))
  .map((m) => ({ href: /href="([^"]+)"/.exec(m[1])![1].replaceAll("&amp;", "&"), current: /aria-current="page"/.test(m[1]), label: m[2].replace(/<[^>]+>/g, "") }));

test("兩個連結依序「挑戰賽」「台灣大賽」，所選者 aria-current＝page；保留 year、不帶 game", () => {
  assert.deepEqual(links(html(<SeriesSwitch selected="E" year={null} />)), [
    { href: "/playoffs?series=E", current: true, label: "挑戰賽" },
    { href: "/playoffs?series=C", current: false, label: "台灣大賽" },
  ]);
  assert.deepEqual(links(html(<SeriesSwitch selected="C" year={2025} />)).map((l) => [l.href, l.current]), [
    ["/playoffs?year=2025&series=E", false], ["/playoffs?year=2025&series=C", true]]);
  assert.ok(links(html(<SeriesSwitch selected={null} year={null} />)).every((l) => !l.current));
});

test("外殼：切換放在頁標題之後、第 1 區之前；所選系列取 overview selected_series", () => {
  const e = { ...REAL, selected_series: "E" as const };
  const out = html(<PlayoffsLive initial={e} year={2026} game={null} series="E" areas={[]} />);
  assert.ok(out.indexOf("<h1") < out.indexOf("data-series-switch"));
  assert.ok(out.indexOf("data-series-switch") < out.indexOf('id="series"'));
  assert.deepEqual(links(out).map((l) => [l.label, l.current]), [["挑戰賽", true], ["台灣大賽", false]]);
});

test("外殼：舊 API（無 selected_series）且網址未指定 ⇒ 依 default_series 標示", () => {
  const { selected_series: _drop, ...old } = { ...REAL, selected_series: undefined };
  const out = html(<PlayoffsLive initial={old as PlayoffsOverview} year={2026} game={null} areas={[]} />);
  assert.deepEqual(links(out).map((l) => [l.label, l.current]), [["挑戰賽", false], ["台灣大賽", true]]);
});

test("外殼：overview 讀取失敗仍可切換，所選依網址", () => {
  const out = html(<PlayoffsLive initial={null} year={2026} game={null} series="E" areas={[]} />);
  assert.deepEqual(links(out).map((l) => [l.label, l.current]), [["挑戰賽", true], ["台灣大賽", false]]);
});
