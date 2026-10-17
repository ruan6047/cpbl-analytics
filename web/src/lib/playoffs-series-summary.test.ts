import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { mergeNotes, PAGE_NOTES } from "./playoffs-notes.ts";
import {
  batterValueText,
  boardReady,
  mvpBadge,
  pitcherValueText,
  seriesSummaryNotes,
  showSummary,
  signed1,
  type SeriesSummary,
  type SeriesSummaryBlock,
} from "./playoffs-series-summary.ts";

// 真實樣本：本機 DB 唯讀取得的 2026-10-16 series_summary（E1–E4 4/4 涵蓋、C 未開打；見 _provenance）。
const REAL = JSON.parse(readFileSync(new URL("./__fixtures__/playoffs-series-summary_2026-10-16.json", import.meta.url), "utf8")) as SeriesSummary;
const clone = (): SeriesSummary => structuredClone(REAL);
const E = (): SeriesSummaryBlock => clone().previous!;
const keys = (s: SeriesSummary) => seriesSummaryNotes({ series_summary: s }).map((n) => n.key);

test("真實樣本：C 0 場不渲染、E 照排；正常完整涵蓋時無固定頁尾說明（已收進 InfoDot）", () => {
  assert.equal(showSummary(REAL.current), false);
  assert.equal(showSummary(REAL.previous), true);
  assert.equal(boardReady(REAL.previous!), true);
  assert.deepEqual(keys(REAL), []);
});

test("沒有 series_summary（舊版 API）或兩系列都沒完賽 ⇒ 0 條說明", () => {
  assert.deepEqual(seriesSummaryNotes(null), []);
  assert.deepEqual(seriesSummaryNotes({}), []);
  const s = clone();
  s.previous = null;
  assert.deepEqual(seriesSummaryNotes({ series_summary: s }), []);
});

test("partial：頁尾 n/N 與缺場；未送達／不完整分開說", () => {
  const s = clone();
  Object.assign(s.previous!, { status: "partial", games_covered: 3, missing_games: [2] });
  const n = seriesSummaryNotes({ series_summary: s }).find((x) => x.key === "series.summary_partial.E")!;
  assert.equal(n.text, "季後挑戰賽累計榜只涵蓋 3/4 場；G2 逐打席資料尚未送達，不是完整系列排行。");
  Object.assign(s.previous!, { missing_games: [2, 4], excluded_games: [{ series_game_no: 4, reason: "terminal_event_missing" }], games_covered: 2 });
  const m = seriesSummaryNotes({ series_summary: s }).find((x) => x.key === "series.summary_partial.E")!;
  assert.match(m.text, /只涵蓋 2\/4 場；G2、G4 逐打席資料尚未送達或不完整/);
});

test("pending_pa／unavailable：榜格待更新＋頁尾原因；MVP 次數照常", () => {
  const s = clone();
  Object.assign(s.previous!, { status: "pending_pa", games_covered: 0, missing_games: [1, 2, 3, 4], batters: [], pitchers: [] });
  assert.equal(boardReady(s.previous!), false);
  assert.ok(keys(s).includes("series.summary_pending.E"));
  Object.assign(s.previous!, { status: "unavailable" });
  const t = seriesSummaryNotes({ series_summary: s }).map((n) => n.text).join("\n");
  assert.match(t, /季後挑戰賽累計榜暫時無法讀取，比分與官方 MVP 不受影響。/);
});

test("投手無法歸屬、MVP 缺場：各一條，key 穩定（不帶索引或時間）", () => {
  const s = clone();
  Object.assign(s.previous!, { pitcher_unattributed: 2, mvp_missing_games: [3] });
  const a = seriesSummaryNotes({ series_summary: s });
  const b = seriesSummaryNotes({ series_summary: structuredClone(s) });
  assert.deepEqual(a, b);
  assert.ok(a.some((n) => n.key === "series.pitcher_unattributed.E" && /2 個打席/.test(n.text)));
  assert.ok(a.some((n) => n.key === "series.mvp_missing.E" && /G3 官方單場 MVP 本站尚未取得/.test(n.text)));
  for (const n of a) assert.match(n.key, /^series\.[a-z_]+(\.[EC])?$/);
});

test("E、C 同狀態不撞 key；與 PAGE_NOTES 合併無衝突", () => {
  const s = clone();
  s.current = { ...E(), kind_code: "C", status: "partial", games_covered: 1, games_total: 2, missing_games: [2] };
  Object.assign(s.previous!, { status: "partial", games_covered: 3, missing_games: [4] });
  const { notes, conflicts } = mergeNotes([{ area: "series", notes: [...PAGE_NOTES.series, ...seriesSummaryNotes({ series_summary: s })] }]);
  assert.deepEqual(conflicts, []);
  assert.ok(notes.some((n) => n.key === "series.summary_partial.C") && notes.some((n) => n.key === "series.summary_partial.E"));
});

test("說明字數 ≤80（推估上限，契約 §9）且無 HTML", () => {
  const s = clone();
  Object.assign(s.previous!, { status: "partial", games_covered: 1, missing_games: [2, 3, 4], pitcher_unattributed: 12, mvp_missing_games: [2, 3, 4] });
  for (const n of seriesSummaryNotes({ series_summary: s })) {
    assert.ok([...n.text].length <= 80, `${n.key} ${[...n.text].length} 字`);
    assert.doesNotMatch(n.text, /[<>]/);
  }
});

test("格式：一位小數帶號、-0.0 不出現；精簡數值與章", () => {
  assert.equal(signed1(2.4087), "+2.4");
  assert.equal(signed1(-0.31), "-0.3");
  assert.equal(signed1(-0.04), "0.0");
  assert.equal(batterValueText(1.6517), "+1.7 分");
  assert.equal(pitcherValueText(3.4458), "+3.4 分");
  assert.equal(mvpBadge(0), null);
  assert.equal(mvpBadge(2), "MVP ×2");
});
