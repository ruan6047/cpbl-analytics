import assert from "node:assert/strict";
import test from "node:test";

import { POSTSEASON_2026, announcementFor, type TeamSlot } from "./postseason-announcement.ts";
import {
  buildPostseasonJourney,
  journeyAsOfText,
  latestResultDate,
  liveEntryProbes,
  liveEntryResults,
  postseasonJourneyFor,
  seriesProgressText,
  slotMayInvolve,
  slotStartMs,
  slotWhen,
  withLiveEntries,
  type JourneyRow,
  type LiveEntryStatus,
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
  assert.match(text, /（兄弟實際勝 0＋規則勝 1）/);
  assert.doesNotMatch(text, /統一實際勝/, "沒有規則勝的一方合計即實際勝場，不另列");
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
  // R1 F1 回歸：首頁摘要直接讀到實際 2 勝，不只合計 3 與規則勝 1。
  assert.equal(seriesProgressText(j.series.E), "統一 0：兄弟 3（兄弟實際勝 2＋規則勝 1）・兄弟晉級台灣大賽");
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

test("公告 G5–G7（10/08 核對官網）：挑戰賽勝隊為客、味全龍為主、大巨蛋、如有必要；無 C 列不建連結", () => {
  const j = journey([], { nowMs: BEFORE });
  for (const key of ["C5", "C6", "C7"]) {
    const s = slot(j, key);
    assert.equal(s.awayCode, null);
    assert.equal(s.awayLabel, "挑戰賽勝隊");
    assert.equal(s.homeCode, DRAGON);
    assert.equal(s.venue, "大巨蛋");
    assert.equal(s.venueNote, null);
    assert.equal(s.conditional, true);
    assert.equal(s.href, null);
  }
  assert.deepEqual(["C5", "C6", "C7"].map((k) => [slot(j, k).date, slot(j, k).start]), [
    ["2026-10-23", "18:35"], ["2026-10-24", "17:05"], ["2026-10-25", "17:05"],
  ]);
  // 挑戰賽分出勝負後，客隊填入勝隊；球場仍是大巨蛋（味全主場）。
  const decided = journey([BRO, BRO]);
  assert.equal(slot(decided, "C5").awayCode, BRO);
  assert.equal(slot(decided, "C5").venue, "大巨蛋");
  const check = POSTSEASON_2026.source.checks.find((c) => c.scope === "announcement");
  assert.equal(check?.ok, true);
  assert.equal(check?.on, "2026-10-08");
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

test("#237 資料截至：2026 E 賽中部分比分不算完賽紀錄；歷史 E 照舊", () => {
  const a = { kind_code: "A", year: 2026, game_date: "2026-10-04", away_score: 3, home_score: 1 };
  const e1 = { kind_code: "E", year: 2026, game_date: "2026-10-09", away_score: 0, home_score: 3 };
  assert.equal(latestResultDate([a, { ...e1, completed: false }]), "2026-10-04");
  assert.equal(latestResultDate([a, e1]), "2026-10-04");
  assert.equal(latestResultDate([a, { ...e1, completed: true }]), "2026-10-09");
  assert.equal(latestResultDate([a, { ...e1, year: 2025, game_date: "2025-10-11" }, { ...a, game_date: "2025-10-01" }]), "2026-10-04");
  assert.equal(latestResultDate([{ ...e1, year: 2025, game_date: "2025-10-11" }]), "2025-10-11");
});

// —— 單場賽況入口（#237）：資料庫還沒有 E 列時，只依公告場號查單場狀態補「連結」 ——
// 狀態回應的欄位形狀取自 19:25 官方 raw 經 build_snapshot 的實際輸出（RECORDED 形狀）；
// 各測試的數值是 SYNTHETIC，只用來覆蓋身分比對的每一個條件。

const DURING_E1 = Date.parse("2026-10-09T19:25:00+08:00");

type Snap = Record<string, unknown>;
function entryStatus(over: Snap = {}, top: Snap = {}): LiveEntryStatus {
  const snap: Snap = {
    game_id: "2026-E-1", game_sno: 1, kind_code: "E", phase: "live", starts_at: "2026-10-09T17:05:00",
    away: { team: { code: LION, name: "統一7-ELEVEn獅" } }, home: { team: { code: BRO, name: "中信兄弟" } },
    ...over,
  };
  return { season: 2026, kind_code: "E", game_sno: 1, canonical_phase: snap.phase, live_snapshot: snap, ...top } as unknown as LiveEntryStatus;
}

const withE1 = (j: ReturnType<typeof journey>, st: LiveEntryStatus) => withLiveEntries(j, { E1: st });

test("單場入口：只對公告有官方場號、資料庫沒有列的 E 場次查詢，最多 4 場；C 不查", () => {
  const j = journey([], { nowMs: DURING_E1 });
  assert.deepEqual(liveEntryProbes(j), [
    { key: "E1", kind: "E", sno: 1 }, { key: "E2", kind: "E", sno: 2 },
    { key: "E3", kind: "E", sno: 3 }, { key: "E4", kind: "E", sno: 4 },
  ]);
  const withRow = journey([], { rows: [row({})], nowMs: DURING_E1 });
  assert.deepEqual(liveEntryProbes(withRow).map((p) => p.key), ["E2", "E3", "E4"], "資料庫有列的場次不查");
  const decided = journey([BRO, BRO]);
  assert.ok(liveEntryProbes(decided).every((p) => p.kind === "E"));
  assert.ok(!liveEntryProbes(decided).some((p) => slot(decided, p.key).status === "not_needed"), "依條件不需進行的場次不查");
});

test("單場入口：身分全部相符才給連結，狀態與系列不變", () => {
  const base = journey([], { nowMs: DURING_E1, dataAsOf: "2026-10-04" });
  const j = withE1(base, entryStatus());
  assert.equal(slot(j, "E1").href, "/games/1?kind=E&year=2026");
  assert.equal(slot(j, "E1").liveEntry, true);
  assert.equal(slot(j, "E1").status, "result_pending");
  assert.equal(slot(j, "E1").row, null);
  assert.equal(slot(j, "E1").score, null);
  assert.equal(slot(base, "E1").liveEntry, false);
  assert.ok(j.slots.filter((s) => s.key !== "E1").every((s) => s.href === null && !s.liveEntry));
  assert.equal(j.next?.key, base.next?.key);
});

test("單場入口：任一身分條件不符、無快照或狀態未知都不給連結", () => {
  const base = journey([], { nowMs: DURING_E1 });
  const cases: [string, LiveEntryStatus][] = [
    ["無回應", null],
    ["無快照", entryStatus({}, { live_snapshot: null })],
    ["game_id 不符", entryStatus({ game_id: "2026-E-2" })],
    ["場號不符", entryStatus({ game_sno: 2 })],
    ["賽別是 C", entryStatus({ kind_code: "C", game_id: "2026-C-1" })],
    ["主客對調", entryStatus({ away: { team: { code: BRO, name: "" } }, home: { team: { code: LION, name: "" } } })],
    ["客隊錯", entryStatus({ away: { team: { code: DRAGON, name: "" } } })],
    ["缺隊伍", entryStatus({ home: null })],
    ["日期不符", entryStatus({ starts_at: "2026-10-10T17:05:00" })],
    ["開賽時刻帶 Z", entryStatus({ starts_at: "2026-10-09T09:05:00Z" })],
    ["沒有開賽時刻", entryStatus({ starts_at: null })],
    ["狀態 unknown", entryStatus({ phase: "unknown" })],
    ["狀態不在清單", entryStatus({ phase: "bogus" })],
    ["回應年度不符", entryStatus({}, { season: 2025 })],
    ["回應賽別不符", entryStatus({}, { kind_code: "A" })],
    ["回應場號不符", entryStatus({}, { game_sno: 2 })],
    ["canonical_phase 與快照不一致", entryStatus({}, { canonical_phase: "final" })],
  ];
  for (const [name, st] of cases) {
    const j = withE1(base, st);
    assert.equal(slot(j, "E1").href, null, name);
    assert.equal(slot(j, "E1").liveEntry, false, name);
  }
});

test("單場入口：快照 final 也不計勝場、不改截至、不改狀態（與無快照逐值相同）", () => {
  const base = journey([], { nowMs: DURING_E1, dataAsOf: "2026-10-04" });
  const fin = withE1(base, entryStatus({ phase: "final" }));
  const none = withE1(base, null);
  assert.equal(slot(fin, "E1").href, "/games/1?kind=E&year=2026", "final 仍可點入單場頁看終場");
  assert.deepEqual(fin.series, none.series);
  assert.equal(fin.recordedGames, none.recordedGames);
  assert.equal(fin.dataAsOf, none.dataAsOf);
  assert.equal(fin.remaining, none.remaining);
  assert.deepEqual(fin.slots.map((s) => [s.key, s.status, s.score]), none.slots.map((s) => [s.key, s.status, s.score]));
  assert.equal(journeyAsOfText(fin), journeyAsOfText(none));
  assert.equal(seriesProgressText(fin.series.E), seriesProgressText(none.series.E));
});

test("單場入口：資料庫有列時沿用資料庫連結，快照一律忽略、不重複", () => {
  const base = journey([], { rows: [row({})], nowMs: DURING_E1 });
  const j = withE1(base, entryStatus({ phase: "final" }));
  assert.equal(slot(j, "E1").href, "/games/1?kind=E&year=2026");
  assert.equal(slot(j, "E1").liveEntry, false);
  assert.equal(slot(j, "E1").row, slot(base, "E1").row);
  assert.equal(slot(j, "E1").status, slot(base, "E1").status);
});

test("單場入口：C 場次即使給了快照也不建連結；沒有公告的年份不建模型", () => {
  const base = journey([BRO, BRO]);
  const j = withLiveEntries(base, { C1: entryStatus({ game_id: "2026-C-1", kind_code: "C" }, { kind_code: "C" }) });
  assert.ok(j.slots.filter((s) => s.kind === "C").every((s) => s.href === null && !s.liveEntry));
  assert.equal(postseasonJourneyFor(2025, null, null, DURING_E1), null);
});

test("單場入口：結果整併只取 fulfilled，rejected 視同無回應", () => {
  const probes = [{ key: "E1", kind: "E" as const, sno: 1 }, { key: "E2", kind: "E" as const, sno: 2 }];
  const got = liveEntryResults(probes, [
    { status: "fulfilled", value: entryStatus() },
    { status: "rejected", reason: new Error("x") },
  ]);
  assert.deepEqual(Object.keys(got), ["E1", "E2"]);
  assert.equal(got.E2, null);
  assert.notEqual(got.E1, null);
});
