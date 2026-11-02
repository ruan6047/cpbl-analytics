import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import type { StatRow } from "@/lib/client";
import { SeasonTrendCard } from "./trend.tsx";

// #318：SeasonTrendCard 依預設指標（打者 OPS+、投手 ERA+）的點數切換呈現。
// 夾具為正式站真實回應（見 season-trend.test.ts）。recharts 在 SSR 只輸出容器，故此處只驗分支與文字。
const load = (name: string): StatRow[] =>
  JSON.parse(readFileSync(new URL(`./__fixtures__/trend-${name}.json`, import.meta.url), "utf8")).items;

const text = (html: string) => html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ");

test("石翔宇（OPS+ 0 點）：改列說明＋本季摘要＋逐場小表，不畫圖", () => {
  const html = renderToStaticMarkup(<SeasonTrendCard trend={load("shixiangyu")} role="batting" isRetired={false} />);
  assert.match(html, /data-testid="season-game-log"/);
  assert.match(html, /height:220px/);
  assert.doesNotMatch(html, /recharts-responsive-container/);
  const t = text(html);
  assert.match(t, /OPS\+ 以近 15 場滾動計算，目前可畫的點不足 2 個/);
  assert.match(t, /本季 11 場（4\/11–10\/4） · 安打 2 · 全壘打 0 · 打點 5/);
  // 表頭與 11 列逐場（新到舊）
  assert.match(t, /日期安打全壘打打點/);
  assert.equal((html.match(/<tr/g) ?? []).length, 1 + 11);
  assert.ok(t.indexOf("10/4") < t.indexOf("4/11", t.indexOf("日期")));
  assert.doesNotMatch(t, /出賽太少|樣本不足/);
});

test("謝榮豪（ERA+ 1 點）：投手欄位為三振／被安打／四壞", () => {
  const t = text(renderToStaticMarkup(<SeasonTrendCard trend={load("xierounghao")} role="pitching" isRetired={false} />));
  assert.match(t, /ERA\+ 以近 15 場滾動計算/);
  assert.match(t, /本季 12 場（4\/22–10\/5） · 三振 5 · 被安打 12 · 四壞 7/);
  assert.match(t, /日期三振被安打四壞/);
});

test("足量對照（郭天信、陳冠偉）：維持原折線分支，不出現逐場紀錄", () => {
  for (const [name, role] of [["guotianxin", "batting"], ["chenguanwei", "pitching"]] as const) {
    const html = renderToStaticMarkup(<SeasonTrendCard trend={load(name)} role={role} isRetired={false} />);
    assert.match(html, /recharts-responsive-container/, name);
    assert.doesNotMatch(html, /season-game-log/, name);
    assert.doesNotMatch(html, /<table/, name);
  }
});

test("載入中與無出賽列：沿用原狀態，不進逐場紀錄", () => {
  const loading = text(renderToStaticMarkup(<SeasonTrendCard trend={null} role="batting" isRetired={false} />));
  assert.match(loading, /載入中…/);
  const empty = text(renderToStaticMarkup(<SeasonTrendCard trend={[]} role="batting" isRetired={false} />));
  assert.match(empty, /本季尚無足夠出賽場次可繪製走勢。/);
  const retired = text(renderToStaticMarkup(<SeasonTrendCard trend={[]} role="pitching" isRetired />));
  assert.match(retired, /本季無出賽紀錄（已退役／轉任教練）/);
});
