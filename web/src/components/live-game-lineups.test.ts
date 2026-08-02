import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { liveLineupBoard } from "../lib/live-lineup-board.ts";
import type { LiveSide } from "../lib/live-game.ts";

const raw = JSON.parse(readFileSync(new URL("../lib/__fixtures__/stats_game_2026-A-234.json", import.meta.url), "utf8")) as {
  Visiting: { Team: { Code: string; Name: string }; Hitters: Record<string, unknown>[]; Pitchers: Record<string, unknown>[] };
};

/** 真實官方 fixture 的隊伍區塊 → worker 已發布的 LiveSide 形狀。 */
const realSide = (): LiveSide => ({
  team: { code: raw.Visiting.Team.Code, name: raw.Visiting.Team.Name },
  score: 0,
  hits: null,
  errors: null,
  inning_score: [],
  lineup: {
    availability: "announced",
    items: raw.Visiting.Hitters
      .filter((hitter) => Number(hitter.Lineup ?? 0) > 0)
      .map((hitter) => ({
        batting_order: Number(hitter.Lineup), player_id: String(hitter.HitterAcnt),
        name: String(hitter.HitterName), position: String(hitter.DefendStation),
      })),
  },
  hitters: raw.Visiting.Hitters,
  pitchers: raw.Visiting.Pitchers,
  probable_pitcher: { availability: "not_announced" },
});

test("真實官方先發 fixture 轉成隊伍頁同款守備圖與角色卡", () => {
  const board = liveLineupBoard(realSide());

  assert.equal(board.fieldCells.RF?.main, "林立");
  assert.equal(board.fieldCells.RF?.meta, "1");
  assert.equal(board.fieldCells.P?.main, "艾菩樂");
  assert.equal(board.fieldCells.P?.sub, "先發投手");
  assert.equal(board.groups[0].label, "先發打線");
  assert.ok(board.groups[0].cells.every((cell) => cell.badge && cell.stat?.endsWith("棒")));
});
