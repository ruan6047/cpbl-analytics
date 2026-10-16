import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import ComparisonSectionDefault, { ComparisonSection, ComparisonView } from "./comparison-section.tsx";
import {
  COMPARISON_COPY, NOTE_COPY, comparisonNotes, type ComparisonPayload, type ComparisonScopeKey,
} from "@/lib/playoffs-comparison.ts";

// #287 WP6b：第 2 區元件（#285 掛點契約 r3 §2）。fixture＝卡號隔離庫真實資料的 reader 輸出
// （2025 台灣大賽 ACN011 vs AJL011 三範圍齊備；2026 台灣大賽 AAA011 vs ACN011 本系列未開打）。
const load = (name: string): ComparisonPayload =>
  JSON.parse(readFileSync(new URL(`../../lib/__fixtures__/${name}`, import.meta.url), "utf8"));
const p2025 = load("playoffs_comparison_2025-C.json");
const p2026 = load("playoffs_comparison_2026-C.json");

const text = (html: string) => html.replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
const view = (data: ComparisonPayload, scope: ComparisonScopeKey) =>
  renderToStaticMarkup(<ComparisonView data={data} scope={scope} />);

test("exports: named + default, null shows area error state, own h2, no id=teams", () => {
  assert.equal(ComparisonSectionDefault, ComparisonSection);
  const html = renderToStaticMarkup(<ComparisonSection data={null} />);
  assert.match(html, /<h2 id="teams-heading"[^>]*>隊伍表現<\/h2>/);
  assert.match(text(html), new RegExp(COMPARISON_COPY.loadFailed));
  assert.doesNotMatch(html, /id="teams"/);
});

test("default scope: series when series has data (2025 C), season otherwise (2026 C)", () => {
  assert.match(renderToStaticMarkup(<ComparisonSection data={p2025} />), /data-scope="series"/);
  assert.match(renderToStaticMarkup(<ComparisonSection data={p2026} />), /data-scope="season_a"/);
});

test("three scopes render metrics, streaks and style from payload only", () => {
  for (const scope of ["season_a", "head_to_head_a", "series"] as const) {
    const html = view(p2025, scope);
    for (const def of p2025.metric_defs) assert.match(html, new RegExp(`>${def.label}<`));
    assert.match(text(html), new RegExp(COMPARISON_COPY.streakLabel[scope]));
    assert.match(html, /aria-pressed="true"[^>]*>[^<]*<\/button>/);
  }
  assert.match(text(view(p2025, "series")), /本系列 二連勝/);
  assert.match(text(view(p2025, "head_to_head_a")), /24 場/); // 樣本數值留格內（F1）
  assert.doesNotMatch(view(p2025, "head_to_head_a"), /第 [12]</); // D2：對戰不出排名
  assert.match(view(p2025, "season_a"), /· 第 [12]/); // 全年才有排名 chip
});

test("T5 side-by-side only in series scope with season data; no prediction words", () => {
  const html = view(p2025, "series");
  assert.match(html, /data-t5=""/);
  assert.match(text(html), /例行賽背景 vs 本系列實際/);
  assert.doesNotMatch(view(p2025, "season_a"), /data-t5/);
  assert.doesNotMatch(text(html), /預測|預期|誤差/);
});

test("no explanatory notes rendered in the area: footer texts never appear in cells", () => {
  const all = [view(p2025, "season_a"), view(p2025, "head_to_head_a"), view(p2025, "series"),
    view(p2026, "season_a"), view(p2026, "series")].map(text).join(" ");
  for (const n of comparisonNotes(p2025)) assert.ok(!all.includes(n.text), n.key);
  for (const v of Object.values(NOTE_COPY)) if (typeof v === "string") assert.ok(!all.includes(v));
  assert.doesNotMatch(all, /數值高較好|數值低較好|只計已到|來源已更正|尚未建置|box 尚未送達/);
});

test("short statuses only: 未開打, 待更新, 對戰組合待定", () => {
  assert.match(text(view(p2026, "series")), /本系列尚未開打/);
  const pending = structuredClone(p2025);
  pending.scopes.series.status = "pending_source";
  pending.scopes.series.missing_game_keys = ["2025/C/5"];
  const ph = view(pending, "series");
  assert.match(ph, /data-scope-status="pending_source"[^>]*>待更新</);
  assert.doesNotMatch(text(ph), /第 5 場|2025\/C\/5/);
  const missing = structuredClone(p2026);
  missing.scopes.season_a = { status: "summary_missing", source: null, teams: {}, scales: {}, league: null };
  const mh = view(missing, "season_a");
  assert.match(mh, /data-scope-status="summary_missing"[^>]*>待更新</);
  assert.doesNotMatch(mh, />OPS</); // 無隊伍資料時不畫空比較條
  const pp = structuredClone(p2026);
  pp.scopes.head_to_head_a = { status: "participants_pending", games: null, teams: {}, scales: {} };
  assert.match(text(view(pp, "head_to_head_a")), /對戰組合待定/);
});

test("missing metric cell shows only —", () => {
  const d = structuredClone(p2025);
  const [l] = d.series_id.teams as string[];
  d.scopes.series.teams[l].metrics.der = null;
  d.scopes.series.teams[l].null_reasons["metric:der"] = ["zero_denominator"];
  const html = view(d, "series");
  assert.match(html, /data-comparison-missing="der"/);
  assert.doesNotMatch(text(html), /樣本為 0/);
});

test("registry: #teams 一筆＝本卡端點、元件、every_round、notes（契約 r3 §4）", async () => {
  const { PLAYOFFS_AREAS } = await import("./area-registry.ts");
  const { COMPARISON_AREA } = await import("@/lib/playoffs-comparison-area.ts");
  const teams = PLAYOFFS_AREAS.filter((r) => r.id === "teams");
  assert.equal(teams.length, 1);
  assert.equal(teams[0], COMPARISON_AREA);
  assert.equal(COMPARISON_AREA.Section, ComparisonSection);
  assert.equal(COMPARISON_AREA.refresh, "every_round");
  assert.equal(COMPARISON_AREA.path(2026, "C"), "/api/v1/playoffs/comparison?season=2026&series=C");
  assert.deepEqual(COMPARISON_AREA.notes!(null), comparisonNotes(null));
});
