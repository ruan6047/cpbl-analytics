import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { WpBar } from "./game-board.tsx";
import { ComparisonBar, SplitBar } from "./split-bar.tsx";
import { comparisonBarVM, type ComparisonPayload } from "@/lib/playoffs-comparison.ts";

// #287 E14：單場頁勝率條抽成共用 SplitBar 後，同一輸入的 markup 必須與抽離前逐字相同。
// golden 由抽離前的 `WpBar`（game-board.tsx @ 405bc2bb，暫時 export 後以 renderToStaticMarkup）擷取，
// 原始檔另存 ~/.wf-evidence/cpbl-analytics/287/exec-1/evidence/wpbar-golden-before.json。
type Golden = { props: Parameters<typeof WpBar>[0]; html: string }[];
const golden: Golden = JSON.parse(
  readFileSync(new URL("../lib/__fixtures__/wpbar_golden_before_287.json", import.meta.url), "utf8"));

test("WpBar after SplitBar extraction renders byte-identical markup to the pre-extraction golden", () => {
  assert.equal(golden.length, 4);
  for (const g of golden) assert.equal(renderToStaticMarkup(<WpBar {...g.props} />), g.html);
});

test("WpBar keeps its own win-prob clamp: 0.4% shows 1%, 99.9% shows 99%", () => {
  const html = (wp: number) => renderToStaticMarkup(
    <WpBar homeWp={wp} homeName="H" awayName="A" homeColor="#111" awayColor="#222" />);
  assert.match(html(0.004), /width:99%;background:#222/);
  assert.match(html(0.004), /H 1%/);
  assert.match(html(0.999), /H 99%/);
});

test("SplitBar renders no extra node when no children are given", () => {
  const html = renderToStaticMarkup(<SplitBar leftPct={40} leftColor="#a" rightColor="#b" left="L" center="C" right="R" />);
  assert.equal((html.match(/<div/g) ?? []).length, 5);
  assert.match(html, /width:40%;background:#a/);
  assert.match(html, /width:60%;background:#b/);
});

const payload: ComparisonPayload = JSON.parse(
  readFileSync(new URL("../lib/__fixtures__/playoffs_comparison_2025-C.json", import.meta.url), "utf8"));

test("ComparisonBar draws both teams on the shared scale with value, unit, sample and direction", () => {
  const s = payload.scopes.series;
  const [l, r] = payload.series_id.teams as string[];
  const def = payload.metric_defs.find((d) => d.key === "era")!;
  const vm = comparisonBarVM(def, s.teams[l], s.teams[r], s.scales.era);
  const html = renderToStaticMarkup(<ComparisonBar vm={vm} leftColor="#C8A24A" rightColor="#8E1537" />);
  assert.match(html, /ERA/);
  assert.match(html, />↓</);
  assert.doesNotMatch(html, /數值低較好/);
  assert.match(html, / 局</);
  assert.ok(vm.leftPct != null);
  assert.match(html, new RegExp(`width:${vm.leftPct}%`));
});

test("ComparisonBar with a missing value shows only — and draws no 0-length bar (reason goes to footer)", () => {
  const s = payload.scopes.series;
  const [l, r] = payload.series_id.teams as string[];
  const def = payload.metric_defs.find((d) => d.key === "ops")!;
  const left = structuredClone(s.teams[l]);
  left.metrics.ops = null;
  left.null_reasons["metric:ops"] = ["column_null:bb"];
  const vm = comparisonBarVM(def, left, s.teams[r], s.scales.ops);
  const html = renderToStaticMarkup(<ComparisonBar vm={vm} leftColor="#000" rightColor="#fff" />);
  assert.equal(vm.leftPct, null);
  assert.doesNotMatch(html, /width:/);
  assert.doesNotMatch(html, /欄位|缺 box|樣本為 0|原因/);
  assert.match(html, />—</);
  assert.match(html, /data-comparison-missing="ops"/);
});
