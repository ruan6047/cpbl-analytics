import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { SeriesSection } from "./series-section.tsx";
import { cardStatus, chipView, mvpText, seriesSentence, seriesStatusLine, startText, asOfText, dateText } from "@/lib/playoffs-series-view";
import { parseGameParam, parseYearParam, type OverviewGameCard, type PlayoffsOverview } from "@/lib/playoffs-types";

// 真實樣本：本機 DB 唯讀抽取的 2026-10-15 overview（見 fixture 的 _provenance）；各態由它複製後改單一欄位。
const REAL = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const clone = (): PlayoffsOverview => structuredClone(REAL);

const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");

test("E 已決＋C 未開打：大比分、精簡卡（比分＋官方 MVP）、G1 預告、挑戰賽一句（真實樣本）", () => {
  const out = html(<SeriesSection overview={REAL} />);
  const t = text(out);
  assert.match(out, /<section id="series"/);
  // 大比分（需求方 SHA-F2 人工審核：要一眼看到）
  assert.match(out, /aria-label="系列大比分 味全龍 0 比 0 中信兄弟"/);
  assert.match(t, /7 戰 4 勝制・尚未開打/);
  // 挑戰賽一句（D3）與四場精簡卡
  assert.match(t, /季後挑戰賽中信兄弟以 3：2 晉級台灣大賽（中信兄弟含規則勝 1）/);
  for (const name of ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]) assert.match(t, new RegExp(`MVP ${name}`));
  // 預告：日期、開賽時刻＋來源、球場、主客
  assert.match(t, /下一場：台灣大賽 G1/);
  assert.match(t, /10\/17（六） 17:05 開賽（官方 10\/5 公告）・大巨蛋/);
  assert.match(t, /中信兄弟（客） @ 味全龍（主）/);
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
  assert.match(t, /中信兄弟以 3：2 晉級台灣大賽/);
  for (const name of ["勝騎士", "喬登", "獅帝芬", "鄭浩均"]) assert.match(t, new RegExp(`MVP ${name}`));
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

test("C1 完賽後：精簡卡有比分（勝方粗體）與 MVP、預告換 C2", () => {
  const o = clone();
  const c1 = o.series_section.current.games[0];
  Object.assign(c1, { completed: true, away_score: 3, home_score: 5, result: "home_win", official_status: "final", target_status: "final", display_status: "final", mvp: { id: "0000002345", name: "鄭浩均" } });
  o.series_section.next_game = o.series_section.current.games[1];
  const v = chipView(c1);
  assert.deepEqual(v.rows, [{ name: "兄弟", value: "3", win: false }, { name: "味全", value: "5", win: true }]);
  assert.equal(v.foot, "MVP 鄭浩均");
  const t = text(html(<SeriesSection overview={o} />));
  assert.match(t, /下一場：台灣大賽 G2/);
  assert.match(t, /MVP 鄭浩均/);
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

test("系列一句與大比分狀態行：進行中寫還差幾勝；已決 C 寫奪冠；衝突寫待確認", () => {
  const c = structuredClone(REAL.series_section.current);
  c.series_status = "active";
  c.sides = c.sides.map((s, i) => ({ ...s, game_wins: i ? 1 : 2, total_wins: i ? 1 : 2, remaining: i ? 3 : 2 }));
  assert.equal(seriesSentence(c), "味全龍 2：中信兄弟 1・味全龍還差 2 勝、中信兄弟還差 3 勝");
  assert.equal(seriesStatusLine(c), "味全龍還差 2 勝、中信兄弟還差 3 勝");
  c.series_status = "decided";
  c.winner = "AAA011";
  c.sides = c.sides.map((s, i) => ({ ...s, total_wins: i ? 2 : 4, remaining: 0 }));
  assert.equal(seriesSentence(c), "味全龍以 4：2 奪得總冠軍");
  assert.equal(seriesStatusLine(c), "味全龍奪得總冠軍");
  c.conflict_reason = "both_reached";
  assert.equal(seriesSentence(c), "台灣大賽系列狀態待確認");
  assert.equal(seriesStatusLine(c), "系列狀態待確認");
  assert.equal(seriesSentence(REAL.series_section.current), "台灣大賽 7 戰 4 勝制，尚未開打・味全龍 0：中信兄弟 0");
  assert.equal(seriesStatusLine(REAL.series_section.current), "7 戰 4 勝制・尚未開打");
  assert.equal(seriesStatusLine(REAL.series_section.previous!), "中信兄弟晉級台灣大賽（中信兄弟含規則勝 1）");
});

test("精簡卡補充行：MVP 缺值、非賽前狀態都有文字", () => {
  const base = REAL.series_section.previous!.games[0];
  assert.equal(chipView({ ...base, mvp: null, mvp_missing_reason: "official_mvp_not_ingested" }).foot, "MVP 未取得");
  assert.equal(chipView({ ...base, mvp: { id: base.mvp!.id, name: null }, mvp_missing_reason: "player_name_unavailable" }).foot, "MVP 姓名未取得");
  const g = REAL.series_section.current.games[0];
  assert.equal(chipView(g).foot, "大巨蛋");
  assert.deepEqual(chipView(g).rows.map((r) => r.value), ["客", "主"]);
  assert.equal(chipView({ ...g, official_status: "postponed" }).foot, "延賽");
  assert.equal(chipView({ ...g, target_status: "live" }).foot, "進行中");
  assert.equal(chipView({ ...g, display_status: "result_pending" }).foot, "賽果待更新");
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
  const c5 = o.series_section.current.games[4];
  assert.equal(c5.conditional, true);
  assert.equal(chipView(c5).foot, "如有必要");
  assert.match(html(<SeriesSection overview={o} />), /data-game="C7"/);
  o.series_section.current.games[6].hidden_not_needed = true;
  assert.doesNotMatch(html(<SeriesSection overview={o} />), /data-game="C7"/);
});

test("?year／?game 解析：只收合法值，其他忽略", () => {
  assert.equal(parseYearParam("2025", 2026), 2025);
  assert.equal(parseYearParam("abc", 2026), 2026);
  assert.equal(parseYearParam(undefined, 2026), 2026);
  assert.equal(parseGameParam("3"), 3);
  assert.equal(parseGameParam(["2", "5"]), 2);
  for (const bad of ["0", "-1", "1.5", "x", "", undefined, "1234"]) assert.equal(parseGameParam(bad), null);
});

test("整張卡就是單場連結（卡內不另放連結文字），清單是格狀不橫捲", () => {
  const out = html(<SeriesSection overview={REAL} />);
  // 每張卡 <li> 內唯一的 <a> 包住整張卡，href 帶 year 與 kind
  const chips = out.match(/<li class="min-w-0" data-game="[EC]\d+"><a [^>]+>/g) ?? [];
  assert.equal(chips.length, 11);
  const e4 = /<li class="min-w-0" data-game="E4"><a [^>]+>/.exec(out)![0];
  assert.match(e4, /href="\/games\/4\?kind=E&amp;year=2026"/);
  assert.match(e4, /aria-label="季後挑戰賽 G4，10\/12（一），洲際，統一獅 2：8 中信兄弟，官方 MVP：鄭浩均"/);
  assert.doesNotMatch(text(out), /單場賽況 →|單場頁 →/);
  const lists = out.match(/<ul aria-label="[^"]+" class="([^"]+)"/g) ?? [];
  assert.equal(lists.length, 2);
  for (const ul of lists) {
    assert.match(ul, /\bgrid\b/);
    assert.doesNotMatch(ul, /overflow-x-auto/);
  }
  // 層級：大比分 → 下一場 → 前一系列
  const i = (re: RegExp) => out.search(re);
  assert.ok(i(/data-big-score/) < i(/data-next-game/) && i(/data-next-game/) < i(/data-series="E"/));
});

