import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
const router={back(){},forward(){},push(){},replace(){},refresh(){},hmrRefresh(){},prefetch(){}};
const renderToStaticMarkup=(node:ReactElement)=>render(<AppRouterContext.Provider value={router}>{node}</AppRouterContext.Provider>);

import DailyHub from "./daily-hub.tsx";
import { SeasonClosedCard } from "./season-closed-card.tsx";
import { seasonClosedView, type DailySummary, type LeagueClosure } from "@/lib/daily-summary.ts";

// #391 首頁「球季結束」：值取自 2026 真實收官（`python -m cpbl.season_close` 本機唯讀輸出：
// 味全 AAA011 於台灣大賽 G6 10/26 封王、G7 not_needed；二軍富邦 AEO022 於 F G3 10/02 封王＝官網 2026 F 原始回應）。

function text(node: ReactElement): string {
  return renderToStaticMarkup(node).replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
}

const MAJOR: LeagueClosure = {
  league: "major", season: 2026, closed: true, status: "decided", champion_team_code: "AAA011",
  decided_by: { year: 2026, kind_code: "C", game_sno: 6 }, decided_game_date: "2026-10-26",
  not_needed: [{ year: 2026, kind_code: "C", game_sno: 7 }], basis: "§63/§60", reason: null, override: null,
};
const FARM: LeagueClosure = {
  league: "farm", season: 2026, closed: true, status: "decided", champion_team_code: "AEO022",
  decided_by: { year: 2026, kind_code: "F", game_sno: 3 }, decided_game_date: "2026-10-02",
  not_needed: [], basis: "farm_first_to_3", reason: null, override: null,
};
const FARM_NO_DATA: LeagueClosure = { ...FARM, closed: false, status: "no_data", champion_team_code: null,
  decided_by: null, decided_game_date: null, reason: "no_f_rows" };

function summary(seasonClose: DailySummary["season_close"]): DailySummary {
  return {
    scope: { season: null, kind_code: "A", kinds: ["A", "E", "C"], as_of: "2026-10-29" },
    today: null,
    latest_game_day: null,
    next_slate: null,
    freshness: {
      as_of: "2026-10-29",
      last_completed_game_date: "2026-10-26",
      last_refresh: { at: null, ok: null, scope: null, hours_ago: null, status: "unknown", reason: null },
      coverage: { status: "covered", taipei_date: "2026-10-29", pending_games: [] },
      unresolved_games: [],
    },
    season_close: seasonClose,
    availability: {
      schedule: { status: "season_complete", reason: null },
      results: { status: "ok", reason: null },
      pregame_model: { status: "serving_current", reason: null, trained_through: null, signals: null },
    },
  } as DailySummary;
}

test("一軍收官：首頁左欄是球季結束卡，含總冠軍、決勝場連結與本季回顧入口", () => {
  const node = <DailyHub summary={summary({ major: MAJOR, farm: FARM_NO_DATA })} calendar={null} postseason={null} />;
  const t = text(node);
  assert.match(t, /2026 球季結束/);
  assert.match(t, /2026 台灣大賽總冠軍 味全龍/);
  assert.match(t, /台灣大賽 G6・10\/26 封王/);
  assert.doesNotMatch(t, /二軍總冠軍/, "二軍尚未收官（F 未入庫）不猜冠軍");
  assert.doesNotMatch(t, /待更新|下一批賽事|本季賽程已全部結束/);
  const html = renderToStaticMarkup(node);
  assert.match(html, /href="\/games\/6\?kind=C&amp;year=2026"/);
  for (const href of ["/playoffs", "/standings?seg=3&amp;year=2026", "/standings?year=2026", "/records#dynasty"]) {
    assert.ok(html.includes(`href="${href}"`), href);
  }
  assert.doesNotMatch(html, /href="\/games\/7/, "G7 不給任何入口");
  // UI_UX_SYSTEM §2.3 強制界線：新碼字級只用角色（Tailwind 內建級距），⛔ arbitrary text-[Npx]。
  const card = renderToStaticMarkup(<SeasonClosedCard view={seasonClosedView(summary({ major: MAJOR, farm: FARM }))!} />);
  assert.doesNotMatch(card, /text-\[/);
});

test("兩軍都收官：二軍總冠軍一行出現（無單場頁連結）", () => {
  const t = text(<DailyHub summary={summary({ major: MAJOR, farm: FARM })} calendar={null} postseason={null} />);
  assert.match(t, /2026 二軍總冠軍 富邦悍將二軍/);
  assert.match(t, /二軍總冠軍賽 G3・10\/2 封王/);
});

test("未收官、讀不到、或二軍範圍：不出現球季結束卡（沿用原行為）", () => {
  assert.equal(seasonClosedView(summary(null)), null);
  assert.equal(seasonClosedView(summary(undefined)), null);
  assert.equal(seasonClosedView(summary({ major: { ...MAJOR, closed: false, status: "undecided" }, farm: FARM })), null);
  assert.equal(seasonClosedView(summary({ major: { ...MAJOR, closed: false, override: "open" } })), null);
  const farmScope = { ...summary({ major: MAJOR, farm: FARM }), scope: { season: null, kind_code: "D", kinds: ["D", "F"], as_of: "2026-10-29" } };
  assert.equal(seasonClosedView(farmScope), null);
  assert.doesNotMatch(text(<DailyHub summary={summary(null)} calendar={null} postseason={null} />), /球季結束/);
});
