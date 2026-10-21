import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { AREA_FRAME_CLASS, AreaFrame } from "./area-frame.tsx";
import { PLAYOFFS_AREAS } from "./area-registry.ts";
import { PageNotes } from "./page-notes.tsx";
import { PLAYOFFS_LIVE_CLASS, PlayoffsLive } from "./playoffs-live.tsx";
import type { AreaRegistration } from "@/lib/playoffs-areas";
import type { PlayoffsOverview } from "@/lib/playoffs-types";

// #285 續做 WP2：區塊順序、錨點外框、空 registry、頁尾說明與疊層保證（PLAN r6 §4 WP2；MOUNT-CONTRACT r3 §1–§4）。
// 假區元件與假說明只在測試（契約：⛔ 在 registry 或 PAGE_NOTES 放正式內容）。

const REAL = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");
const ids = (s: string) => [...s.matchAll(/<(?:section|div) id="(series|watch|roster|teams)"/g)].map((m) => m[1]);

type Fake = { context_version: string; label: string };
const FakeSection = (name: string) => function Fake({ data }: { data: Fake | null }) {
  return <section aria-labelledby={`${name}-h`}><h2 id={`${name}-h`}>假區 {name}</h2><p>{data ? data.label : "假區讀取失敗"}</p></section>;
};
const fake = (id: "roster" | "teams", notes?: AreaRegistration<Fake>["notes"]): AreaRegistration<Fake> => ({
  id, path: (y, s) => `/api/v1/playoffs/${id}-fake?season=${y}&series=${s}`, Section: FakeSection(id), refresh: "every_round", notes,
});

test("空 registry：只有 #series、#watch，無 #roster／#teams；頁尾只含第 1／4 區說明、無第 2／3 區（需求方 W2）", () => {
  const out = html(<PlayoffsLive initial={REAL} year={2026} game={null} areas={[]} />);
  assert.deepEqual(ids(out), ["series", "watch"]);
  assert.doesNotMatch(out, /id="(roster|teams)"/);
  const noteIds = [...out.matchAll(/<li id="note-([^"]+)"/g)].map((m) => m[1]);
  assert.ok(noteIds.every((k) => /^(series|watch)\./.test(k)), noteIds.join());
  assert.doesNotMatch(text(out), /待更新/);
});

test("C2：登記陣列順序顛倒，渲染仍為 series → watch → roster → teams；錨點外框帶同值 scroll-margin", () => {
  const out = html(<PlayoffsLive initial={REAL} year={2026} game={null} areas={[fake("teams"), fake("roster")]} />);
  assert.deepEqual(ids(out), ["series", "watch", "roster", "teams"]);
  for (const id of ["roster", "teams"]) {
    const tag = new RegExp(`<div id="${id}" class="([^"]+)"`).exec(out)![1];
    assert.match(tag, /scroll-mt-\[70px\] md:scroll-mt-\[76px\]/);
  }
  // 首次取得前只有占位，區元件與區資料都不在首屏
  assert.doesNotMatch(out, /假區 roster|假區 teams/);
  assert.equal((out.match(/data-area-state="idle"/g) ?? []).length, 2);
});

test("C1：只登記一區時另一區連錨點都不出現", () => {
  const out = html(<PlayoffsLive initial={REAL} year={2026} game={null} areas={[fake("teams")]} />);
  assert.deepEqual(ids(out), ["series", "watch", "teams"]);
});

test("頁尾說明：未載入時用 notes(null) 的說明、依 C2 排序、重複 common.* 只出一次、在所有區塊之後；主導覽整合 MainTabs 與 SeriesSwitch", () => {
  const out = html(<PlayoffsLive initial={REAL} year={2026} game={null} areas={[
    fake("teams", (d) => [{ key: "common.box_source", text: "共用說明" }, { key: "teams.fixed", text: "假第 2 區固定說明" },
      ...(d ? [{ key: "teams.dynamic", text: `依資料 ${d.label}` }] : [])]),
    fake("roster", () => [{ key: "roster.fixed", text: "假第 3 區固定說明" }, { key: "common.box_source", text: "共用說明" }]),
  ]} />);
  assert.match(out, /aria-label="季後賽分區"/);
  for (const label of ["系列賽", "觀戰重點", "系列賽名單", "隊伍表現"]) assert.match(out, new RegExp(`>${label}<`));
  const footer = /<section aria-labelledby="page-notes-heading"[\s\S]*?<\/section>/.exec(out)![0];
  assert.deepEqual([...footer.matchAll(/<li id="note-([^"]+)"/g)].map((m) => m[1]), ["roster.fixed", "common.box_source", "teams.fixed"]);
  assert.match(footer, /資料說明/);
  assert.doesNotMatch(footer, /依資料/);
  assert.ok(out.indexOf('id="teams"') < out.indexOf("page-notes-heading"));
});

test("AreaFrame：區元件固定為外框第一個子節點（不 remount）；stale／error 保留上一份並把提示放在之後", () => {
  const S = FakeSection("teams");
  const first = (s: string) => /^<div id="teams"[^>]*><section aria-labelledby="teams-h"/.test(s);
  const prev = { context_version: "v1", label: "上一份" };
  const data = html(<AreaFrame id="teams" state={{ kind: "data", data: { context_version: "v2", label: "新" } }} Section={S} />);
  const stale = html(<AreaFrame id="teams" state={{ kind: "stale", previous: prev }} Section={S} />);
  const err = html(<AreaFrame id="teams" state={{ kind: "error", previous: prev }} Section={S} />);
  const errNone = html(<AreaFrame id="teams" state={{ kind: "error", previous: null }} Section={S} />);
  for (const s of [data, stale, err, errNone]) assert.ok(first(s), s.slice(0, 120));
  assert.match(text(stale), /上一份.*資料更新中，暫時顯示上一份一致的內容/);
  assert.match(text(err), /上一份.*最新資料暫時無法取得/);
  assert.match(text(errNone), /假區讀取失敗/);
  const idleStale = html(<AreaFrame id="teams" state={{ kind: "stale", previous: null }} Section={S} />);
  assert.match(text(idleStale), /^資料更新中$/);
  assert.match(html(<AreaFrame id="teams" state={{ kind: "idle" }} Section={S} minHeightPx={480} />), /min-height:480px/);
});

test("頁尾說明元件：0 條不渲染；來源連結只收站內或官方 https", () => {
  assert.equal(html(<PageNotes notes={[]} />), "");
  const out = html(<PageNotes notes={[
    { key: "teams.a", text: "甲", source: { label: "官方", url: "https://www.cpbl.com.tw/x" } },
    { key: "teams.b", text: "乙", source: { label: "外站", url: "https://evil.com/" } },
  ]} />);
  assert.match(out, /<li id="note-teams.a">甲（<a href="https:\/\/www.cpbl.com.tw\/x"/);
  assert.doesNotMatch(out, /evil\.com/);
  assert.match(out, /<li id="note-teams.b">乙<\/li>/);
});

test("疊層保證：外框與外殼 className 不含困住 position: fixed 的樣式", () => {
  for (const cls of [AREA_FRAME_CLASS, PLAYOFFS_LIVE_CLASS]) {
    assert.doesNotMatch(cls, /\b(transform|filter|contain|overflow-hidden|overflow-x-hidden|overflow-y-hidden|backdrop-|will-change|perspective)/, cls);
  }
});
