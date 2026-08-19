import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TodayGameCard } from "./today-slate.tsx";
import {
  LATEST_STATUS_COPY,
  TODAY_COPY,
  type TodayGame,
  type TodayLive,
} from "@/lib/daily-summary.ts";
import { PREGAME_COPY } from "@/lib/pregame-card.ts";

// 首頁今日賽事卡的**渲染**測試（DEV-WEB-COMPONENT-TEST-HARNESS1）。
//
// 為什麼這一支必須真的渲染：本目錄既有的元件測試（`hierarchical-tabs.test.ts` 等）
// 讀原始碼字串做 regex 斷言，看得到「有沒有寫某個 className」，看不到「這個分支到底
// 有沒有被走到」。2026-08-19 #126 的變異檢驗證實了這個盲點——把 `&& g.live` 兩個守衛
// 加回去（延賽徽章整個消失），364 條全綠。
//
// 判準因此一律落在**畫出來的字**上，不落在原始碼形狀上：守衛改動會讓分支換一條走，
// 輸出的字就跟著變，測試才會轉紅。

const NOW = Date.parse("2026-08-19T19:30:00+08:00");

function markup(node: ReactElement): string {
  return renderToStaticMarkup(node);
}

/** 取畫面上的可讀文字：去標籤、還原 entity、壓空白。斷言只看讀者看得到的字。 */
function text(node: ReactElement): string {
  return markup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function live(over: Partial<TodayLive> = {}): TodayLive {
  return {
    phase: "live",
    raw_status: "START",
    starts_at: "2026-08-19T18:35:00+08:00",
    inning: 5,
    half: "2",
    outs: 1,
    bases: { first: true, second: false, third: false },
    away_score: 2,
    home_score: 3,
    event_count: 150,
    freshness: "fresh",
    stale_after_seconds: 45,
    source_status: "ok",
    fetched_at: new Date(NOW - 10_000).toISOString(),
    interrupt: "none",
    decisions: null,
    ...over,
  };
}

function game(over: Partial<TodayGame> = {}): TodayGame {
  return {
    season: 2026, kind_code: "A", game_sno: 274, game_date: "2026-08-19", venue: "洲際",
    away_team_code: "ADD011", away_team_name: "統一7-ELEVEn獅", away_score: null,
    home_team_code: "ACN011", home_team_name: "中信兄弟", home_score: null,
    completed: false, delay_kind: null, orig_date: null, live: null,
    ...over,
  } as TodayGame;
}

function card(g: TodayGame) {
  return <TodayGameCard g={g} trainedThrough={2025} nowMs={NOW} />;
}

// —— 延賽 ——

test("延賽（僅 DB delay_kind、無 live snapshot）：畫面上要有延賽徽章", () => {
  // 這就是 A#274 的形狀：worker 只在開賽時段供 snapshot，延賽場一整天都拿不到，
  // 官方 `delay_kind` 是手上唯一的事實。守衛若要求 `&& g.live`，這一格會落到賽前態。
  const out = text(card(game({ delay_kind: "延賽" })));
  assert.match(out, new RegExp(LATEST_STATUS_COPY.postponed.label));
  // 落到賽前態的病徵：畫面上唯一的說明文字變成模型狀態，等於拿模型缺席充當缺分的原因。
  assert.doesNotMatch(out, new RegExp(PREGAME_COPY.missingArtifact));
  assert.doesNotMatch(out, new RegExp(PREGAME_COPY.unsupported));
});

test("延賽（live snapshot phase=postponed）：同樣是延賽徽章，詞不隨來源改變", () => {
  const out = text(card(game({ live: live({ phase: "postponed" }) })));
  assert.match(out, new RegExp(LATEST_STATUS_COPY.postponed.label));
  assert.doesNotMatch(out, new RegExp(PREGAME_COPY.unsupported));
});

test("延賽：根本沒開打，不得畫出任何比分", () => {
  const out = text(card(game({ delay_kind: "延賽", away_score: 0, home_score: 0 })));
  assert.match(out, new RegExp(LATEST_STATUS_COPY.postponed.label));
  assert.doesNotMatch(out, /\b[0-9]+ *比 *[0-9]+\b/);
  assert.match(out, /—/, "缺分要照顯破折號，不回填 0");
});

// —— 保留賽 ——

test("保留賽（僅 DB delay_kind）：保留比賽徽章＋擇期續賽附註＋照顯中斷時比分", () => {
  const out = text(card(game({ delay_kind: "保留", away_score: 4, home_score: 1 })));
  assert.match(out, new RegExp(LATEST_STATUS_COPY.reserved.label));
  assert.match(out, new RegExp(TODAY_COPY.reservedNote));
  // 比分綁在隊名旁邊斷言：光找「4」會被日期／場次號矇混過去。
  assert.match(out, /統一7-ELEVEn獅 4/);
  assert.match(out, /中信兄弟 1/);
  assert.doesNotMatch(out, new RegExp(PREGAME_COPY.unsupported));
});

test("保留賽（live snapshot phase=reserved）：徽章與附註一致", () => {
  const out = text(card(game({ live: live({ phase: "reserved", away_score: 4, home_score: 1 }) })));
  assert.match(out, new RegExp(LATEST_STATUS_COPY.reserved.label));
  assert.match(out, new RegExp(TODAY_COPY.reservedNote));
});

test("延賽與保留賽是兩件事，徽章不得互換", () => {
  const p = text(card(game({ delay_kind: "延賽" })));
  const r = text(card(game({ delay_kind: "保留", away_score: 4, home_score: 1 })));
  assert.doesNotMatch(p, new RegExp(LATEST_STATUS_COPY.reserved.label));
  assert.doesNotMatch(r, new RegExp(`(?<!保)${LATEST_STATUS_COPY.postponed.label}`));
  assert.doesNotMatch(p, new RegExp(TODAY_COPY.reservedNote));
});

// —— 其餘三態：確保延賽/保留分支沒有把正常場次吃掉 ——

test("賽前態：走 PregameCard，不冒出延賽或保留徽章", () => {
  const out = text(card(game()));
  assert.match(out, new RegExp(PREGAME_COPY.unsupported));
  assert.doesNotMatch(out, new RegExp(LATEST_STATUS_COPY.postponed.label));
  assert.doesNotMatch(out, new RegExp(LATEST_STATUS_COPY.reserved.label));
});

test("賽中態：畫出局數、比分與螢幕閱讀器播報", () => {
  const out = text(card(game({ live: live() })));
  assert.match(out, /5 局下|5局下|5 局/);
  assert.match(out, new RegExp("統一7-ELEVEn獅 2 比 3 中信兄弟"));
  assert.doesNotMatch(out, new RegExp(PREGAME_COPY.unsupported));
});

test("賽後態：終場文案與賽後復盤入口", () => {
  const out = text(card(game({ completed: true, away_score: 2, home_score: 5 })));
  assert.match(out, /比賽結束/);
  assert.match(out, /賽後復盤/);
  assert.doesNotMatch(out, new RegExp(LATEST_STATUS_COPY.postponed.label));
});

// —— 環境本身的自我檢查 ——

test("harness：JSX 真的被渲染成 HTML（不是拿原始碼字串比對）", () => {
  const html = markup(card(game({ delay_kind: "延賽" })));
  assert.match(html, /^<div/, "應輸出真實 DOM 標記");
  assert.doesNotMatch(html, /className/, "className 已轉成 class ＝ 走過 React 渲染");
});
