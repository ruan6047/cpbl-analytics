import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PostseasonOverview } from "./postseason-overview.tsx";
import { POSTSEASON_2026, type TeamSlot } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, type JourneyRow, type SeriesGame, type SummarySeries } from "@/lib/postseason-journey.ts";

// #237 當季季後總覽：挑戰賽與台灣大賽分開兩個分頁（需求方 2026-10-08），每頁只有一套進度與賽程，
// 同一資訊只出現在一個位置。判準落在讀者看得到的字、次數與連結上。

const LION = "ADD011";
const BRO = "ACN011";
const NAMES: Record<string, string> = { ADD011: "統一7-ELEVEn獅", ACN011: "中信兄弟", AAA011: "味全龍" };
const nameOf = (c: string | null) => (c ? NAMES[c] ?? c : "");
const seedOf = (c: string | null) => (c === BRO ? "下半季冠軍" : c === LION ? "外卡・全年 #2" : c ? "上半季冠軍" : "");

function text(node: ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}
const count = (t: string, s: string) => t.split(s).length - 1;

function eGame(n: number, winner: string): SeriesGame {
  const s = POSTSEASON_2026.slots.find((x) => x.key === `E${n}`)!;
  const codeOf = (t: TeamSlot | null) => (t && "code" in t ? t.code : "");
  const away = codeOf(s.away);
  const home = codeOf(s.home);
  return {
    game_no: n, game_sno: n, date: s.date, away_code: away, home_code: home,
    away_score: winner === away ? 4 : 1, home_score: winner === home ? 4 : 1,
  };
}

function build(winners: string[], nowIso: string, rows: JourneyRow[] | null = null) {
  const summary: SummarySeries[] = winners.length
    ? [{ kind_code: "E", team1_code: LION, team2_code: BRO, games: winners.map((w, i) => eGame(i + 1, w)) }]
    : [];
  return buildPostseasonJourney({
    announcement: POSTSEASON_2026, summary, rows, nowMs: Date.parse(nowIso), dataAsOf: "2026-10-04",
  });
}
const view = (j: ReturnType<typeof build>, active?: string) =>
  <PostseasonOverview journey={j} nameOf={nameOf} seedOf={seedOf} active={active} />;

test("開打前預設挑戰賽分頁：進度（規則勝另註）、晉級關係、只列挑戰賽四場；不稱形勢預測、沒有假連結", () => {
  const j = build([], "2026-10-08T12:00:00+08:00");
  const html = renderToStaticMarkup(view(j));
  const t = text(view(j));
  assert.doesNotMatch(t, /形勢預測/);
  assert.match(html, /aria-current="page"[^>]*href="\/standings\?seg=3&amp;ps=E"|href="\/standings\?seg=3&amp;ps=E"[^>]*aria-current="page"/);
  assert.match(t, /季後挑戰賽 5 戰 3 勝 中信兄弟/);
  assert.equal(count(t, "晉級台灣大賽"), 1, "門檻與去向只在晉級關係句說一次");
  assert.match(t, /中信兄弟 下半季冠軍 1 還差 2 勝/);
  assert.match(t, /統一獅 外卡・全年 #2 0 還差 3 勝/);
  assert.match(t, /■ 規則勝：兄弟依規則先得 1 勝，不是實際比賽/);
  assert.match(t, /先拿 3 勝晉級台灣大賽，10\/17（六） 起對味全。 看台灣大賽 →/);
  assert.match(t, /G1 10\/09（五） 17:05 下一場 統一獅（客） 對 中信兄弟（主） ・洲際/);
  assert.match(t, /G3 10\/11（日） 17:05 如有必要/);
  assert.doesNotMatch(t, /10\/23|大巨蛋/, "台灣大賽賽程不出現在挑戰賽分頁");
  assert.doesNotMatch(html, /href="\/games\/\d/);
  assert.match(html, /href="\/games\?month=2026-10"/);
});

test("台灣大賽分頁：G5–G7 為挑戰賽勝隊（客）對味全龍（主）、大巨蛋、如有必要；G3／G4 球場分支只寫一次；補賽日排入賽程", () => {
  const j = build([], "2026-10-08T12:00:00+08:00");
  const html = renderToStaticMarkup(view(j, "C"));
  const t = text(view(j, "C"));
  assert.match(t, /台灣大賽 7 戰 4 勝 味全龍/);
  assert.match(t, /味全龍 上半季冠軍・保送 0 還差 4 勝/);
  assert.match(t, /挑戰賽勝隊 挑戰賽分出勝負後確定 0 待定/);
  assert.match(t, /味全直接晉級，對手由季後挑戰賽決定；先拿 4 勝奪得總冠軍。 看季後挑戰賽 →/);
  for (const [g, day] of [["G5", "10/23（五） 18:35"], ["G6", "10/24（六） 17:05"], ["G7", "10/25（日） 17:05"]]) {
    assert.match(t, new RegExp(`${g} ${day} 如有必要 挑戰賽勝隊（客） 對 味全龍（主） ・大巨蛋`));
  }
  assert.match(t, /G3 10\/20（二） 18:35 味全龍（客） 對 挑戰賽勝隊（主） ・球場依挑戰賽勝隊而定/);
  assert.equal(count(t, "兄弟晉級→大巨蛋／統一晉級→亞太主"), 1, "G3／G4 球場分支只在清單下方說一次");
  assert.match(t, /G3、G4 球場 ：依挑戰賽勝隊而定：兄弟晉級→大巨蛋／統一晉級→亞太主/);
  assert.match(t, /G2 10\/18（日） 17:05 .*10\/19（一） 移動補賽日（遇延賽才使用，不是比賽） G3 10\/20/);
  assert.doesNotMatch(t, /本站未取得|統一獅（客）/, "不出現挑戰賽場次列");
  assert.doesNotMatch(html, /href="\/games\/\d/, "沒有官方台灣大賽場號，不建單場連結");
});

test("去重：每個分頁只有一處資訊截至、一處「如有必要」定義、一個下一場標記；沒有另一系列的清單", () => {
  const j = build([], "2026-10-08T12:00:00+08:00");
  const e = text(view(j, "E"));
  const c = text(view(j, "C"));
  for (const t of [e, c]) {
    assert.equal(count(t, "本站賽果紀錄至"), 1);
    assert.equal(count(t, "＝系列尚未分出勝負才進行"), 1);
    assert.equal(count(t, "公告安排"), 1, "只有清單下方一句，場次列不逐列掛徽章");
  }
  assert.equal(count(e, "下一場"), 1);
  assert.equal(count(c, "下一場"), 0, "下一場在挑戰賽，台灣大賽分頁不重複");
  assert.equal(count(e, "如有必要"), 3);
  assert.equal(count(c, "如有必要"), 4);
});

test("必要回歸：獅贏 E1–E2 → 統一 2、兄弟 1，兩隊都還沒晉級；完賽列連回原場", () => {
  const j = build([LION, LION], "2026-10-10T23:00:00+08:00");
  const html = renderToStaticMarkup(view(j));
  const t = text(view(j));
  assert.match(t, /中信兄弟 下半季冠軍 1 還差 2 勝/);
  assert.match(t, /統一獅 外卡・全年 #2 2 還差 1 勝/);
  assert.doesNotMatch(t, /統一晉級|兄弟晉級|統一獅 外卡・全年 #2 2 晉級/);
  assert.match(t, /G1 10\/09（五） 17:05 終場 統一獅（客） 4：1 中信兄弟（主）/);
  assert.match(html, /href="\/games\/1\?kind=E&amp;year=2026"/);
  assert.match(html, /href="\/games\/2\?kind=E&amp;year=2026"/);
  assert.match(t, /G3 10\/11（日） 17:05 下一場 如有必要/);
});

test("挑戰賽分出勝負：預設改到台灣大賽分頁、對手與 G3／G4 球場填入；挑戰賽分頁標晉級與不需進行", () => {
  const j = build([BRO, BRO], "2026-10-10T23:00:00+08:00");
  const c = text(view(j));
  assert.match(c, /中信兄弟 季後挑戰賽勝隊 0 還差 4 勝/);
  assert.match(c, /味全直接晉級，對手為兄弟；先拿 4 勝奪得總冠軍。/);
  assert.match(c, /G3 10\/20（二） 18:35 味全龍（客） 對 中信兄弟（主） ・大巨蛋/);
  assert.doesNotMatch(c, /球場依挑戰賽勝隊而定|G3、G4 球場/);
  assert.match(c, /G1 10\/17（六） 17:05 下一場/);
  const e = text(view(j, "E"));
  assert.match(e, /中信兄弟 下半季冠軍 3 晉級/);
  assert.match(e, /兄弟晉級台灣大賽，10\/17（六） 起對味全。/);
  assert.match(e, /G3 10\/11（日） 17:05 依條件不需進行/);
});

test("已過開賽時間仍無賽果：該列標賽果待更新與截至；有資料庫列時可點進單場", () => {
  const row: JourneyRow = {
    year: 2026, kind_code: "E", game_sno: 1, game_date: "2026-10-09", venue: "洲際",
    away_team_code: LION, home_team_code: BRO, away_score: 0, home_score: 0,
  };
  const j = build([], "2026-10-09T20:00:00+08:00", [row]);
  const html = renderToStaticMarkup(view(j));
  const t = text(view(j));
  assert.match(html, /href="\/games\/1\?kind=E&amp;year=2026"/);
  assert.match(t, /G1 10\/09（五） 17:05 賽果待更新 .*已過預定開賽時間・本站尚無賽果紀錄（本站賽果紀錄至 10\/04）/);
  assert.match(t, /G2 10\/10（六） 17:05 下一場/);
});
