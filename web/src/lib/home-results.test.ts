import assert from "node:assert/strict";
import test from "node:test";

import type { CalendarGame } from "./api.ts";
import type { DailyGame, DailySummary } from "./daily-summary.ts";
import { previousGameDay, resultsCutDate } from "./home-results.ts";

// 首頁 7:3 右欄的取法回歸（#220 規劃 §3 必要回歸：混合日、延賽補賽、未來日期保留賽、0:0、
// 季後賽、季初第一天、UTC）。資料形狀取自本機 2026-10-02 實查的 summary／calendar 欄位。

function cal(over: Partial<CalendarGame>): CalendarGame {
  return {
    year: 2026, kind_code: "A", game_sno: 1, game_date: "2026-09-30", venue: "新莊", present_status: 1,
    away_team_name: "味全龍", away_team_code: "AAA011", away_score: 0,
    home_team_name: "富邦悍將", home_team_code: "AEO011", home_score: 0,
    win_pitcher: null, lose_pitcher: null, mvp: null, home_starter: null, away_starter: null,
    attendance: null, game_time: null, delay_kind: null, orig_date: null,
    ...over,
  };
}

function daily(over: Partial<DailyGame>): DailyGame {
  return {
    season: 2026, kind_code: "A", game_sno: 1, game_date: "2026-09-30", venue: "新莊",
    away_team_code: "AAA011", away_team_name: "味全龍", away_score: 5,
    home_team_code: "AEO011", home_team_name: "富邦悍將", home_score: 3,
    completed: true, delay_kind: null, orig_date: null,
    ...over,
  };
}

type S = Pick<DailySummary, "today" | "scope" | "latest_game_day">;
function summary(over: { today?: string | null; asOf?: string; latest?: { game_date: string; games: DailyGame[] } | null }): S {
  return {
    scope: { season: null, kind_code: "A", kinds: ["A", "E", "C"], as_of: over.asOf ?? "2026-10-02" },
    today: over.today === null || over.today === undefined ? null
      : { game_date: over.today, started: false, live_source: { status: "ok", reason: null, snapshots: 0, games: 0 }, games: [] },
    latest_game_day: over.latest === undefined ? null : over.latest,
  };
}

test("今天尚無完成場：直接用 summary 的 latest_game_day（後端證據感知完賽）", () => {
  const s = summary({ today: "2026-10-02", latest: { game_date: "2026-09-30", games: [daily({ game_sno: 254 })] } });
  const r = previousGameDay(s, [cal({ game_sno: 254, mvp: "某選手", away_score: 5, home_score: 3 })]);
  assert.equal(r?.game_date, "2026-09-30");
  assert.equal(r?.source, "summary");
  assert.equal(r?.games[0].mvp, "某選手", "MVP 由 calendar 依 kind/sno/season 合併");
});

test("今天已有完成場：latest 指向今天 → 改從 calendar 找嚴格早於今天的最近完賽日", () => {
  const s = summary({ today: "2026-10-02", latest: { game_date: "2026-10-02", games: [daily({ game_date: "2026-10-02" })] } });
  const r = previousGameDay(s, [
    cal({ game_sno: 279, game_date: "2026-10-02", away_score: 3, home_score: 1 }),
    // 10/01 只有延賽與保留（中止比分掛在未來日期的保留賽不會出現在 10/01）→ 跳過
    cal({ game_sno: 277, game_date: "2026-10-01", delay_kind: "延賽", orig_date: "2026-08-21" }),
    cal({ game_sno: 302, game_date: "2026-09-30", away_score: 7, home_score: 1, mvp: "MVP 甲" }),
  ]);
  assert.equal(r?.game_date, "2026-09-30");
  assert.equal(r?.source, "calendar");
  assert.equal(r?.games.length, 1);
  assert.equal(r?.games[0].mvp, "MVP 甲");
  assert.ok(r?.games.every((g) => g.game_date < "2026-10-02"), "右欄不得出現今天的場次");
});

test("混合日：同一天有完賽與無賽果場，整天送出、未完成場不帶比分", () => {
  const s = summary({ today: "2026-10-02", latest: { game_date: "2026-10-02", games: [] } });
  const r = previousGameDay(s, [
    cal({ game_sno: 253, game_date: "2026-08-09", away_score: 2, home_score: 9 }),
    cal({ game_sno: 254, game_date: "2026-08-09", delay_kind: "延賽", orig_date: "2026-08-09" }),
  ]);
  assert.equal(r?.games.length, 2);
  const pending = r?.games.find((g) => g.game_sno === 254);
  assert.equal(pending?.completed, false);
  assert.equal(pending?.away_score, null, "0:0 不回填成比分");
});

test("未來日期的保留賽（帶中止比分）不得被當成前一比賽日", () => {
  const s = summary({ today: "2026-10-02", latest: { game_date: "2026-10-02", games: [] } });
  const r = previousGameDay(s, [
    cal({ game_sno: 326, game_date: "2026-10-09", delay_kind: "保留", orig_date: "2026-09-12", away_score: 5, home_score: 4 }),
    cal({ game_sno: 300, game_date: "2026-09-29", away_score: 1, home_score: 2 }),
  ]);
  assert.equal(r?.game_date, "2026-09-29");
});

test("0:0 場在 calendar 路徑視為無賽果（已知限制：calendar 無完賽證據欄）", () => {
  const s = summary({ today: "2026-10-02", latest: { game_date: "2026-10-02", games: [] } });
  const r = previousGameDay(s, [cal({ game_sno: 1, game_date: "2026-10-01" }), cal({ game_sno: 2, game_date: "2026-09-28", away_score: 1, home_score: 0 })]);
  assert.equal(r?.game_date, "2026-09-28", "只有 0:0 的日子不被選為前一比賽日");
});

test("0:0 真和局在 summary 路徑照後端 completed 呈現為完賽", () => {
  const s = summary({ today: "2026-10-02", latest: { game_date: "2026-09-30", games: [daily({ away_score: 0, home_score: 0, completed: true })] } });
  const r = previousGameDay(s, null);
  assert.equal(r?.games[0].completed, true);
});

test("季後賽：calendar 的 E／C 場次與例行賽同樣參與", () => {
  const s = summary({ today: "2026-10-20", asOf: "2026-10-20", latest: { game_date: "2026-10-20", games: [] } });
  const r = previousGameDay(s, [
    cal({ kind_code: "A", game_sno: 360, game_date: "2026-10-05", away_score: 4, home_score: 2 }),
    cal({ kind_code: "E", game_sno: 3, game_date: "2026-10-18", away_score: 2, home_score: 6 }),
  ]);
  assert.equal(r?.game_date, "2026-10-18");
  assert.equal(r?.games[0].kind_code, "E");
});

test("季初第一天：本季 calendar 沒有更早的完賽日 → 用早於切點的 latest；都沒有回 null", () => {
  const first = summary({ today: "2026-03-28", asOf: "2026-03-28", latest: { game_date: "2025-10-30", games: [daily({ season: 2025, game_date: "2025-10-30" })] } });
  assert.equal(previousGameDay(first, [cal({ game_date: "2026-03-28" })])?.game_date, "2025-10-30");
  const none = summary({ today: "2026-03-28", asOf: "2026-03-28", latest: { game_date: "2026-03-28", games: [] } });
  assert.equal(previousGameDay(none, [cal({ game_date: "2026-03-28", away_score: 1, home_score: 0 })]), null);
});

test("UTC：切點只取 summary 的台北日期，不讀執行環境時鐘", () => {
  // 今天無賽程（today=null）時用 scope.as_of；不論 process.env.TZ 為何，結果只由字串決定。
  const s = summary({ today: null, asOf: "2026-10-02", latest: { game_date: "2026-10-02", games: [] } });
  assert.equal(resultsCutDate(s), "2026-10-02");
  const prev = process.env.TZ;
  process.env.TZ = "UTC";
  try {
    const r = previousGameDay(s, [cal({ game_date: "2026-10-01", away_score: 3, home_score: 2 })]);
    assert.equal(r?.game_date, "2026-10-01");
  } finally {
    if (prev === undefined) delete process.env.TZ; else process.env.TZ = prev;
  }
});
