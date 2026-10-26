import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import GameBoard, { type Live } from "./game-board.tsx";
import type { StatRow } from "@/lib/client.ts";
import { buildHighlights } from "@/lib/game-highlights.ts";
import { applyLiveSnapshot, type LiveApiResponse } from "@/lib/live-game.ts";

// #357 WP2-b：`/api/v1/games/{sno}/live` 的 **DB 路徑**合併附加表後，最後事件號有兩列
// （實際打席＋結束標記），與 48 小時快照路徑同形。本檔驗「前端不需改碼」這個規劃預估。
// fixture 由後端實際轉換＋合併函式產生（見 JSON 內 _source），不是手寫。
// ⚠️ 預估**不完全成立**：`overview.tsx` `buildMoments`（關鍵打席結果文）在兩列同號時取到
// 結束標記（快照路徑同病）。依派工停下回報、待裁定，本檔只釘住已成立的部分；
// 重現紀錄見 ~/.wf-evidence/cpbl-analytics/357/exec-wp2/logs/probe-b-*。
const FIXTURE = JSON.parse(readFileSync(
  new URL("../lib/__fixtures__/live-db-livelog_357_2026-C-4.json", import.meta.url), "utf8",
)) as { livelog: StatRow[] };
const DUP = "1120021000";
const PLAY = "擊出左外野高飛球，一壘安打 。1分打點。 二壘跑者岳政華回本壘得分。";

const merged = (): StatRow[] => FIXTURE.livelog.map((r) => ({ ...r }));
const withoutMarker = (): StatRow[] => merged().filter((r) => r.content !== "比賽結束");

const live = (livelog: StatRow[]): Live => {
  const raw: LiveApiResponse = {
    game: { year: 2026, kind_code: "C", game_sno: 4, away_score: 4, home_score: 5,
            away_team_code: "AAA", home_team_code: "BBB" },
    scoreboard: [], livelog, batting: [], pitching: [], people: {}, records: {}, batter_avg: {},
    detail: null, decisions: {}, decision_counts: null, has_tracking: false, tracking: [], spray: [],
    live_snapshot: null,
  };
  return applyLiveSnapshot(raw) as unknown as Live;
};

const pbp = (livelog: StatRow[], idx: number): string => renderToStaticMarkup(
  <GameBoard data={live(livelog)} idx={idx} setIdx={() => {}} view="pbp" gameSno="4" />,
).replace(/<!-- -->/g, "");

test("fixture 前提：DB 路徑最後事件號兩列，實際打席在前、結束標記在後", () => {
  const log = merged();
  assert.deepEqual(log.slice(-2).map((r) => [r.main_event_no, r.content]),
    [[DUP, PLAY], [DUP, "比賽結束"]]);
});

test("逐打席：最後一列選中時，實際敘述與結束列都在；投手累計球數不因結束列多算", () => {
  const log = merged();
  const html = pbp(log, log.length - 1);
  assert.ok(html.includes(PLAY), "實際最後打席敘述要出現");
  assert.ok(html.includes("比賽結束"), "結束列保留");
  const count = (h: string) => /K・被安\d+・([^<]*?)球/.exec(h)?.[1];
  const base = withoutMarker();
  assert.equal(count(html), count(pbp(base, base.length - 1)), "多一列結束標記不改變投手球數");
});

test("本場焦點：再見安打判定與沒有結束列時相同", () => {
  const h = (log: StatRow[]) => buildHighlights(live(log) as never, true).map((x) => x.text);
  assert.ok(h(merged()).some((t) => t.includes("再見安打")), "前提：本場有再見安打焦點");
  assert.deepEqual(h(merged()), h(withoutMarker()));
});
