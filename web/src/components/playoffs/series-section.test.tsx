import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { SeriesSection } from "./series-section.tsx";
import { cardStatus, mvpText, seriesSentence, startText, asOfText, dateText } from "@/lib/playoffs-series-view";
import { parseGameParam, parseYearParam, type OverviewGameCard, type PlayoffsOverview } from "@/lib/playoffs-types";

// 真實樣本：本機 DB 唯讀抽取的 2026-10-15 overview（見 fixture 的 _provenance）；各態由它複製後改單一欄位。
const REAL = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const clone = (): PlayoffsOverview => structuredClone(REAL);

const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");

test("E 已決＋C 未開打：挑戰賽總結、四場比分與官方 MVP、G1 預告（真實樣本）", () => {
  const out = html(<SeriesSection overview={REAL} />);
  const t = text(out);
  assert.match(out, /<section id="series"/);
  assert.match(t, /季後挑戰賽結果/);
  assert.match(t, /中信兄弟以 3：2 晉級台灣大賽（中信兄弟含規則勝 1）/);
  for (const name of ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]) assert.match(t, new RegExp(`官方 MVP：${name}`));
  assert.match(t, /下一場：台灣大賽 G1/);
  assert.match(t, /10\/17（六）/);
  assert.match(t, /17:05 開賽（官方 10\/5 公告）/);
  assert.match(t, /大巨蛋/);
  assert.match(t, /中信兄弟（客）@味全龍（主）/);
  assert.match(out, /href="\/games\/4\?kind=E&amp;year=2026"/);
});

test("D7：第 1 區不出現先發投手字樣", () => {
  const t = text(html(<SeriesSection overview={REAL} />));
  assert.doesNotMatch(t, /先發/);
});

test("Q3：第 2／3／4 區整區不渲染（無標題、無占位、無 #watch）", () => {
  const out = html(<SeriesSection overview={REAL} />);
  assert.doesNotMatch(out, /id="(teams|roster|watch)"/);
  assert.doesNotMatch(text(out), /觀戰重點|名單|待更新/);
});

test("審核 F1：當前系列（C）缺場次列時，挑戰賽總結照常顯示，不誤稱全年無資料", () => {
  const o = clone();
  o.series_section.current.games = [];
  o.series_section.next_game = null;
  o.series_section.next_game_missing_reason = "no_target";
  o.series_section.missing_reason = ["series_games_missing"];
  const t = text(html(<SeriesSection overview={o} />));
  assert.doesNotMatch(t, /本站尚無這一年的季後賽場次/);
  assert.match(t, /季後挑戰賽結果/);
  assert.match(t, /中信兄弟以 3：2 晉級台灣大賽/);
  for (const name of ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]) assert.match(t, new RegExp(`官方 MVP：${name}`));
  assert.match(t, /台灣大賽場次本站尚未取得/);
  assert.match(t, /下一場賽程本站尚未取得/);
});

test("整年 E／C 都沒有場次列：整區空態", () => {
  const o = clone();
  o.series_section = { ...o.series_section, status: "empty", previous: null, current: { ...o.series_section.current, games: [] }, next_game: null, next_game_missing_reason: "no_target" };
  const t = text(html(<SeriesSection overview={o} />));
  assert.match(t, /本站尚無這一年的季後賽場次/);
  assert.doesNotMatch(t, /季後挑戰賽結果/);
});

test("C1 完賽後：卡上有比分與 MVP、預告換 C2", () => {
  const o = clone();
  const c1 = o.series_section.current.games[0];
  Object.assign(c1, { completed: true, away_score: 3, home_score: 5, result: "home_win", official_status: "final", target_status: "final", display_status: "final", mvp: { id: "0000002345", name: "鄭浩均" } });
  o.series_section.next_game = o.series_section.current.games[1];
  const t = text(html(<SeriesSection overview={o} />));
  assert.match(t, /下一場：台灣大賽 G2/);
  assert.match(t, /官方 MVP：鄭浩均/);
});

test("目標場進行中：預告標題改「進行中」，不叫下一場", () => {
  const o = clone();
  o.series_section.next_game = { ...o.series_section.next_game!, target_status: "live" };
  const t = text(html(<SeriesSection overview={o} />));
  assert.match(t, /進行中：台灣大賽 G1/);
  assert.doesNotMatch(t, /下一場：/);
});

test("MVP 缺值：未取得與姓名缺分開，⛔ 寫未公布", () => {
  const base = REAL.series_section.previous!.games[0];
  const missing: OverviewGameCard = { ...base, mvp: null, mvp_missing_reason: "official_mvp_not_ingested" };
  const noName: OverviewGameCard = { ...base, mvp: { id: base.mvp!.id, name: null }, mvp_missing_reason: "player_name_unavailable" };
  assert.equal(mvpText(missing), "官方 MVP：本站尚未取得");
  assert.equal(mvpText(noName), "官方 MVP：姓名本站尚未取得");
  assert.equal(mvpText(REAL.series_section.current.games[0]), null);
  for (const c of [missing, noName]) assert.doesNotMatch(mvpText(c)!, /未公布/);
});

test("覆蓋 pending_update：顯示待更新說明；overview 缺下一場：說明本站尚未取得", () => {
  const o = clone();
  o.coverage = "pending_update";
  o.series_section.next_game = null;
  o.series_section.next_game_missing_reason = "no_target";
  const t = text(html(<SeriesSection overview={o} />));
  assert.match(t, /最新完賽結果更新中/);
  assert.match(t, /下一場賽程本站尚未取得/);
});

test("系列一句：進行中寫還差幾勝；已決 C 寫奪冠；衝突寫待確認", () => {
  const c = structuredClone(REAL.series_section.current);
  c.series_status = "active";
  c.sides = c.sides.map((s, i) => ({ ...s, game_wins: i ? 1 : 2, total_wins: i ? 1 : 2, remaining: i ? 3 : 2 }));
  assert.equal(seriesSentence(c), "味全龍 2：中信兄弟 1・味全龍還差 2 勝、中信兄弟還差 3 勝");
  c.series_status = "decided";
  c.winner = "AAA011";
  c.sides = c.sides.map((s, i) => ({ ...s, total_wins: i ? 2 : 4, remaining: 0 }));
  assert.equal(seriesSentence(c), "味全龍以 4：2 奪得總冠軍");
  c.conflict_reason = "both_reached";
  assert.equal(seriesSentence(c), "台灣大賽系列狀態待確認");
  assert.equal(seriesSentence(REAL.series_section.current), "台灣大賽 7 戰 4 勝制，尚未開打・味全龍 0：中信兄弟 0");
});

test("狀態章皆有文字；開賽時刻標公告來源；資料時點轉台北時間", () => {
  const g = REAL.series_section.current.games[0];
  assert.deepEqual(cardStatus(g), { text: "賽前", tone: "scheduled" });
  assert.deepEqual(cardStatus(REAL.series_section.previous!.games[0]), { text: "終場", tone: "done" });
  assert.deepEqual(cardStatus({ ...g, target_status: "live" }), { text: "進行中", tone: "live" });
  assert.deepEqual(cardStatus({ ...g, official_status: "postponed" }), { text: "延賽", tone: "warn" });
  assert.deepEqual(cardStatus({ ...g, display_status: "result_pending" }), { text: "賽果待更新", tone: "warn" });
  assert.equal(startText({ ...g, start: null }, REAL), "開賽時間本站尚未取得");
  assert.equal(asOfText(REAL), "本站資料更新於 10/15 10:11");
  assert.equal(asOfText({ as_of: { ...REAL.as_of, last_refresh_at: "2026-10-15T02:11:21+00:00" } }), "本站資料更新於 10/15 10:11");
  assert.equal(dateText(null), "日期待定");
});

test("條件場次標如有必要；不需進行的場次隱藏", () => {
  const o = clone();
  const t = text(html(<SeriesSection overview={o} />));
  assert.match(t, /台灣大賽 G7/);
  o.series_section.current.games[6].hidden_not_needed = true;
  assert.doesNotMatch(text(html(<SeriesSection overview={o} />)), /台灣大賽 G7/);
});

test("?year／?game 解析：只收合法值，其他忽略", () => {
  assert.equal(parseYearParam("2025", 2026), 2025);
  assert.equal(parseYearParam("abc", 2026), 2026);
  assert.equal(parseYearParam(undefined, 2026), 2026);
  assert.equal(parseGameParam("3"), 3);
  assert.equal(parseGameParam(["2", "5"]), 2);
  for (const bad of ["0", "-1", "1.5", "x", "", undefined, "1234"]) assert.equal(parseGameParam(bad), null);
});

test("場次清單是 sr-only 的包含塊（relative）且區內橫捲，避免整頁水平溢出", () => {
  const out = html(<SeriesSection overview={REAL} />);
  const lists = out.match(/<ul aria-label="[^"]+" class="([^"]+)"/g) ?? [];
  assert.equal(lists.length, 2);
  for (const ul of lists) assert.match(ul, /\brelative\b.*\boverflow-x-auto\b/);
});
