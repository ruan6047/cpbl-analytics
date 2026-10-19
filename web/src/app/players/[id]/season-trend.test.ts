import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { StatRow } from "@/lib/client";
import { BAT_METRICS, type Metric, PIT_METRICS } from "./lib.ts";
import {
  MIN_TREND_POINTS, gameLogMetrics, gameLogRows, gameLogSummary, showGameLog, trendPointCount,
} from "./season-trend.ts";

// #318：夾具是 2026-10-19 自正式站 `GET /api/v1/players/{id}/trend?role=…` 原樣存下的真實回應
// （石翔宇 0 點、謝榮豪 1 點、林柏佑 0 點、林家勝 ERA+ 1 點但 ERA 3 點、郭天信／陳冠偉足量對照）。
const load = (name: string): StatRow[] =>
  JSON.parse(readFileSync(new URL(`./__fixtures__/trend-${name}.json`, import.meta.url), "utf8")).items;

const bat = (k: string): Metric => BAT_METRICS.find((m) => m.key === k)!;
const pit = (k: string): Metric => PIT_METRICS.find((m) => m.key === k)!;

test("門檻：少於 2 點切換（0 點與 1 點都切），2 點起維持折線", () => {
  assert.equal(MIN_TREND_POINTS, 2);
  const row = (v: number | null): StatRow => ({ name: "x", date: "2026-04-01", ops_plus: v });
  const ops = bat("ops_plus");
  assert.equal(showGameLog([row(null), row(null)], ops), true);
  assert.equal(showGameLog([row(null), row(120)], ops), true);
  assert.equal(showGameLog([row(90), row(null), row(120)], ops), false);
});

test("無出賽列時不進逐場紀錄（沿用原空態）", () => {
  assert.equal(showGameLog([], bat("ops_plus")), false);
  assert.equal(showGameLog([], pit("era_plus")), false);
});

test("計數型指標永不切換（柱狀不受滾動門檻影響），即使全為 0", () => {
  const shi = load("shixiangyu");
  for (const k of ["hits", "home_runs", "rbi"]) assert.equal(showGameLog(shi, bat(k)), false, k);
  const lin = load("linboyou");
  for (const k of ["so", "hits", "bb"]) assert.equal(showGameLog(lin, pit(k)), false, k);
});

test("石翔宇（11 場、5 個比率指標皆 0 點）：每個滾動指標都切換", () => {
  const shi = load("shixiangyu");
  for (const k of ["ops_plus", "ops", "avg", "obp", "slg"]) {
    assert.equal(trendPointCount(shi, bat(k)), 0, k);
    assert.equal(showGameLog(shi, bat(k)), true, k);
  }
});

test("投手 0 點／1 點：林柏佑 0 點、謝榮豪 1 點皆切換", () => {
  const lin = load("linboyou"), xie = load("xierounghao");
  for (const k of ["era_plus", "era", "whip"]) {
    assert.equal(trendPointCount(lin, pit(k)), 0, `林柏佑 ${k}`);
    assert.equal(showGameLog(lin, pit(k)), true, `林柏佑 ${k}`);
    assert.equal(trendPointCount(xie, pit(k)), 1, `謝榮豪 ${k}`);
    assert.equal(showGameLog(xie, pit(k)), true, `謝榮豪 ${k}`);
  }
});

test("以所選指標判斷：林家勝 ERA+ 1 點切換，ERA／WHIP 3 點維持折線", () => {
  const ljs = load("linjiasheng");
  assert.equal(trendPointCount(ljs, pit("era_plus")), 1);
  assert.equal(showGameLog(ljs, pit("era_plus")), true);
  assert.equal(trendPointCount(ljs, pit("era")), 3);
  assert.equal(showGameLog(ljs, pit("era")), false);
  assert.equal(showGameLog(ljs, pit("whip")), false);
});

test("足量對照：郭天信、陳冠偉所有指標都不切換", () => {
  const guo = load("guotianxin"), chen = load("chenguanwei");
  for (const m of BAT_METRICS) assert.equal(showGameLog(guo, m), false, `郭天信 ${m.key}`);
  for (const m of PIT_METRICS) assert.equal(showGameLog(chen, m), false, `陳冠偉 ${m.key}`);
  assert.equal(trendPointCount(guo, bat("ops_plus")), 112);
  assert.equal(trendPointCount(chen, pit("era_plus")), 46);
});

test("逐場欄位＝該 role 的計數型指標，與下拉同源", () => {
  assert.deepEqual(gameLogMetrics("batting").map((m) => m.label), ["安打", "全壘打", "打點"]);
  assert.deepEqual(gameLogMetrics("pitching").map((m) => m.label), ["三振", "被安打", "四壞"]);
});

test("本季累計摘要：真實資料加總與日期範圍", () => {
  assert.deepEqual(gameLogSummary(load("shixiangyu"), "batting"), {
    games: 11, first: "4/11", last: "10/4",
    totals: [
      { key: "hits", label: "安打", value: 2 },
      { key: "home_runs", label: "全壘打", value: 0 },
      { key: "rbi", label: "打點", value: 5 },
    ],
  });
  assert.deepEqual(gameLogSummary(load("xierounghao"), "pitching"), {
    games: 12, first: "4/22", last: "10/5",
    totals: [
      { key: "so", label: "三振", value: 5 },
      { key: "hits", label: "被安打", value: 12 },
      { key: "bb", label: "四壞", value: 7 },
    ],
  });
});

test("摘要不補 0：全場缺值的欄位回 null", () => {
  const rows: StatRow[] = [{ name: "4/1", date: "2026-04-01", hits: 1 }, { name: "4/2", date: "2026-04-02", hits: 0 }];
  const s = gameLogSummary(rows, "batting");
  assert.equal(s.totals.find((t) => t.key === "hits")!.value, 1);
  assert.equal(s.totals.find((t) => t.key === "home_runs")!.value, null);
});

test("逐場列新到舊，且不改動原陣列", () => {
  const shi = load("shixiangyu");
  const out = gameLogRows(shi);
  assert.equal(out[0].name, "10/4");
  assert.equal(out[out.length - 1].name, "4/11");
  assert.equal(shi[0].name, "4/11");
});
