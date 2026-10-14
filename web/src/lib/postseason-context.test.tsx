import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { PostseasonOverview } from "../components/postseason-overview.tsx";
import { postseasonGameLabels, postseasonPointer, postseasonResultLabels } from "../components/postseason-next.tsx";
import { AnnouncedCompact } from "../components/postseason-calendar.tsx";
import { POSTSEASON_2026 } from "./postseason-announcement.ts";
import {
  arrangedSlotForGame,
  buildPostseasonJourney,
  postseasonJourneyFromContext,
  seriesFromContext,
  seriesProgressText,
  slotMayInvolve,
  type JourneyRow,
  type PostseasonJourney,
  type SummarySeries,
} from "./postseason-journey.ts";
import type { PostseasonSeriesContextV2 } from "./postseason-series-contract.ts";

// #283 S02 WP5：讀 Python 產生、committed 的同一份 golden（tests/test_postseason_context_golden.py），
// 驗首頁、日曆、當季戰績、單場頁吃同一份 series_context 得到相同的系列事實。前端不重算規則。

const router = { back() {}, forward() {}, push() {}, replace() {}, refresh() {}, hmrRefresh() {}, prefetch() {} };
function text(node: ReactElement): string {
  return render(<AppRouterContext.Provider value={router}>{node}</AppRouterContext.Provider>)
    .replace(/<[^>]*>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&")
    .replace(/\s+/g, " ").trim();
}

function golden(name: string): PostseasonSeriesContextV2 {
  return JSON.parse(readFileSync(new URL(`./__golden__/series-context/${name}.json`, import.meta.url), "utf8"));
}

const BRO = "ACN011";
const LION = "ADD011";
const DRAGON = "AAA011";

const now = golden("2026-e-decided-c-pending");
const afterE2 = golden("2026-e-after-e2");
const swept = golden("2026-c-swept-injected");
const y2025 = golden("2025-complete");

function journeyOf(ctx: PostseasonSeriesContextV2): PostseasonJourney {
  const j = postseasonJourneyFromContext(ctx, null);
  assert.ok(j);
  return j;
}

const slot = (j: PostseasonJourney, key: string) => j.slots.find((s) => s.key === key)!;

test("2026 真實狀態：挑戰賽兄弟 3（規則 1＋實際 2）晉級；台灣大賽味全對兄弟、下一場 C1", () => {
  const j = journeyOf(now);
  assert.equal(j.series.E.status, "decided");
  assert.equal(j.series.E.tally.winner, BRO);
  assert.equal(seriesProgressText(j.series.E), "統一 2：兄弟 3（兄弟實際勝 2＋規則勝 1）・兄弟晉級台灣大賽");
  assert.equal(j.series.C.status, "not_started");
  assert.deepEqual([j.series.C.tally.a.code, j.series.C.tally.b.code], [DRAGON, BRO]);
  assert.equal(j.series.C.tally.a.ruleWins + j.series.C.tally.b.ruleWins, 0);
  assert.equal(j.next?.key, "C1");
  assert.equal(j.remaining, true);
  assert.equal(j.recordedGames, 4);
});

test("G01／G02：單場連結只來自真實列且帶 kind／year；E1–E4 終場、C1–C7 已排定", () => {
  const j = journeyOf(now);
  for (const k of ["E1", "E2", "E3", "E4"]) assert.equal(slot(j, k).status, "final");
  for (let n = 1; n <= 7; n++) {
    const s = slot(j, `C${n}`);
    assert.equal(s.status, "scheduled");
    assert.equal(s.href, `/games/${n}?kind=C&year=2026`);
  }
  assert.equal(slot(j, "E4").href, "/games/4?kind=E&year=2026");
  assert.deepEqual(slot(j, "E4").score, { away: 2, home: 8 });
});

test("首頁、日曆、當季戰績、單場頁同源：大比分、晉級字樣、對手、場序一致", () => {
  const j = journeyOf(now);
  const pointer = postseasonPointer(j);
  assert.ok(pointer);
  assert.match(JSON.stringify(postseasonGameLabels(j)), /台灣大賽/);
  const results = postseasonResultLabels(j);
  assert.ok(Object.values(results).some((v) => v.includes("兄弟晉級台灣大賽")));
  // 日曆格
  const cell = text(<AnnouncedCompact s={slot(j, "C1")} />);
  assert.match(cell, /已排定/);
  // 當季戰績（季後總覽）
  const overview = text(<PostseasonOverview journey={{ ...j, scheduleChanges: [] }} nameOf={(c) => c ?? ""} seedOf={() => ""} active="E" />);
  assert.match(overview, /兄弟/);
  assert.match(overview, /規則勝：兄弟依規則先得 1 勝/);
  // 單場頁：C1 對到公告 C1、非如有必要
  const s = arrangedSlotForGame(now, "C", 1);
  assert.equal(s?.seq, 1);
  assert.equal(s?.conditional, false);
  assert.equal(arrangedSlotForGame(now, "C", 99), null);
});

test("挑戰賽進行中（真實 E1–E2）：兄弟 2（規則 1＋實際 1）、獅 1；兄弟聽牌；下一場 E3", () => {
  const j = journeyOf(afterE2);
  assert.equal(seriesProgressText(j.series.E), "統一 1：兄弟 2（兄弟實際勝 1＋規則勝 1）・統一還差 2 勝、兄弟還差 1 勝");
  assert.equal(afterE2.series.E.sides.find((s) => s.team_code === BRO)?.clinch, true);
  assert.equal(afterE2.series.E.sides.find((s) => s.team_code === LION)?.facing_elimination, true);
  assert.equal(j.next?.key, "E3");
  // C 對手未定：可能參賽隊＝種子＋挑戰賽兩隊
  assert.ok(slotMayInvolve(j, slot(j, "C1"), LION));
  assert.equal(slot(j, "C1").awayLabel, "挑戰賽勝隊");
});

test("決勝後未需場（注入 C 四連勝）：C5–C7 依條件不需進行、原安排保留；系列結束不再有下一場", () => {
  const j = journeyOf(swept);
  assert.equal(j.series.C.status, "decided");
  assert.equal(seriesProgressText(j.series.C), "味全 0：兄弟 4・兄弟奪得總冠軍");
  for (const k of ["C5", "C6", "C7"]) {
    assert.equal(slot(j, k).status, "not_needed");
    assert.ok(slot(j, k).date && slot(j, k).venue);   // 原安排可追溯
  }
  assert.equal(j.next, null);
  assert.equal(j.remaining, false);
});

test("沒有公告安排的年份（2025）：不建旅程；系列計數仍可讀（已完成 E→C）", () => {
  assert.equal(postseasonJourneyFromContext(y2025, null), null);
  const e = seriesFromContext(y2025, "E", "季後挑戰賽");
  const c = seriesFromContext(y2025, "C", "台灣大賽");
  assert.equal(e.tally.winner, "AJL011");
  assert.equal(c.tally.winner, "AJL011");
  assert.equal(c.games.length, 5);
});

test("公告轉錄：API 的公告與 TS 舊常數（報告路徑殘留）逐欄一致", () => {
  const j = journeyOf(now);
  assert.deepEqual(j.announcement, POSTSEASON_2026);
});

// —— 報告路徑等值（T1 裁定前殘留）：舊 TS 算法與 Python 同輸入同結果 ——

function legacyInputs(ctx: PostseasonSeriesContextV2): { summary: SummarySeries[]; rows: JourneyRow[] } {
  const done = ctx.games.filter((g) => g.completed);
  const summary = (["E", "C"] as const).map((k) => {
    const s = ctx.series[k];
    return {
      kind_code: k, team1_code: s.sides[0].team_code ?? "", team2_code: s.sides[1].team_code ?? "",
      games: done.filter((g) => g.game_key.kind_code === k).map((g, i) => ({
        game_no: i + 1, game_sno: g.game_key.game_sno, date: g.game_date,
        home_code: g.home_team_code, home_score: g.home_score!, away_code: g.away_team_code, away_score: g.away_score!,
      })),
    };
  }).filter((s) => s.games.length > 0);
  const rows = ctx.games.map((g) => ({
    year: g.game_key.year, kind_code: g.game_key.kind_code, game_sno: g.game_key.game_sno, game_date: g.game_date!,
    venue: g.venue, away_team_code: g.away_team_code, home_team_code: g.home_team_code,
    away_score: g.away_score ?? 0, home_score: g.home_score ?? 0, completed: g.completed,
  }));
  return { summary, rows };
}

for (const [name, ctx] of [["2026-e-decided-c-pending", now], ["2026-e-after-e2", afterE2]] as const) {
  test(`等值：${name} 舊 TS 算法（報告路徑）與 Python 系列結果相同`, () => {
    const { summary, rows } = legacyInputs(ctx);
    const legacy = buildPostseasonJourney({ announcement: POSTSEASON_2026, summary, rows, nowMs: Date.parse(ctx.as_of.now), dataAsOf: null });
    const fromApi = journeyOf(ctx);
    for (const k of ["E", "C"] as const) {
      assert.deepEqual(legacy.series[k].tally, fromApi.series[k].tally, `${k} tally`);
      assert.equal(legacy.series[k].status, fromApi.series[k].status, `${k} status`);
    }
    assert.deepEqual(legacy.slots.map((s) => [s.key, s.status, s.href]), fromApi.slots.map((s) => [s.key, s.status, s.href]));
    assert.equal(legacy.next?.key, fromApi.next?.key);
  });
}

test("已知差異（本卡修正）：決勝後仍有 DB 列的未需場，舊算法不標不需進行、Python 標 not_needed", () => {
  const { summary, rows } = legacyInputs(swept);
  const legacy = buildPostseasonJourney({ announcement: POSTSEASON_2026, summary, rows, nowMs: Date.parse(swept.as_of.now), dataAsOf: null });
  assert.notEqual(legacy.slots.find((s) => s.key === "C5")?.status, "not_needed");
  assert.equal(slot(journeyOf(swept), "C5").status, "not_needed");
});
