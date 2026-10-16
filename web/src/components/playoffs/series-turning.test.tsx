import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { SeriesSummaryBlock } from "./series-summary.tsx";
import { mergeNotes, PAGE_NOTES } from "@/lib/playoffs-notes";
import {
  seriesSummaryNotes,
  turningHeading,
  turningScoreChange,
  turningSituation,
  type SeriesSummary,
  type TurningPoint,
} from "@/lib/playoffs-series-summary";

// 真實樣本：本機 DB 唯讀取得的 2026-10-16 series_summary（WP-G3 版；E1–E4 4/4、|ΔWP| 全齊；C 未開打）。
const REAL = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-series-summary_2026-10-16-g3.json", import.meta.url), "utf8")) as SeriesSummary;
const sum = (): SeriesSummary => structuredClone(REAL);

const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");
const keys = (s: SeriesSummary) => seriesSummaryNotes({ series_summary: s }).map((n) => n.key);

test("真實樣本：挑戰賽三大轉折 3 筆、依時間排列、受益隊＋整數百分點", () => {
  const out = html(<SeriesSummaryBlock summary={REAL} />);
  const rows = out.match(/data-turning="[^"]+"/g) ?? [];
  assert.deepEqual(rows, ['data-turning="2-29"', 'data-turning="3-46"', 'data-turning="4-29"']);
  const t = text(out);
  assert.ok(t.includes("三大轉折（依勝率擺動選出・依時間排列）"));
  for (const s of ["岳東華 雙殺打 刺殺", "宋晟睿 雙殺打 刺殺", "江坤宇 二壘安打", "+13pt", "+18pt", "+13pt"]) assert.ok(t.includes(s), s);
  assert.ok(t.includes("G4・4 局下　2 出局　二壘有人・0–0"));
  assert.ok(t.includes("比分（客：主）0：0 → 0：1"));
  // ⛔ 勝率水平值、⛔ 稱 MVP
  assert.doesNotMatch(t, /\d+(\.\d+)?%/);
  assert.doesNotMatch(t, /最有價值|系列 MVP/);
});

test("受益隊：主隊視角負值 ⇒ 客隊受益（G3 宋晟睿雙殺，客隊統一）", () => {
  const out = html(<SeriesSummaryBlock summary={REAL} />);
  const row = /data-turning="3-46"[\s\S]*?<\/li>/.exec(out)![0];
  assert.match(text(row), /統一獅 \+18pt|統一 \+18pt|統一7-ELEVEn獅 \+18pt/);
});

test("降級（|ΔRE24|）：小標換準則、不顯示勝率擺動、改顯示得分期望；頁尾加降級說明", () => {
  const s = sum();
  const tp = s.previous!.turning_points!;
  Object.assign(tp, { signal: "delta_re24", degraded: true, reason: "winprob_model_not_built", min_abs: 0.3, degraded_games: [1, 2, 3, 4] });
  for (const it of tp.items) it.delta_wp = null;
  const t = text(html(<SeriesSummaryBlock summary={s} />));
  assert.ok(t.includes("三大轉折（依 |ΔRE24| 選出・依時間排列）"));
  assert.doesNotMatch(t, /pt/);
  assert.ok(t.includes("得分期望 -1.2"));
  assert.ok(keys(s).includes("series.turning_degraded_re24.E"));
});

test("部分涵蓋：小標改「已涵蓋場次轉折」，頁尾 n/N", () => {
  const s = sum();
  Object.assign(s.previous!, { status: "partial", games_covered: 3, missing_games: [1] });
  s.previous!.turning_points!.scope = "covered_only";
  const t = text(html(<SeriesSummaryBlock summary={s} />));
  assert.ok(t.includes("已涵蓋場次轉折"));
  assert.doesNotMatch(t, /三大轉折/);
  const note = seriesSummaryNotes({ series_summary: s }).find((n) => n.key === "series.turning_partial.E")!;
  assert.equal(note.text, "季後挑戰賽轉折只涵蓋 3/4 場，不是全系列前三。");
});

test("榜未就緒（pending_pa）：轉折格「待更新」，無轉折頁尾", () => {
  const s = sum();
  Object.assign(s.previous!, { status: "pending_pa", games_covered: 0, batters: [], pitchers: [], turning_points: null });
  const t = text(html(<SeriesSummaryBlock summary={s} />));
  assert.ok(t.includes("三大轉折待更新"));
  assert.ok(!keys(s).includes("series.turning_method"));
});

test("候選全低於門檻：轉折格「—」，不補", () => {
  const s = sum();
  s.previous!.turning_points!.items = [];
  assert.match(text(html(<SeriesSummaryBlock summary={s} />)), /三大轉折（依勝率擺動選出・依時間排列）—/);
});

test("舊版 API（沒有 turning_points 欄）：不出轉折標題，G2 行為不變", () => {
  const s = sum();
  delete (s.previous as { turning_points?: unknown }).turning_points;
  assert.doesNotMatch(text(html(<SeriesSummaryBlock summary={s} />)), /轉折/);
  assert.ok(!keys(s).includes("series.turning_method"));
});

test("頁尾：固定方法說明一條、key 穩定、與 PAGE_NOTES 合併無衝突、每條 ≤80 字", () => {
  const s = sum();
  assert.ok(keys(s).includes("series.turning_method"));
  s.current = { ...structuredClone(s.previous!), kind_code: "C", status: "partial", games_covered: 1, games_total: 2, missing_games: [2] };
  s.current.turning_points = { ...s.current.turning_points!, scope: "covered_only", degraded: true, signal: "delta_re24" };
  Object.assign(s.previous!.turning_points!, { degraded: true, signal: "delta_re24" });
  const { notes, conflicts } = mergeNotes([{ area: "series", notes: [...PAGE_NOTES.series, ...seriesSummaryNotes({ series_summary: s })] }]);
  assert.deepEqual(conflicts, []);
  assert.equal(notes.filter((n) => n.key === "series.turning_method").length, 1);
  assert.ok(notes.some((n) => n.key === "series.turning_degraded_re24.C") && notes.some((n) => n.key === "series.turning_degraded_re24.E"));
  for (const n of notes) assert.ok([...n.text].length <= 80, `${n.key} ${[...n.text].length} 字`);
});

test("純函式：局面字串、比分變化（不加總、無變化回 null）、小標", () => {
  const it = REAL.previous!.turning_points!.items[0] as TurningPoint;
  assert.equal(turningSituation(it), "G2・4 局上　1 出局　一壘、三壘有人・0–0");
  assert.equal(turningScoreChange(it), null);
  assert.deepEqual(turningScoreChange({ ...it, away_score_after: 2 }), { before: "0：0", after: "2：0" });
  assert.equal(turningHeading({ scope: "full" }), "三大轉折");
  assert.equal(turningHeading({ scope: "covered_only" }), "已涵蓋場次轉折");
});

test("觸控：轉折列 min-h-11", () => {
  for (const li of html(<SeriesSummaryBlock summary={REAL} />).match(/<li[^>]*data-turning=[^>]*>/g) ?? []) assert.match(li, /min-h-11/);
});
