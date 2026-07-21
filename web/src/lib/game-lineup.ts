import type { FieldCells, FieldPosition } from "@/components/field-diagram";
import type { StatRow } from "@/lib/client";

type Side = "away" | "home";

export type LineupPlayer = {
  id: string;
  name: string;
  position: string;
  order: number;
};

export type StartingLineup = {
  cells: FieldCells;
  designatedHitter: LineupPlayer | null;
  order: LineupPlayer[];
  /** 名單只能從首輪打席重建；未湊齊九人或先有野手異動時不可假稱先發。 */
  available: boolean;
};

const FIELD_POSITIONS = new Set<FieldPosition>(["LF", "CF", "RF", "3B", "SS", "2B", "1B", "P", "C"]);
const BATTER_CHANGE = /代打|代跑|守備|更換打者|更換野手/;

function sideCode(side: Side) {
  return side === "away" ? "1" : "2";
}

/**
 * 官網 `batting_order` 每半局都從 1 重計，不能直接代表先發棒次。
 * 因此以該隊九位打者的「首次正式打席」出現順序重建；若首輪未完成前已有
 * 野手異動，資料已無法可靠區分先發與替補，寧可不顯示。
 */
export function startingLineup(side: Side, log: StatRow[], game: StatRow, pitching: StatRow[]): StartingLineup {
  const code = sideCode(side);
  const firstNine: LineupPlayer[] = [];
  const seen = new Set<string>();
  let blocked = false;

  for (const row of log) {
    if (String(row.visiting_home_type ?? "") !== code) continue;
    if (Boolean(row.is_change_player)) {
      if (BATTER_CHANGE.test(String(row.content ?? "")) && firstNine.length < 9) blocked = true;
      continue;
    }
    const id = String(row.hitter_acnt ?? "");
    const name = String(row.hitter_name ?? "").trim();
    const position = String(row.defend_station_code ?? "").trim();
    if (!id || !name || seen.has(id)) continue;
    seen.add(id);
    if (firstNine.length < 9) firstNine.push({ id, name, position, order: firstNine.length + 1 });
  }

  if (blocked || firstNine.length !== 9) {
    return { cells: {}, designatedHitter: null, order: firstNine, available: false };
  }

  const cells: FieldCells = {};
  let designatedHitter: LineupPlayer | null = null;
  for (const player of firstNine) {
    if (player.position === "DH") {
      designatedHitter = player;
      continue;
    }
    if (FIELD_POSITIONS.has(player.position as FieldPosition)) {
      const code = player.position as FieldPosition;
      // 同一守位意外重複時保留首位，避免把首輪資料靜默覆蓋成後來的球員。
      if (!cells[code]) cells[code] = { main: player.name, meta: String(player.order) };
    }
  }

  const starterId = String(side === "away" ? game.away_starter_id ?? "" : game.home_starter_id ?? "");
  const starter = pitching.find((row) => String(row.pitcher_acnt ?? "") === starterId);
  const pitcher = firstNine.find((player) => player.position === "P")
    ?? (starter ? { id: starterId, name: String(starter.pitcher_name ?? "").trim(), position: "P", order: 0 } : null);
  if (pitcher?.name) {
    cells.P = { main: pitcher.name, sub: pitcher.order ? null : "先發投手", meta: pitcher.order ? String(pitcher.order) : null };
  }

  return { cells, designatedHitter, order: firstNine, available: true };
}
