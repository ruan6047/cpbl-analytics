import assert from "node:assert/strict";
import test from "node:test";

import { POSTSEASON_2026, announcementFor, type TeamSlot } from "./postseason-announcement.ts";
import {
  buildPostseasonJourney,
  journeyAsOfText,
  latestResultDate,
  postseasonJourneyFor,
  seriesProgressText,
  slotMayInvolve,
  slotStartMs,
  slotWhen,
  type JourneyRow,
  type SeriesGame,
  type SummarySeries,
} from "./postseason-journey.ts";

// #237 季後追賽旅程模型。讓勝固定歸兄弟、歸併只認真實場號、時間狀態以注入的現在時刻判定。
// 「獅贏前兩場」是需求列明的必要回歸（不是已觀測事故）：舊戰績頁以「勝隊場勝＝門檻−1」反推
// 讓勝，會把規則勝誤給獅而顯示晉級。

const LION = "ADD011";
const BRO = "ACN011";
const DRAGON = "AAA011";
const BEFORE = Date.parse("2026-10-08T12:00:00+08:00");
const AFTER_E2 = Date.parse("2026-10-10T23:00:00+08:00");

/** E 第 n 戰的完賽紀錄（主客照公告），winner 決定比分。 */
const codeOf = (t: TeamSlot | null) => (t && "code" in t ? t.code : "");

function eGame(n: number, winner: string): SeriesGame {
  const slot = POSTSEASON_2026.slots.find((s) => s.key === `E${n}`)!;
  const away = codeOf(slot.away);
  const home = codeOf(slot.home);
  return {
    game_no: n, game_sno: n, date: slot.date,
    away_code: away, home_code: home,
    away_score: winner === away ? 5 : 2, home_score: winner === home ? 5 : 2,
  };
}

function summaryE(...winners: string[]): SummarySeries[] {
  if (winners.length === 0) return [];
  return [{ kind_code: "E", team1_code: LION, team2_code: BRO, games: winners.map((w, i) => eGame(i + 1, w)) }];
}

function row(over: Partial<JourneyRow>): JourneyRow {
  return {
    year: 2026, kind_code: "E", game_sno: 1, game_date: "2026-10-09", venue: "洲際",
    away_team_code: LION, home_team_code: BRO, away_score: 0, home_score: 0,
    ...over,
  };
}

function journey(winners: string[], over: { rows?: JourneyRow[] | null; nowMs?: number; dataAsOf?: string | null } = {}) {
  return buildPostseasonJourney({
    announcement: POSTSEASON_2026,
    summary: summaryE(...winners),
    rows: over.rows ?? null,
    nowMs: over.nowMs ?? AFTER_E2,
    dataAsOf: over.dataAsOf ?? null,
  });
}

function side(j: ReturnType<typeof journey>, code: string) {
  const { a, b } = j.series.E.tally;
  return a.code === code ? a : b;
}

const slot = (j: ReturnType<typeof journey>, key: string) => j.slots.find((s) => s.key === key)!;

// —— 系列：讓勝固定、與實際場勝分列 ——

test("開打前：兄弟規則 1 勝、獅 0；兩隊各還差 2／3 勝，系列未開打", () => {
  const j = journey([], { nowMs: BEFORE });
  assert.deepEqual(side(j, BRO), { code: BRO, ruleWins: 1, gameWins: 0, total: 1, remaining: 2 });
  assert.deepEqual(side(j, LION), { code: LION, ruleWins: 0, gameWins: 0, total: 0, remaining: 3 });
  assert.equal(j.series.E.status, "not_started");
  assert.equal(j.series.E.tally.winner, null);
});

test("兄弟贏 E1：兄弟 2（規則 1＋實際 1）、獅 0", () => {
  const j = journey([BRO]);
  assert.equal(side(j, BRO).total, 2);
  assert.equal(side(j, BRO).gameWins, 1);
  assert.equal(side(j, LION).total, 0);
  assert.equal(j.series.E.status, "in_progress");
});

test("獅贏 E1：1：1（兄弟的 1 是規則勝）", () => {
  const j = journey([LION]);
  assert.equal(side(j, LION).total, 1);
  assert.equal(side(j, LION).ruleWins, 0);
  assert.equal(side(j, BRO).total, 1);
  assert.equal(side(j, BRO).gameWins, 0);
  assert.equal(j.series.E.status, "in_progress");
});

test("實際場勝 1：1：兄弟 2、獅 1", () => {
  const j = journey([LION, BRO]);
  assert.equal(side(j, BRO).total, 2);
  assert.equal(side(j, LION).total, 1);
  assert.equal(j.series.E.tally.decided, false);
});

test("必要回歸：獅贏 E1–E2 → 獅 2、兄弟 1，系列未分勝負，不得誤給獅規則勝而晉級", () => {
  const j = journey([LION, LION]);
  assert.deepEqual(side(j, LION), { code: LION, ruleWins: 0, gameWins: 2, total: 2, remaining: 1 });
  assert.deepEqual(side(j, BRO), { code: BRO, ruleWins: 1, gameWins: 0, total: 1, remaining: 2 });
  assert.equal(j.series.E.tally.decided, false);
  assert.equal(j.series.E.tally.winner, null);
  assert.equal(j.series.E.status, "in_progress");
  // 條件場仍要進行；台灣大賽對手仍待定。
  assert.equal(slot(j, "E3").status, "announced");
  assert.equal(slot(j, "E4").status, "announced");
  assert.equal(slot(j, "C1").awayCode, null);
  assert.equal(slot(j, "C1").awayLabel, "挑戰賽勝隊");
  const text = seriesProgressText(j.series.E);
  assert.match(text, /統一 2：兄弟 1/);
  assert.match(text, /兄弟含規則勝 1/);
  assert.doesNotMatch(text, /晉級/);
});

test("兄弟贏 E1–E2：3 勝晉級；E3／E4 依條件不需進行；C 對手與 G3／G4 球場填入", () => {
  const j = journey([BRO, BRO]);
  assert.equal(j.series.E.status, "decided");
  assert.equal(j.series.E.tally.winner, BRO);
  assert.equal(side(j, BRO).total, 3);
  assert.equal(slot(j, "E3").status, "not_needed");
  assert.equal(slot(j, "E4").status, "not_needed");
  assert.equal(slot(j, "C1").awayCode, BRO);
  assert.equal(slot(j, "C3").homeCode, BRO);
  assert.equal(slot(j, "C3").venue, "大巨蛋");
  assert.equal(slot(j, "C3").venueNote, null);
  assert.match(seriesProgressText(j.series.E), /兄弟晉級台灣大賽/);
});

test("獅贏 E1–E3：獅晉級，G3／G4 改在亞太主", () => {
  const j = journey([LION, LION, LION], { nowMs: Date.parse("2026-10-11T23:00:00+08:00") });
  assert.equal(j.series.E.tally.winner, LION);
  assert.equal(slot(j, "E4").status, "not_needed");
  assert.equal(slot(j, "C3").homeCode, LION);
  assert.equal(slot(j, "C3").venue, "亞太主");
});

test("比分相同不算任何一方勝場，記為異常", () => {
  const tie: SeriesGame = { ...eGame(1, LION), away_score: 3, home_score: 3 };
  const j = buildPostseasonJourney({
    announcement: POSTSEASON_2026, rows: null, nowMs: AFTER_E2, dataAsOf: null,
    summary: [{ kind_code: "E", team1_code: LION, team2_code: BRO, games: [tie] }],
  });
  assert.equal(j.series.E.tally.ties, 1);
  assert.equal(side(j, LION).gameWins, 0);
  assert.equal(side(j, BRO).gameWins, 0);
});

// —— 歸併與連結 ——

test("沒有資料庫列：全部是公告安排、沒有任何單場連結", () => {
  const j = journey([], { nowMs: BEFORE });
  assert.ok(j.slots.every((s) => s.href === null && s.row === null));
  assert.ok(j.slots.every((s) => s.status === "announced"));
  assert.equal(j.next?.key, "E1");
  assert.equal(j.remaining, true);
});

test("E 列：場號與主客一致才歸併，連結帶 kind=E 與 year；同號 A 列不被採用", () => {
  const rows = [
    row({ kind_code: "A", game_sno: 1, game_date: "2026-10-09", away_team_code: LION, home_team_code: BRO }),
    row({ kind_code: "E", game_sno: 1 }),
  ];
  const j = journey([], { rows, nowMs: BEFORE });
  assert.equal(slot(j, "E1").href, "/games/1?kind=E&year=2026");
  assert.equal(slot(j, "E1").status, "scheduled");
  assert.equal(slot(j, "E2").href, null);
  // 只有 A 列時不建連結。
  const onlyA = journey([], { rows: [rows[0]], nowMs: BEFORE });
  assert.equal(slot(onlyA, "E1").href, null);
  assert.equal(slot(onlyA, "E1").status, "announced");
});

test("E 列主客與公告不符：不歸併、標已異動", () => {
  const j = journey([], { rows: [row({ away_team_code: BRO, home_team_code: LION })], nowMs: BEFORE });
  assert.equal(slot(j, "E1").href, null);
  assert.match(slot(j, "E1").changeNote ?? "", /已異動/);
});

test("E 列改期：以資料庫日期為準並註記公告原定", () => {
  const j = journey([], { rows: [row({ game_date: "2026-10-10" })], nowMs: BEFORE });
  assert.equal(slot(j, "E1").date, "2026-10-10");
  assert.equal(slot(j, "E1").changeNote, "公告原定 10/09");
});

test("summary 完賽場本身就是資料庫列：calendar 取不到時仍能連回原場", () => {
  const j = journey([LION], { rows: null });
  assert.equal(slot(j, "E1").status, "final");
  assert.deepEqual(slot(j, "E1").score, { away: 5, home: 2 });
  assert.equal(slot(j, "E1").href, "/games/1?kind=E&year=2026");
});

test("summary 沒有 game_sno（舊版 API）：照算系列，但不建連結", () => {
  const g = { ...eGame(1, LION) };
  delete g.game_sno;
  const j = buildPostseasonJourney({
    announcement: POSTSEASON_2026, rows: null, nowMs: AFTER_E2, dataAsOf: null,
    summary: [{ kind_code: "E", team1_code: LION, team2_code: BRO, games: [g] }],
  });
  assert.equal(side(j, LION).total, 1);
  assert.equal(slot(j, "E1").status, "final", "以日期＋主客認出完賽，不誤標賽果待更新");
  assert.equal(slot(j, "E1").href, null);
});

test("沒有 C 列：C 全部無連結，不由 Game 1 推場號", () => {
  const j = journey([BRO, BRO]);
  assert.ok(j.slots.filter((s) => s.kind === "C").every((s) => s.href === null));
});

test("有 C 列：以日期對應並帶 kind=C；同日兩列不對應、標已異動", () => {
  const c1 = row({ kind_code: "C", game_sno: 1, game_date: "2026-10-17", away_team_code: BRO, home_team_code: DRAGON, venue: "大巨蛋" });
  const j = journey([BRO, BRO], { rows: [c1] });
  assert.equal(slot(j, "C1").href, "/games/1?kind=C&year=2026");
  assert.equal(slot(j, "C2").href, null);
  assert.equal(slot(j, "C2").changeNote, null);

  const dup = journey([BRO, BRO], { rows: [c1, { ...c1, game_sno: 2 }] });
  assert.equal(slot(dup, "C1").href, null);
  assert.match(slot(dup, "C1").changeNote ?? "", /已異動/);
});

test("C 列落在公告沒有的日期（延賽改期）：對不上的公告格標已異動", () => {
  const moved = row({ kind_code: "C", game_sno: 1, game_date: "2026-10-19", away_team_code: BRO, home_team_code: DRAGON });
  const j = journey([BRO, BRO], { rows: [moved] });
  assert.match(slot(j, "C1").changeNote ?? "", /已異動/);
  assert.equal(slot(j, "C1").href, null);
});

// —— 時間狀態（注入現在時刻；與 TZ 無關） ——

test("已過預定開賽時間、沒有賽果：賽果待更新；有資料庫列時仍可連結", () => {
  const at = Date.parse("2026-10-09T18:00:00+08:00");
  const j = journey([], { nowMs: at });
  assert.equal(slot(j, "E1").status, "result_pending");
  assert.equal(slot(j, "E1").href, null);
  assert.equal(slot(j, "E2").status, "announced");
  assert.equal(j.next?.key, "E2", "下一場先找還沒到開賽時間的");

  const withRow = journey([], { nowMs: at, rows: [row({})] });
  assert.equal(slot(withRow, "E1").status, "result_pending");
  assert.equal(slot(withRow, "E1").href, "/games/1?kind=E&year=2026");
});

test("開賽時刻以台北解讀，不吃執行環境時區", () => {
  assert.equal(slotStartMs("2026-10-09", "17:05"), Date.parse("2026-10-09T09:05:00Z"));
  assert.equal(slotWhen({ date: "2026-10-09", start: "17:05" }), "10/09（五） 17:05");
  assert.equal(slotWhen({ date: "2026-10-20", start: "18:35" }), "10/20（二） 18:35");
});

test("資料不足不得稱全季結束：公告仍有未完成場次就 remaining", () => {
  const late = Date.parse("2026-10-30T12:00:00+08:00");
  const j = journey([BRO, BRO], { nowMs: late });
  assert.equal(j.remaining, true);
  assert.ok(j.slots.some((s) => s.status === "result_pending"));
});

// —— 公告內容與三入口一致 ——

test("公告：E 四場日期時間、E3／E4 如有必要、C 七個日期、兩個移動補賽日", () => {
  const e = POSTSEASON_2026.slots.filter((s) => s.kind === "E");
  assert.deepEqual(e.map((s) => [s.date, s.start, s.conditional]), [
    ["2026-10-09", "17:05", false], ["2026-10-10", "17:05", false],
    ["2026-10-11", "17:05", true], ["2026-10-12", "18:35", true],
  ]);
  const c = POSTSEASON_2026.slots.filter((s) => s.kind === "C");
  assert.deepEqual(c.map((s) => s.date.slice(5)), ["10-17", "10-18", "10-20", "10-21", "10-23", "10-24", "10-25"]);
  assert.deepEqual(c.filter((s) => s.conditional).map((s) => s.seq), [5, 6, 7]);
  assert.deepEqual(POSTSEASON_2026.reserveDays.map((d) => d.date), ["2026-10-19", "2026-10-22"]);
  assert.equal(POSTSEASON_2026.series.E.handicapTeam, BRO);
  assert.equal(announcementFor(2025), null, "沒有公告的年份走原路徑");
});

test("同樣輸入得到同一份場次清單（三入口共用同一函式）", () => {
  const rows = [row({}), row({ kind_code: "A", game_sno: 300, game_date: "2026-10-04" })];
  const a = postseasonJourneyFor(2026, summaryE(LION), rows, AFTER_E2);
  const b = postseasonJourneyFor(2026, summaryE(LION), rows, AFTER_E2);
  assert.deepEqual(a, b);
  assert.equal(postseasonJourneyFor(2025, null, rows, AFTER_E2), null);
});

test("日曆篩隊：未定席位以可能參賽隊判斷", () => {
  const j = journey([], { nowMs: BEFORE });
  assert.equal(slotMayInvolve(j, slot(j, "C1"), LION), true);
  assert.equal(slotMayInvolve(j, slot(j, "C5"), DRAGON), true);
  assert.equal(slotMayInvolve(j, slot(j, "C5"), "AEO011"), false);
  assert.equal(slotMayInvolve(j, slot(j, "E1"), DRAGON), false);
  const decided = journey([BRO, BRO]);
  assert.equal(slotMayInvolve(decided, slot(decided, "C1"), LION), false);
});

test("資料截至：取最近一筆有比分的場次；文案分辨有無季後紀錄", () => {
  assert.equal(latestResultDate([
    { game_date: "2026-10-04", away_score: 3, home_score: 1 },
    { game_date: "2026-10-09", away_score: 0, home_score: 0 },
  ]), "2026-10-04");
  assert.equal(journeyAsOfText({ recordedGames: 0, dataAsOf: "2026-10-04" }), "本站尚無季後賽果紀錄，本站賽果紀錄至 10/04");
  assert.equal(journeyAsOfText({ recordedGames: 2, dataAsOf: "2026-10-10" }), "本站季後賽果紀錄 2 場，本站賽果紀錄至 10/10");
});
