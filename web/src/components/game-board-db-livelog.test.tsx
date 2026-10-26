import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import GameBoard, { type Live } from "./game-board.tsx";
import type { StatRow } from "@/lib/client.ts";
import { buildHighlights } from "@/lib/game-highlights.ts";
import { applyLiveSnapshot, type LiveApiResponse } from "@/lib/live-game.ts";
import { buildMoments } from "@/app/games/[sno]/overview.tsx";

// #357 WP2-b：`/api/v1/games/{sno}/live` 的 **DB 路徑**合併附加表後，最後事件號有兩列
// （實際打席＋結束標記），與 48 小時快照路徑同形。本檔驗「前端不需改碼」這個規劃預估。
// fixture 由後端實際轉換＋合併函式產生（見 JSON 內 _source），不是手寫。
// 預估**不完全成立**：`overview.tsx` `buildMoments`（關鍵打席結果文）在兩列同號時取到
// 結束標記（快照路徑同病）；需求方授權本卡小改（跳過結束標記列），檔尾兩支測試釘住。
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

// ── 關鍵打席（overview buildMoments）：結束標記列不得當成打席結果（需求方授權本卡修正）──
test("關鍵打席：最後打席是單一事件、首事件號即重複號（2026-C-4 再見安打）時，結果文是實際敘述", () => {
  const wp = [
    { evt: "1120020000", inning: 11, half: "2", wp: 0.5 },
    { evt: DUP, inning: 11, half: "2", wp: 0.45 },
    { evt: null, inning: 11, half: "2", wp: 1 },
  ];
  const last = buildMoments(wp as never, merged()).find((m) => m.evt === DUP);
  assert.equal(last?.desc, PLAY);
  assert.deepEqual(buildMoments(wp as never, merged()), buildMoments(wp as never, withoutMarker()),
    "多一列結束標記不改變任何關鍵打席");
});

// 2026-D-118：最後打席多事件（暴投上二壘 → 盜壘刺第三出局），標記＝「主審裁定比賽結束」。
const D118 = JSON.parse(readFileSync(
  new URL("../lib/__fixtures__/live-db-livelog_357_2026-D-118.json", import.meta.url), "utf8",
)) as { livelog: StatRow[]; snapshot_livelog: Record<string, unknown>[] };
const D118_PLAY = "壞球。 二壘跑者黃鈞麟出局-盜壘刺 3人出局。";
const d118Wp = (log: StatRow[]) => {
  let s = log.length - 1;
  while (s > 0 && log[s - 1].hitter_acnt === log[log.length - 1].hitter_acnt) s--;
  return [{ evt: String(log[s].main_event_no), inning: 7, half: "2", wp: 0.4 },
          { evt: null, inning: 7, half: "2", wp: 0 }];
};

test("關鍵打席（DB 路徑，2026-D-118 多事件最後打席）：結果文是盜壘刺，不是主審裁定比賽結束", () => {
  const log = D118.livelog;
  assert.equal(log[log.length - 1].content, "主審裁定比賽結束", "前提：DB 路徑最後一列是標記");
  assert.equal(buildMoments(d118Wp(log) as never, log)[0]?.desc, D118_PLAY);
});

test("關鍵打席（快照路徑，同一份 D-118 原文經 applyLiveSnapshot）：同樣不取結束標記", () => {
  const raw: LiveApiResponse = {
    game: { year: 2026, kind_code: "D", game_sno: 118 },
    scoreboard: [], livelog: [], batting: [], pitching: [], people: {}, records: {}, batter_avg: {},
    detail: null, decisions: {}, decision_counts: null, has_tracking: false, tracking: [], spray: [],
    live_snapshot: {
      game_id: "2026-D-118", game_sno: 118, kind_code: "D", phase: "final", raw_status: "FINISHED",
      inning: 7, half: "bottom", event_count: D118.snapshot_livelog.length, tracking_count: 0,
      tracking_availability: "pending", poll_after_seconds: 12, freshness: "fresh", source_status: "ok",
      stale_after_seconds: 45, source: { fetched_at: "2026-09-22T11:00:00+00:00", version: "357" },
      away: { team: { code: "AAA", name: "客" }, score: 0, inning_score: [],
              lineup: { availability: "announced", items: [], first_observed_at: null },
              hitters: [], pitchers: [], probable_pitcher: { availability: "not_announced" } },
      home: { team: { code: "BBB", name: "主" }, score: 0, inning_score: [],
              lineup: { availability: "announced", items: [], first_observed_at: null },
              hitters: [], pitchers: [], probable_pitcher: { availability: "not_announced" } },
      livelog: D118.snapshot_livelog,
    } as never,
  };
  const log = applyLiveSnapshot(raw).livelog as StatRow[];
  assert.equal(log[log.length - 1].content, "主審裁定比賽結束", "前提：快照路徑同號兩列都在");
  assert.equal(buildMoments(d118Wp(log) as never, log)[0]?.desc, D118_PLAY);
});

test("關鍵打席：多事件最後打席（向後掃描路徑）也不取結束標記；兩種標記字面都認", () => {
  const row = (no: string, content: string, extra: Partial<StatRow> = {}): StatRow => ({
    main_event_no: no, hitter_acnt: "H1", hitter_name: "打者", pitcher_name: "投手",
    is_change_player: null, is_score: null, content, ...extra,
  });
  for (const marker of ["比賽結束", "主審裁定比賽結束。"]) {
    const log = [row("0001", "壞球。"), row("0002", "壞球。 二壘跑者出局-盜壘刺 3人出局。"),
                 row("0002", marker)];
    const wp = [{ evt: "0001", inning: 9, half: "2", wp: 0.4 }, { evt: null, inning: 9, half: "2", wp: 0 }];
    assert.equal(buildMoments(wp as never, log)[0]?.desc, "壞球。 二壘跑者出局-盜壘刺 3人出局。", marker);
  }
});
