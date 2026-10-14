import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PostseasonExplainer, SeriesCard } from "./postseason-series.tsx";
import { POSTSEASON_2026, type TeamSlot } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, type SeriesGame, type SummarySeries } from "@/lib/postseason-journey.ts";

// #237 系列卡（歷史年份／二軍）與台灣大賽未定說明（日曆）的渲染測試。當季總覽見 postseason-overview.test.tsx。

const LION = "ADD011";
const BRO = "ACN011";
const NAMES: Record<string, string> = { ADD011: "統一7-ELEVEn獅", ACN011: "中信兄弟", AAA011: "味全龍" };
const nameOf = (c: string | null) => (c ? NAMES[c] ?? c : "");

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

function build(winners: string[], nowIso: string) {
  const summary: SummarySeries[] = winners.length
    ? [{ kind_code: "E", team1_code: LION, team2_code: BRO, games: winners.map((w, i) => eGame(i + 1, w)) }]
    : [];
  return buildPostseasonJourney({
    announcement: POSTSEASON_2026, summary, rows: null, nowMs: Date.parse(nowIso), dataAsOf: "2026-10-04",
  });
}

test("SeriesCard 既有行為：沒有完賽場時大比分顯示「—」（歷史／預測路徑不變）；當季才開打前顯示 1：0", () => {
  const card = (totals: boolean) => (
    <SeriesCard title="季後挑戰賽" format="5 戰 3 勝" needed={3} nameOf={nameOf} totalsBeforeGames={totals}
      sideA={{ code: BRO, seed: "", handicap: true }} sideB={{ code: LION, seed: "", handicap: false }} />
  );
  assert.equal((text(card(false)).match(/—/g) ?? []).length, 2);
  assert.equal((text(card(true)).match(/—/g) ?? []).length, 0);
});

test("台灣大賽未定事項：只寫場次列寫不下的對手條件與 G3／G4 球場分支；來源收在可展開區", () => {
  const j = build([], "2026-10-08T12:00:00+08:00");
  const node = <PostseasonExplainer journey={j} />;
  const t = text(node);
  assert.match(t, /台灣大賽未定事項 對手 挑戰賽勝隊，挑戰賽分出勝負後確定/);
  assert.match(t, /G3、G4 球場 依挑戰賽勝隊而定：兄弟晉級→大巨蛋／統一晉級→亞太主/);
  // G5–G7 已由官方公告確定（大巨蛋），不再列為未定。
  assert.doesNotMatch(t, /G5|本站未取得/);
  assert.match(t, /本站尚無季後賽果紀錄，本站賽果紀錄至 10\/04/);
  const html = renderToStaticMarkup(node);
  const details = /<details[^>]*>([\s\S]*?)<\/details>/.exec(html)?.[1] ?? "";
  assert.match(details, /<summary[^>]*>資料來源與單場連結<\/summary>/);
  assert.match(details, /本站尚無官方台灣大賽場次編號，暫不提供單場連結/);
  assert.match(details, /CPBL 官方 10\/05 公告，本站 10\/06 14:28 取得，10\/08 重新核對官網公告/);
  assert.doesNotMatch(html, /<details[^>]*\bopen\b/);
  assert.doesNotMatch(text(<PostseasonExplainer journey={j} showAsOf={false} />), /本站賽果紀錄至/);
});

// #268 N14（#273 盤點轉入）：挑戰賽分出勝負後，舊版把這塊改寫成「對手 已確定：兄弟（挑戰賽勝隊）」
// 「G3、G4 球場 大巨蛋（兄弟主場）」——標題仍是「未定事項」，內容卻全是已定，且「主場」是本站推論。
// 舊碼在下面兩種輸入都會畫出那兩行，所以本測試在舊碼下失敗。
test("台灣大賽未定事項：挑戰賽分出勝負、G3／G4 球場已依晉級隊決定後沒有未定事項，整塊不畫", () => {
  // 尚無 C 資料庫列（公告推定球場）。
  const noRows = build([BRO, BRO], "2026-10-10T23:00:00+08:00");
  assert.equal(renderToStaticMarkup(<PostseasonExplainer journey={noRows} />), "");
  // C 資料庫列已入庫（正式場次，球場與主客取自列；值為合成，不是官方核對結果）。
  const cRows = POSTSEASON_2026.slots.filter((s) => s.kind === "C").map((s, i) => ({
    year: 2026, kind_code: "C", game_sno: i + 1, game_date: s.date, venue: "合成球場",
    away_team_code: s.seq === 3 || s.seq === 4 ? "AAA011" : BRO,
    home_team_code: s.seq === 3 || s.seq === 4 ? BRO : "AAA011",
    away_score: 0, home_score: 0, completed: false,
  }));
  const withRows = buildPostseasonJourney({
    announcement: POSTSEASON_2026,
    summary: [{ kind_code: "E", team1_code: LION, team2_code: BRO, games: [eGame(1, BRO), eGame(2, BRO)] }],
    rows: cRows, nowMs: Date.parse("2026-10-14T12:00:00+08:00"), dataAsOf: "2026-10-12",
  });
  const html = renderToStaticMarkup(<PostseasonExplainer journey={withRows} className="mt-6" />);
  assert.equal(html, "");
  assert.doesNotMatch(html, /已確定|主場/);
});

test("台灣大賽未定事項：挑戰賽未分勝負時仍列對手與 G3／G4 球場分支，可帶外距 class", () => {
  const j = build([LION], "2026-10-09T23:00:00+08:00");
  const html = renderToStaticMarkup(<PostseasonExplainer journey={j} className="mt-6" />);
  assert.match(html, /<section[^>]*class="[^"]*\bmt-6"/);
  const t = text(<PostseasonExplainer journey={j} />);
  assert.match(t, /對手 挑戰賽勝隊，挑戰賽分出勝負後確定/);
  assert.match(t, /G3、G4 球場 依挑戰賽勝隊而定/);
  assert.doesNotMatch(t, /已確定|主場）/);
});
