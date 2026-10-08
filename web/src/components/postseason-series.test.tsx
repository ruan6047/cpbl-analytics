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

test("台灣大賽未定事項：挑戰賽由兄弟拿下後改寫為已確定對手與實際球場", () => {
  const j = build([BRO, BRO], "2026-10-10T23:00:00+08:00");
  const t = text(<PostseasonExplainer journey={j} />);
  assert.match(t, /對手 已確定：兄弟（挑戰賽勝隊）/);
  assert.match(t, /G3、G4 球場 大巨蛋（兄弟主場）/);
  assert.match(t, /本站季後賽果紀錄 2 場/);
});
