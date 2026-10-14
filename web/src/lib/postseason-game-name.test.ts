import assert from "node:assert/strict";
import { test } from "node:test";
import { POSTSEASON_2026 } from "./postseason-announcement.ts";
import { buildPostseasonJourney, type JourneyRow, type SeriesGame } from "./postseason-journey.ts";
import { announcedSlotOf, monthDay, nextGameName, postseasonGameName, reportEntry, taipeiMinute } from "./postseason-game-name.ts";

// SYNTHETIC：形狀取自 #273 研究（E4 統一 2:8 兄弟，C1 10/17 兄弟@味全・大巨蛋）。
const LIONS = "ADD011", BROTHERS = "ACN011", DRAGONS = "AAA011";
const E_GAMES: SeriesGame[] = [
  { game_no: 1, game_sno: 1, date: "2026-10-09", away_code: LIONS, away_score: 3, home_code: BROTHERS, home_score: 1 },
  { game_no: 2, game_sno: 2, date: "2026-10-10", away_code: BROTHERS, away_score: 5, home_code: LIONS, home_score: 2 },
  { game_no: 3, game_sno: 3, date: "2026-10-11", away_code: LIONS, away_score: 4, home_code: BROTHERS, home_score: 2 },
  { game_no: 4, game_sno: 4, date: "2026-10-12", away_code: LIONS, away_score: 2, home_code: BROTHERS, home_score: 8 },
];
const C_ROW = (sno: number, date: string): JourneyRow => ({ year: 2026, kind_code: "C", game_sno: sno, game_date: date, venue: "大巨蛋",
  away_team_code: BROTHERS, home_team_code: DRAGONS, away_score: 0, home_score: 0, completed: false });
const journey = (rows: JourneyRow[] | null) => buildPostseasonJourney({ announcement: POSTSEASON_2026,
  summary: [{ kind_code: "E", team1_code: BROTHERS, team2_code: LIONS, games: E_GAMES }], rows,
  nowMs: Date.parse("2026-10-14T12:00:00+08:00"), dataAsOf: "2026-10-12" });

test("完賽場與已入庫場次取公告場序，下一場取旅程 next", () => {
  const j = journey([C_ROW(1, "2026-10-17")]);
  assert.equal(postseasonGameName(j, "E", 4), "季後挑戰賽 G4");
  assert.equal(postseasonGameName(j, "C", 1), "台灣大賽 G1");
  assert.equal(nextGameName(j), "台灣大賽 G1");
});

test("⛔ 不從場號推場序：未入庫的 C 場號回 null；正式場號與公告場序不同時以公告歸併為準", () => {
  assert.equal(postseasonGameName(journey(null), "C", 1), null);
  // 場號 9 的 C 列落在 C2 那天（10/18）＝ G2，不是 G9。
  assert.equal(postseasonGameName(journey([C_ROW(9, "2026-10-18")]), "C", 9), "台灣大賽 G2");
  assert.equal(postseasonGameName(journey(null), "A", 1), null);
  assert.equal(postseasonGameName(null, "E", 4), null);
});

test("日期與時戳只給讀者需要的精度", () => {
  assert.equal(monthDay("2026-10-12"), "10/12");
  assert.equal(taipeiMinute("2026-10-14T04:49:44.916317+00:00"), "2026-10-14 12:49（台北）");
  assert.equal(taipeiMinute(null), null);
  assert.equal(taipeiMinute("不是時間"), "不是時間");
});

test("單場頁公告安排：E 以官方場號＋日期、C 只認同日唯一公告，不以場號猜場序", () => {
  assert.equal(announcedSlotOf(POSTSEASON_2026, "C", 1, "2026-10-17")?.key, "C1");
  assert.equal(announcedSlotOf(POSTSEASON_2026, "C", 9, "2026-10-23")?.conditional, true);
  assert.equal(announcedSlotOf(POSTSEASON_2026, "C", 5, "2026-10-19"), null, "補賽日沒有公告場，不以場號 5 猜 G5");
  assert.equal(announcedSlotOf(POSTSEASON_2026, "E", 4, "2026-10-12")?.start, "18:35");
  assert.equal(announcedSlotOf(POSTSEASON_2026, "E", 3, "2026-10-12"), null);
  assert.equal(announcedSlotOf(null, "C", 1, "2026-10-17"), null);
});

test("N38：完賽季後單場頁在下一場目標解析前不給連結，解析後一次定案", () => {
  const base = { recapHref: "/games/4/report?kind=E&year=2026&tab=overview", backendFinal: true, kind: "E", year: 2026 };
  assert.deepEqual(reportEntry({ ...base, previewHref: undefined }), { pending: true });
  assert.deepEqual(reportEntry({ ...base, previewHref: "/games/1/preview?kind=C&year=2026&tab=overview" }),
    { pending: false, href: "/games/1/preview?kind=C&year=2026&tab=overview", text: "下一場觀戰報告" });
  assert.deepEqual(reportEntry({ ...base, previewHref: null }), { pending: false, href: base.recapHref, text: "場間報告：下一場兩隊背景" });
  // 後端尚未定案（只有頁面層完賽）時不會去解析，直接給場間報告，不會卡在空位。
  assert.equal((reportEntry({ ...base, backendFinal: false, previewHref: undefined }) as { pending: boolean }).pending, false);
  assert.equal(reportEntry({ ...base, recapHref: null, previewHref: undefined }), null);
});
