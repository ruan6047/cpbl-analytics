import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PostseasonExplainer, PostseasonOverview, SeriesCard, SlotLine } from "./postseason-series.tsx";
import { POSTSEASON_2026, type TeamSlot } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, type JourneyRow, type SeriesGame, type SummarySeries } from "@/lib/postseason-journey.ts";

// #237 季後總覽與 G3／G4 說明的**渲染**測試：判準落在讀者看得到的字與連結上。

const LION = "ADD011";
const BRO = "ACN011";
const NAMES: Record<string, string> = { ADD011: "統一7-ELEVEn獅", ACN011: "中信兄弟", AAA011: "味全龍" };
const nameOf = (c: string | null) => (c ? NAMES[c] ?? c : "");
const seedOf = (c: string | null) => (c === BRO ? "上半季冠軍" : c === LION ? "外卡・全年 #3" : c ? "下半季冠軍" : "");

function text(node: ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

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

test("開打前季後總覽：不稱形勢預測；兄弟規則 1 勝列在「讓」欄並計入大比分；下一場與日曆入口", () => {
  const j = build([], "2026-10-08T12:00:00+08:00");
  const html = renderToStaticMarkup(<PostseasonOverview journey={j} nameOf={nameOf} seedOf={seedOf} />);
  const t = text(<PostseasonOverview journey={j} nameOf={nameOf} seedOf={seedOf} />);
  assert.doesNotMatch(t, /形勢預測/);
  assert.match(t, /公告賽程・依實際賽果/);
  assert.match(t, /5 戰 3 勝：先拿 3 勝晉級台灣大賽/);
  assert.match(t, /兄弟依規則先勝 1 場（不是實際比賽/);
  assert.match(t, /統一 0：兄弟 1（兄弟含規則勝 1）・統一還差 3 勝、兄弟還差 2 勝/);
  assert.match(t, /下一場 季後挑戰賽 G1・10\/09（五） 17:05・統一獅（客）對 中信兄弟（主）・洲際 公告安排/);
  assert.match(html, /href="\/games\?month=2026-10"/);
  assert.match(t, /本站尚無季後賽果紀錄/);
  // 沒有任何資料庫列 → 不得出現單場連結。
  assert.doesNotMatch(html, /href="\/games\/\d/);
});

test("必要回歸（渲染）：獅贏 E1–E2 → 大比分 獅 2、兄弟 1，系列未結束、不顯示晉級", () => {
  const j = build([LION, LION], "2026-10-10T23:00:00+08:00");
  const html = renderToStaticMarkup(<PostseasonOverview journey={j} nameOf={nameOf} seedOf={seedOf} />);
  const t = text(<PostseasonOverview journey={j} nameOf={nameOf} seedOf={seedOf} />);
  assert.match(t, /統一 2：兄弟 1（兄弟含規則勝 1）・統一還差 1 勝、兄弟還差 2 勝/);
  assert.doesNotMatch(t, /晉級台灣大賽(?!。)/, "只有規則說明句可出現「晉級台灣大賽」");
  assert.doesNotMatch(t, /統一晉級台灣大賽|已確定（統一晉級）/);
  // 系列卡逐場欄頭連回原場，連結帶 kind=E 與 year。
  assert.match(html, /href="\/games\/1\?kind=E&amp;year=2026"/);
  assert.match(html, /href="\/games\/2\?kind=E&amp;year=2026"/);
  // 台灣大賽對手仍待定。
  assert.match(t, /挑戰賽勝隊/);
});

test("SeriesCard 既有行為：沒有完賽場時大比分顯示「—」（歷史／預測路徑不變）；當季才開打前顯示 1：0", () => {
  const card = (totals: boolean) => (
    <SeriesCard title="季後挑戰賽" format="5 戰 3 勝" needed={3} nameOf={nameOf} totalsBeforeGames={totals}
      sideA={{ code: BRO, seed: "", handicap: true }} sideB={{ code: LION, seed: "", handicap: false }} />
  );
  assert.equal((text(card(false)).match(/—/g) ?? []).length, 2);
  assert.equal((text(card(true)).match(/—/g) ?? []).length, 0);
});

test("G3／G4 說明：日期時間、挑戰賽勝方球場分支、確認條件、待定與未取得、來源與截至", () => {
  const j = build([], "2026-10-08T12:00:00+08:00");
  const t = text(<PostseasonExplainer journey={j} />);
  assert.match(t, /台灣大賽 G3／G4 與未定場次說明/);
  assert.match(t, /10\/20（二） 18:35、10\/21（三） 18:35，味全龍（客）對 挑戰賽勝隊（主）/);
  assert.match(t, /依挑戰賽勝隊而定：兄弟晉級→大巨蛋／統一晉級→亞太主/);
  assert.match(t, /確認條件：挑戰賽分出勝負後確定。目前： 待定/);
  assert.match(t, /台灣大賽對手：挑戰賽勝隊，挑戰賽分出勝負後確定/);
  assert.match(t, /G5–G7（10\/23（五） 18:35、10\/24（六） 17:05、10\/25（日） 17:05）是否進行：如有必要/);
  assert.match(t, /G5–G7 球場與主客：本站未取得，以官方公告為準/);
  assert.match(t, /10\/19、10\/22：移動補賽日（遇延賽才使用，不是比賽）/);
  assert.match(t, /本站尚無官方台灣大賽場次編號，暫不提供單場連結/);
  assert.match(t, /CPBL 官方 10\/05 公告，本站 10\/06 14:28 取得/);
  assert.match(t, /本站尚無季後賽果紀錄，本站賽果紀錄至 10\/04/);
});

test("G3／G4 說明：挑戰賽由兄弟拿下後改寫為已確定與實際球場", () => {
  const j = build([BRO, BRO], "2026-10-10T23:00:00+08:00");
  const t = text(<PostseasonExplainer journey={j} />);
  assert.match(t, /已確定（兄弟晉級）/);
  assert.match(t, /球場：兄弟晉級，於大巨蛋/);
  assert.match(t, /台灣大賽對手：已確定為兄弟/);
  assert.match(t, /本站季後賽果紀錄 2 場/);
});

test("場次列：公告安排為虛線框無連結；正式場次可點進單場；賽果待更新附截至", () => {
  const announced = build([], "2026-10-08T12:00:00+08:00").slots[0];
  const a = renderToStaticMarkup(<SlotLine s={announced} asOf="2026-10-04" />);
  assert.match(a, /data-announced="true"/);
  assert.doesNotMatch(a, /<a /);

  const row: JourneyRow = {
    year: 2026, kind_code: "E", game_sno: 1, game_date: "2026-10-09", venue: "洲際",
    away_team_code: LION, home_team_code: BRO, away_score: 0, home_score: 0,
  };
  const pending = build([], "2026-10-09T20:00:00+08:00", [row]).slots[0];
  const p = renderToStaticMarkup(<SlotLine s={pending} asOf="2026-10-04" />);
  assert.match(p, /href="\/games\/1\?kind=E&amp;year=2026"/);
  assert.match(text(<SlotLine s={pending} asOf="2026-10-04" />), /賽果待更新 .*已過預定開賽時間・本站尚無賽果紀錄（本站賽果紀錄至 10\/04）/);
});
