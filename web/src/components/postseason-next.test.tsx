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

// #237 首頁右欄：一行系列概況＋唯一連結直達季後總覽；下一場細節、日曆與單場入口只在季後總覽。
const hrefs = (html: string) => html.match(/href="[^"]*"/g);

test("季後入口卡：一行概況＋唯一連結到季後總覽，不重複下一場時間、主客、球場、規則勝與截至", () => {
  const j = journey("2026-10-08T12:00:00+08:00");
  const node = <PostseasonNextCard journey={j} />;
  const t = text(node);
  assert.equal(t, "季後賽 季後挑戰賽・本站尚無季後賽果紀錄 季後賽總覽 →");
  assert.deepEqual(hrefs(renderToStaticMarkup(node)), ['href="/standings?seg=3"']);
  assert.doesNotMatch(t, /10\/09|17:05|洲際|（客）|規則勝|賽果紀錄至|待更新/);
});

test("季後入口卡：已過開賽時間仍無賽果 → 照實說部分場次賽果待更新，不列單場細節", () => {
  const j = journey("2026-10-09T21:00:00+08:00");
  const node = <PostseasonNextCard journey={j} />;
  const t = text(node);
  assert.equal(t, "季後賽 季後挑戰賽・本站尚無季後賽果紀錄・部分場次賽果待更新 季後賽總覽 →");
  assert.deepEqual(hrefs(renderToStaticMarkup(node)), ['href="/standings?seg=3"']);
  assert.doesNotMatch(t, /G\d|10\/09|10\/10/);
});

// #237 單場賽況入口（slot.liveEntry）只在季後總覽呈現；首頁卡不給單場連結、不轉述單場狀態。
// 快照值為 SYNTHETIC（形狀同 19:25 RECORDED）。
const e1Status = (phase: string): LiveEntryStatus => ({
  season: 2026, kind_code: "E", game_sno: 1, canonical_phase: phase,
  live_snapshot: {
    game_id: "2026-E-1", game_sno: 1, kind_code: "E", phase, starts_at: "2026-10-09T17:05:00",
    away: { team: { code: "ADD011" } }, home: { team: { code: "ACN011" } },
  },
});

test("季後入口卡：E1 有單場入口 → 卡片內容與連結不變，仍只連季後總覽", () => {
  const base = journey("2026-10-09T19:25:00+08:00");
  const plain = text(<PostseasonNextCard journey={base} />);
  for (const phase of ["live", "final"]) {
    const j = withLiveEntries(base, { E1: e1Status(phase) });
    const html = renderToStaticMarkup(<PostseasonNextCard journey={j} />);
    const t = text(<PostseasonNextCard journey={j} />);
    assert.deepEqual(hrefs(html), ['href="/standings?seg=3"'], `${phase}：只有季後總覽連結`);
    assert.equal(t, plain, `${phase}：內容不變`);
    assert.doesNotMatch(t, /終場|比賽進行中|單場賽況/, "首頁卡不轉述單場狀態");
  }
  assert.doesNotMatch(renderToStaticMarkup(<PostseasonNextCard journey={withLiveEntries(base, { E1: null })} />), /href="\/games/);
});
