import assert from "node:assert/strict";
import { test } from "node:test";
import type { StatRow } from "./client.ts";
import { startingLineup } from "./game-lineup.ts";

const row = (id: number, name: string, pos: string, extra: Record<string, unknown> = {}) => ({
  visiting_home_type: "1", hitter_acnt: String(id), hitter_name: name, defend_station_code: pos, ...extra,
}) as StatRow;

test("依首次正式打席順序重建九人先發，DH 不塞進守備圖", () => {
  const log = [
    row(1, "一棒", "CF"), row(1, "一棒", "CF"), row(2, "二棒", "C"), row(3, "三棒", "LF"),
    row(4, "四棒", "DH"), row(5, "五棒", "1B"), row(6, "六棒", "3B"), row(7, "七棒", "SS"),
    row(8, "八棒", "2B"), row(9, "九棒", "RF"),
  ];
  const lineup = startingLineup("away", log, { away_starter_id: "99" } as StatRow,
    [{ pitcher_acnt: "99", pitcher_name: "先發投手" } as StatRow]);

  assert.equal(lineup.available, true);
  assert.deepEqual(lineup.order.map((p) => p.name), ["一棒", "二棒", "三棒", "四棒", "五棒", "六棒", "七棒", "八棒", "九棒"]);
  assert.equal(lineup.cells.CF?.meta, "1");
  assert.equal(lineup.cells.P?.main, "先發投手");
  assert.equal(lineup.designatedHitter?.name, "四棒");
});

test("首輪未湊齊九人或先發前已有野手異動時，不假稱先發名單", () => {
  const incomplete = startingLineup("away", [row(1, "一棒", "CF")], {} as StatRow, []);
  assert.equal(incomplete.available, false);

  const changed = startingLineup("away", [
    row(1, "一棒", "CF"), row(2, "二棒", "C", { is_change_player: true, content: "代打：甲=>乙" }),
    row(3, "三棒", "LF"), row(4, "四棒", "DH"), row(5, "五棒", "1B"), row(6, "六棒", "3B"),
    row(7, "七棒", "SS"), row(8, "八棒", "2B"), row(9, "九棒", "RF"), row(10, "十棒", "P"),
  ], {} as StatRow, []);
  assert.equal(changed.available, false);
});
