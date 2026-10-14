import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import DailyHub from "./daily-hub.tsx";
import { PostseasonOverview } from "./postseason-overview.tsx";
import { NEXT_ANNOUNCED_STATUS, PostseasonNextCard, postseasonGameLabels, postseasonPointer } from "./postseason-next.tsx";
import {
  freshnessAxes, gameHref, hasScheduleChange, scheduleChangeCopy, scheduleChanges, summaryWithTeamNames, withScheduleChanges,
  type Coverage, type DailyGame, type DailySummary,
} from "@/lib/daily-summary.ts";
import { gameTeamName, teamNamesFromGames, withGameTeamNames } from "@/lib/teams.ts";
import { POSTSEASON_2026 } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, type JourneyRow, type SeriesGame } from "@/lib/postseason-journey.ts";

// #268 挑戰賽 → 台灣大賽的首頁轉換與雙軸 freshness。全部是 SYNTHETIC fixture（形狀取自 #268 反例：
// E4 統一 2:8 兄弟，兄弟實際 2 勝＋規則 1 勝＝3；C1 10/17 17:05 兄弟@味全・大巨蛋），不是公站證據。

const router = { back() {}, forward() {}, push() {}, replace() {}, refresh() {}, hmrRefresh() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router}>{node}</AppRouterContext.Provider>);
const text = (node: ReactElement) => html(node)
  .replace(/<[^>]*>/g, " ")
  .replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&")
  .replace(/\s+/g, " ").trim();

const LIONS = "ADD011";
const BROTHERS = "ACN011";
const DRAGONS = "AAA011";

const E_GAMES: SeriesGame[] = [
  { game_no: 1, game_sno: 1, date: "2026-10-09", away_code: LIONS, away_score: 3, home_code: BROTHERS, home_score: 1 },
  { game_no: 2, game_sno: 2, date: "2026-10-10", away_code: BROTHERS, away_score: 5, home_code: LIONS, home_score: 2 },
  { game_no: 3, game_sno: 3, date: "2026-10-11", away_code: LIONS, away_score: 4, home_code: BROTHERS, home_score: 2 },
  { game_no: 4, game_sno: 4, date: "2026-10-12", away_code: LIONS, away_score: 2, home_code: BROTHERS, home_score: 8 },
];

const C1_ROW: JourneyRow = {
  year: 2026, kind_code: "C", game_sno: 1, game_date: "2026-10-17", venue: "大巨蛋",
  away_team_code: BROTHERS, home_team_code: DRAGONS, away_score: 0, home_score: 0, completed: false,
};

function journeyAt(nowIso: string, eGames: SeriesGame[], rows: JourneyRow[] | null = null) {
  return buildPostseasonJourney({
    announcement: POSTSEASON_2026,
    summary: [{ kind_code: "E", team1_code: BROTHERS, team2_code: LIONS, games: eGames }],
    rows,
    nowMs: Date.parse(nowIso),
    dataAsOf: eGames.at(-1)?.date ?? null,
  });
}

const COVERED: Coverage = { status: "covered", taipei_date: "2026-10-13", pending_games: [] };
const E4_PENDING: Coverage = {
  status: "pending_update", taipei_date: "2026-10-13",
  pending_games: [{ year: 2026, kind_code: "E", game_sno: 4, game_date: "2026-10-12",
                    official_status: "scheduled", reason: "past_game_without_result" }],
};

function summary({ coverage, nextGames = [] as DailyGame[], lastDone = "2026-10-12" }: {
  coverage?: Coverage; nextGames?: DailyGame[]; lastDone?: string;
}): DailySummary {
  return {
    scope: { season: null, kind_code: "A", kinds: ["A", "E", "C"], as_of: "2026-10-13" },
    today: null,
    latest_game_day: null,
    next_slate: nextGames.length ? { game_date: nextGames[0].game_date, days_from_as_of: 4, games: nextGames } : null,
    freshness: {
      as_of: "2026-10-13",
      last_completed_game_date: lastDone,
      last_refresh: { at: "2026-10-13T02:12:00+00:00", ok: true, scope: "recent-games", hours_ago: 1, status: "fresh", reason: null },
      ...(coverage ? { coverage } : {}),
      unresolved_games: [],
    },
    availability: {
      schedule: nextGames.length ? { status: "available", reason: null } : { status: "season_complete", reason: null },
      results: { status: "available", reason: null },
      pregame_model: { status: "serving_current", reason: null, trained_through: null, signals: null },
    },
  };
}

const C1_GAME: DailyGame = {
  season: 2026, kind_code: "C", game_sno: 1, game_date: "2026-10-17", venue: "大巨蛋",
  away_team_code: BROTHERS, away_team_name: "中信兄弟", away_score: null,
  home_team_code: DRAGONS, home_team_name: "味全龍", home_score: null,
  completed: false, delay_kind: null, orig_date: null,
  pregame: { status: "unsupported", home_win_probability: null, signals: null },
};

// —— 下一批賽事：真 G1 ——

test("E 已決、DB 尚無 C 列：首頁下一批呈現公告台灣大賽 G1 兄弟@味全，不給單場連結、不稱全季結束", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES);
  assert.equal(j.series.E.tally.winner, BROTHERS);
  const p = postseasonPointer(j)!;
  assert.deepEqual(p.next, {
    title: "台灣大賽 G1", when: "10/17（六） 17:05", away: "中信兄弟", home: "味全龍", venue: "大巨蛋",
    status: NEXT_ANNOUNCED_STATUS, gameHref: null,
  });
  const node = <DailyHub summary={summary({ coverage: COVERED })} calendar={null} postseason={p} />;
  const t = text(node);
  assert.match(t, /台灣大賽 G1 10\/17（六） 17:05 公告安排・正式場次待更新 中信兄弟（客） 對 味全龍（主） ?・大巨蛋/);
  assert.doesNotMatch(t, /本季賽程已全部結束/);
  assert.doesNotMatch(html(node), /href="\/games\//, "公告安排不得造單場連結");
});

test("E 已決、DB 已有 C1 正式列：首頁票券、季後總覽、日曆的單場連結同為真 (2026,C,1)", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES, [C1_ROW]);
  const slot = j.slots.find((s) => s.key === "C1")!;
  const expected = "/games/1?kind=C&year=2026";
  // 季後總覽與日曆都只渲染共用旅程模型的 slot.href。
  assert.equal(slot.href, expected);
  assert.equal(gameHref(C1_GAME), expected);
  const labels = postseasonGameLabels(j);
  assert.equal(labels["2026-C-1"], "台灣大賽 G1");
  // 資料庫有列 → 指引改為「已排定」並給真連結（只在左欄無場次時才會用到）。
  assert.equal(postseasonPointer(j)!.next!.gameHref, expected);

  const node = <DailyHub summary={summary({ coverage: COVERED, nextGames: [C1_GAME] })} calendar={null}
    postseason={postseasonPointer(j)} seriesLabels={labels} />;
  const t = text(node);
  assert.match(t, /台灣大賽 G1/);
  assert.match(html(node), /href="\/games\/1\?kind=C&amp;year=2026"/);
});

test("系列標籤只收已入庫場次，不從公告場序推場號", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES);
  assert.equal(Object.keys(postseasonGameLabels(j)).some((k) => k.includes("-C-")), false);
  assert.deepEqual(postseasonGameLabels(null), {});
});

test("首頁季後卡：挑戰賽已決要說出來", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES);
  assert.match(text(<PostseasonNextCard journey={j} />), /挑戰賽已決：兄弟晉級・台灣大賽・本站季後賽果 4 場/);
});

// —— 季後頁：預設分頁是台灣大賽時，挑戰賽 E4 待更新仍要在標頭明示（N8 情境 A 自檢發現）——

test("季後頁標頭：E4 已過開賽時間仍無賽果 → 即使預設在台灣大賽分頁也明示待更新", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES.slice(0, 3));
  assert.equal(j.next?.kind, "C", "前提：預設分頁是台灣大賽");
  const page = html(<PostseasonOverview journey={j} nameOf={(c) => c ?? ""} seedOf={() => ""} />);
  const t = page.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
  assert.match(t, /本站賽果紀錄至 10\/11 ・季後挑戰賽 G4 賽果待更新/);
  const done = html(<PostseasonOverview journey={journeyAt("2026-10-13T10:30:00+08:00", E_GAMES)}
    nameOf={(c) => c ?? ""} seedOf={() => ""} />);
  assert.doesNotMatch(done, /data-testid="ps-pending"/, "全部有賽果時不出現");
});

// —— 公開反例：C 場次官方隊名空白（隊碼正確）——

test("C1 隊名空白：首頁票券以隊碼補齊可讀名，不再唸成「No.1 對 ，賽事詳情」", () => {
  const blank: DailyGame = { ...C1_GAME, away_team_name: "", home_team_name: "" };
  const page = html(<DailyHub summary={summary({ coverage: COVERED, nextGames: [blank] })} calendar={null} postseason={null} />);
  assert.match(page, /aria-label="No\.1 中信兄弟 對 味全龍，賽事詳情"/);
  assert.doesNotMatch(page, /No\.1  對 /);
  assert.match(page, /href="\/games\/1\?kind=C&amp;year=2026"/);
});

test("隊名補齊只補空白、不猜：官方原名優先，未知或歷史隊碼不套現役名", () => {
  assert.equal(gameTeamName("ACN011", ""), "中信兄弟");
  assert.equal(gameTeamName("ACN011", "  "), "中信兄弟");
  assert.equal(gameTeamName("ADD011", "統一7-ELEVEn獅"), "統一7-ELEVEn獅");
  assert.equal(gameTeamName("ACC011", ""), "", "兄弟象≠中信兄弟");
  assert.equal(gameTeamName("", ""), "");
  const row = withGameTeamNames({ ...C1_GAME, away_team_name: "", home_team_name: "" });
  assert.equal(row.away_team_code, "ACN011");
  assert.deepEqual([row.away_team_name, row.home_team_name], ["中信兄弟", "味全龍"]);
});

test("日曆篩選：後出現的空白 C 列不得覆蓋同隊例行賽名稱", () => {
  const regular = { away_team_code: DRAGONS, away_team_name: "味全龍", home_team_code: BROTHERS, home_team_name: "中信兄弟" };
  const cRow = { away_team_code: BROTHERS, away_team_name: "", home_team_code: DRAGONS, home_team_name: "" };
  const odd = { away_team_code: "ZZZ999", away_team_name: "", home_team_code: LIONS, home_team_name: "統一7-ELEVEn獅" };
  const names = teamNamesFromGames([regular, cRow, odd]);
  assert.equal(names.get(DRAGONS), "味全龍");
  assert.equal(names.get(BROTHERS), "中信兄弟");
  assert.equal(names.get(LIONS), "統一7-ELEVEn獅");
  assert.equal(names.get("ZZZ999"), "", "不認得的隊碼不猜名");
  // 只有空白 C 列時也有可讀名（隊碼字典）
  assert.equal(teamNamesFromGames([cRow]).get(BROTHERS), "中信兄弟");
});

test("輪詢與 SSR 同一個入口：summaryWithTeamNames 補齊每個區塊且不動其他欄位", () => {
  const blank: DailyGame = { ...C1_GAME, away_team_name: "", home_team_name: "" };
  const s = summaryWithTeamNames(summary({ coverage: COVERED, nextGames: [blank] }));
  assert.deepEqual([s.next_slate!.games[0].away_team_name, s.next_slate!.games[0].home_team_name], ["中信兄弟", "味全龍"]);
  assert.equal(s.next_slate!.games[0].game_sno, 1);
  assert.deepEqual(s.freshness.coverage, COVERED);
});

// —— 雙軸 freshness：刷新成功 × 已涵蓋最新完賽 ——

test("缺 10/12 E4：刷新成功也不得標「資料為最新」，改明示 E4 待更新", () => {
  const s = summary({ coverage: E4_PENDING, lastDone: "2026-10-11" });
  const axes = freshnessAxes(s.freshness);
  assert.equal(axes.refresh.label, "最近一次刷新成功");
  assert.equal(axes.coverage?.label, "1 場賽果待更新");
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES.slice(0, 3));
  const t = text(<DailyHub summary={s} calendar={null} postseason={postseasonPointer(j)} />);
  assert.doesNotMatch(t, /資料為最新/);
  assert.match(t, /1 場賽果待更新 10\/12 季後挑戰賽 No\.4/);
  assert.match(t, /資料更新至 10\/11/);
  assert.doesNotMatch(t, /本季賽程已全部結束/);
});

test("沒有季後公告但仍有場次待更新：不得說「本季賽程已全部結束」", () => {
  const t = text(<DailyHub summary={summary({ coverage: E4_PENDING })} calendar={null} postseason={null} />);
  assert.doesNotMatch(t, /本季賽程已全部結束/);
  assert.match(t, /最新賽果待更新，後續賽程待確認/);
});

test("刷新成功且已涵蓋：才說「資料為最新」", () => {
  const axes = freshnessAxes(summary({ coverage: COVERED }).freshness);
  assert.equal(axes.refresh.label, "資料為最新");
  assert.equal(axes.coverage, null);
});

test("舊 API 沒有 coverage：視為未確認，不說「資料為最新」", () => {
  const axes = freshnessAxes(summary({}).freshness);
  assert.notEqual(axes.refresh.label, "資料為最新");
  assert.equal(axes.coverage?.label, "最新賽果涵蓋待確認");
});

test("同晚即時來源中斷（live_status_unavailable）：不說「資料為最新」，也不灌進待更新場數", () => {
  const unobserved = { year: 2026, kind_code: "E", game_sno: 4, game_date: "2026-10-12",
                       official_status: "scheduled", reason: "live_status_unavailable" as const };
  const axes = freshnessAxes(summary({ coverage: {
    status: "unknown", taipei_date: "2026-10-12", pending_games: [unobserved] } }).freshness);
  assert.equal(axes.refresh.label, "最近一次刷新成功");
  assert.equal(axes.coverage?.label, "最新賽果涵蓋待確認");
  // 與確定待更新的場次並存：只計確定者
  const mixed = freshnessAxes(summary({ coverage: {
    ...E4_PENDING, pending_games: [...E4_PENDING.pending_games, { ...unobserved, game_sno: 5 }] } }).freshness);
  assert.equal(mixed.coverage?.label, "1 場賽果待更新");
  assert.equal(mixed.coverage?.detail, "10/12 季後挑戰賽 No.4");
});

test("官方賽程異動未入庫（official_change_not_ingested，#268 D1）：明示賽程待更新，不說「資料為最新」", () => {
  const change = { year: 2026, kind_code: "C", game_sno: 1, game_date: "2026-10-18",
                   official_status: "unknown", reason: "official_change_not_ingested" as const };
  const s = summary({ coverage: { status: "pending_update", taipei_date: "2026-10-13", pending_games: [change] } });
  const axes = freshnessAxes(s.freshness);
  assert.equal(axes.refresh.label, "最近一次刷新成功");
  assert.equal(axes.coverage?.label, "1 場賽程待更新");
  assert.equal(axes.coverage?.detail, "10/18 台灣大賽 No.1 賽程異動");
  const t = text(<DailyHub summary={s} calendar={null} postseason={null} />);
  assert.doesNotMatch(t, /資料為最新/);
  assert.match(t, /1 場賽程待更新 10\/18 台灣大賽 No\.1 賽程異動/);
  // 與完賽待更新並存：計入同一個數字，標籤不把賽程異動說成賽果；日期未知照實顯示「—」。
  const mixed = freshnessAxes(summary({ coverage: {
    ...E4_PENDING, pending_games: [...E4_PENDING.pending_games, { ...change, game_date: null }] } }).freshness);
  assert.equal(mixed.coverage?.label, "2 場賽果／賽程待更新");
  assert.equal(mixed.coverage?.detail, "10/12 季後挑戰賽 No.4、— 台灣大賽 No.1 賽程異動");
});

// —— #268 B2：季後頁／日曆讀同一份 daily summary coverage 的官方賽程異動（需求方裁定 6142744045）——

const C1_CHANGE = { year: 2026, kind_code: "C", game_sno: 1, game_date: "2026-10-17",
                    official_status: "unknown", reason: "official_change_not_ingested" as const };
const changeSummary = (pending: Coverage["pending_games"]) =>
  summary({ coverage: { status: "pending_update", taipei_date: "2026-10-13", pending_games: pending } });
const HEADER_NOTE = /<b data-testid="ps-schedule-pending"[^>]*>[^<]*<\/b>/;
const ROW_NOTE = /<span data-testid="ps-row-schedule-pending"[^>]*>[^<]*<\/span>/g;

test("兩頁共用：只取該季 E／C 的 official_change_not_ingested，文案與首頁同一句", () => {
  const s = changeSummary([
    C1_CHANGE,
    E4_PENDING.pending_games[0],                                   // 完賽類：旅程已有「賽果待更新」，不重複
    { ...C1_CHANGE, game_sno: 2, reason: "live_status_unavailable" }, // 無從判斷：不在兩頁出現
    { ...C1_CHANGE, year: 2025 },                                   // 別季
  ]);
  const changes = scheduleChanges(s, 2026);
  assert.deepEqual(changes, [{ year: 2026, kind_code: "C", game_sno: 1, game_date: "2026-10-17" }]);
  assert.deepEqual(scheduleChangeCopy(changes), { label: "1 場賽程待更新", detail: "10/17 台灣大賽 No.1 賽程異動" });
  const home = freshnessAxes(changeSummary([C1_CHANGE]).freshness).coverage!;
  assert.equal(`${home.label} ${home.detail}`, "1 場賽程待更新 10/17 台灣大賽 No.1 賽程異動", "與首頁字串一致");
  assert.deepEqual(scheduleChanges(null, 2026), [], "summary 取不到＝不顯示");
  assert.equal(scheduleChangeCopy([]), null);
});

test("對應場次只認正式身分（year／kind／game_sno），不從公告 G 序推場號", () => {
  const changes = scheduleChanges(changeSummary([C1_CHANGE]), 2026);
  assert.equal(hasScheduleChange(changes, C1_ROW), true);
  assert.equal(hasScheduleChange(changes, { ...C1_ROW, game_sno: 2 }), false);
  assert.equal(hasScheduleChange(changes, { ...C1_ROW, year: 2025 }), false);
  assert.equal(hasScheduleChange(changes, null), false, "公告場（無資料庫列）不比對");
});

test("季後頁：尚無 C 列時異動只出現在標頭一句，#238 報告入口與其餘畫面逐字不變", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES);
  const props = { nameOf: (c: string | null) => c ?? "", seedOf: () => "", active: "C" };
  const before = html(<PostseasonOverview journey={j} {...props} />);
  const after = html(<PostseasonOverview journey={withScheduleChanges(j, scheduleChanges(changeSummary([C1_CHANGE]), 2026))} {...props} />);
  const t = after.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
  assert.match(t, /・1 場賽程待更新：10\/17 台灣大賽 No\.1 賽程異動/);
  assert.doesNotMatch(after, /ps-row-schedule-pending/, "公告 G1 沒有正式列：不把訊號掛到 G1");
  assert.equal(after.replace(HEADER_NOTE, ""), before, "只多標頭一句；報告 Link/CTA/preview 與 RefreshHint 不受影響");
  assert.match(before, /最新場間報告/, "前提：#238 入口有渲染");
});

test("季後頁：已有 C1 正式列時該列另標賽程待更新；拿掉兩處標示後與原畫面逐字相同", () => {
  const j = journeyAt("2026-10-13T10:30:00+08:00", E_GAMES, [C1_ROW]);
  const props = { nameOf: (c: string | null) => c ?? "", seedOf: () => "", active: "C" };
  const before = html(<PostseasonOverview journey={j} {...props} />);
  const after = html(<PostseasonOverview journey={withScheduleChanges(j, scheduleChanges(
    changeSummary([{ ...C1_CHANGE, game_date: "2026-10-18" }]), 2026))} {...props} />);
  assert.equal((after.match(ROW_NOTE) ?? []).length, 1);
  assert.match(after, /賽程待更新・官方賽程已異動，本站正式資料尚未反映/);
  assert.equal(after.replace(HEADER_NOTE, "").replace(ROW_NOTE, ""), before);
  assert.match(before, /下一場觀戰報告/, "前提：#238 下一場入口有渲染且未被改動");
});

test("刷新失敗與涵蓋分立：已涵蓋但刷新失敗仍照實說刷新失敗", () => {
  const s = summary({ coverage: COVERED });
  s.freshness.last_refresh = { ...s.freshness.last_refresh, ok: false, status: "failed" };
  const axes = freshnessAxes(s.freshness);
  assert.equal(axes.refresh.label, "最近一次刷新失敗");
  assert.equal(axes.coverage, null);
});
