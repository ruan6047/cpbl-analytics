import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import DailyHub from "./daily-hub.tsx";
import { PostseasonNextCard, postseasonPointer } from "./postseason-next.tsx";
import type { DailySummary } from "@/lib/daily-summary.ts";
import { POSTSEASON_2026 } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, withLiveEntries, type LiveEntryStatus, type SeriesGame } from "@/lib/postseason-journey.ts";

// #237 首頁：資料庫沒有未來列、但公告還有未完成季後場次時，不得出現「本季賽程已全部結束」。

function text(node: ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

/** 例行賽打完、資料庫沒有任何未來列：後端回 season_complete、沒有下一批。 */
function seasonComplete(): DailySummary {
  return {
    scope: { season: 2026, kind_code: "A", kinds: ["A", "E", "C"], as_of: "2026-10-08" },
    today: null,
    latest_game_day: null,
    next_slate: null,
    freshness: {
      as_of: "2026-10-08",
      last_completed_game_date: "2026-10-04",
      last_refresh: { at: null, ok: null, scope: null, hours_ago: null, status: "unknown", reason: null },
      unresolved_games: [],
    },
    availability: {
      schedule: { status: "season_complete", reason: null },
      results: { status: "ok", reason: null },
      pregame_model: { status: "serving_current", reason: null, trained_through: null, signals: null },
    },
  };
}

const journey = (nowIso: string, eGames: SeriesGame[] = []) => buildPostseasonJourney({
  announcement: POSTSEASON_2026,
  summary: eGames.length ? [{ kind_code: "E", team1_code: "ADD011", team2_code: "ACN011", games: eGames }] : [],
  rows: null,
  nowMs: Date.parse(nowIso),
  dataAsOf: "2026-10-04",
});

test("公告仍有未完成場次：首頁左欄改寫全季結束文案，並連到季後總覽", () => {
  const j = journey("2026-10-08T12:00:00+08:00");
  const node = <DailyHub summary={seasonComplete()} calendar={null} postseason={postseasonPointer(j)} />;
  const t = text(node);
  assert.doesNotMatch(t, /本季賽程已全部結束/);
  assert.match(t, /例行賽已結束，季後賽仍在進行/);
  // 下一場的日期與對戰只由同頁的季後卡呈現，左欄不重複。
  assert.doesNotMatch(t, /10\/09/);
  assert.match(renderToStaticMarkup(node), /href="\/standings\?seg=3"/);
});

test("沒有季後公告（或已全部完成）：沿用原文案", () => {
  const t = text(<DailyHub summary={seasonComplete()} calendar={null} postseason={null} />);
  assert.match(t, /本季賽程已全部結束/);
});

test("季後下一場卡：日期時間、主客、球場、狀態、截至，入口連到季後總覽與日曆；公告場次不給單場連結", () => {
  const j = journey("2026-10-08T12:00:00+08:00");
  const node = <PostseasonNextCard journey={j} />;
  const html = renderToStaticMarkup(node);
  const t = text(node);
  assert.match(t, /季後賽・下一場 季後挑戰賽 G1 公告安排 10\/09（五） 17:05/);
  assert.match(t, /統一獅（客） 對 中信兄弟（主） 洲際/);
  assert.match(t, /季後挑戰賽：統一 0：兄弟 1（兄弟實際勝 0＋規則勝 1）/);
  assert.match(t, /本站尚無季後賽果紀錄，本站賽果紀錄至 10\/04。/);
  // 可讀性：「公告安排」只在狀態徽章說一次；公告來源長句只放季後總覽的可展開區。
  assert.equal(t.split("公告安排").length - 1, 1);
  assert.doesNotMatch(t, /CPBL 官方/);
  assert.match(html, /href="\/standings\?seg=3"/);
  assert.match(html, /href="\/games\?month=2026-10"/);
  assert.doesNotMatch(html, /href="\/games\/\d/);
  assert.doesNotMatch(t, /賽果待更新/);
});

test("季後下一場卡：已過開賽時間仍無賽果 → 賽果待更新，下一場前進到下一個公告場次", () => {
  const j = journey("2026-10-09T21:00:00+08:00");
  const t = text(<PostseasonNextCard journey={j} />);
  assert.match(t, /季後挑戰賽 G2 公告安排 10\/10（六） 17:05/);
  assert.match(t, /中信兄弟（客） 對 統一獅（主） 亞太主/);
  assert.match(t, /季後挑戰賽 G1 10\/09（五） 17:05：賽果待更新（已過預定開賽時間・本站尚無賽果紀錄）/);
});

// #237 單場賽況入口：資料庫沒有 E1 列、單場狀態身分相符時，待更新那一行給單場頁連結，
// 並明說整體賽果待更新；系列進度與截至一句不變。快照值為 SYNTHETIC（形狀同 19:25 RECORDED）。
const e1Status = (phase: string): LiveEntryStatus => ({
  season: 2026, kind_code: "E", game_sno: 1, canonical_phase: phase,
  live_snapshot: {
    game_id: "2026-E-1", game_sno: 1, kind_code: "E", phase, starts_at: "2026-10-09T17:05:00",
    away: { team: { code: "ADD011" } }, home: { team: { code: "ACN011" } },
  },
});
const E1_HREF = /href="\/games\/1\?kind=E&amp;year=2026"/g;

test("季後下一場卡：E1 有單場入口 → 待更新行給單場頁連結且只有一個，系列與截至不變", () => {
  const base = journey("2026-10-09T19:25:00+08:00");
  for (const phase of ["live", "final"]) {
    const j = withLiveEntries(base, { E1: e1Status(phase) });
    const html = renderToStaticMarkup(<PostseasonNextCard journey={j} />);
    const t = text(<PostseasonNextCard journey={j} />);
    assert.equal(html.match(E1_HREF)?.length, 1, `${phase}：E1 連結恰一個`);
    assert.match(t, /季後挑戰賽 G1 10\/09（五） 17:05：整體賽果待更新，可查看單場賽況/);
    assert.match(t, /季後挑戰賽 G2 公告安排/);
    const plain = text(<PostseasonNextCard journey={base} />);
    const tail = (s: string) => s.slice(s.indexOf("季後挑戰賽：統一"));
    assert.equal(tail(t).replace(/ 單場賽況 →/, ""), tail(plain), `${phase}：系列進度與截至一句不變`);
    assert.doesNotMatch(t, /終場|比賽進行中/, "總覽不轉述單場狀態");
  }
  assert.doesNotMatch(renderToStaticMarkup(<PostseasonNextCard journey={withLiveEntries(base, { E1: null })} />), /href="\/games\/\d/);
});
