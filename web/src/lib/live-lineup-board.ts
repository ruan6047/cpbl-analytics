import type { FieldCells, FieldPosition } from "@/components/field-diagram";
import type { RosterGroup } from "@/components/roster-board";
import type { LiveSide } from "@/lib/live-game";

const FIELD_POSITIONS = new Set<FieldPosition>(["LF", "CF", "RF", "3B", "SS", "2B", "1B", "P", "C"]);

export type LiveLineupBoard = {
  fieldCells: FieldCells;
  designatedHitter: { main: string; meta: string; href: string } | null;
  groups: RosterGroup[];
};

/** 將 live snapshot 的先發棒次轉為與隊伍頁相同的 RosterBoard 顯示模型。 */
export function liveLineupBoard(data: LiveSide): LiveLineupBoard {
  const players = data.lineup.items.slice().sort((a, b) => a.batting_order - b.batting_order);
  const fieldCells: FieldCells = {};
  let designatedHitter: LiveLineupBoard["designatedHitter"] = null;

  for (const player of players) {
    const content = { main: player.name, meta: `${player.batting_order}棒`, href: `/players/${player.player_id}` };
    if (player.position === "DH") designatedHitter = content;
    else if (FIELD_POSITIONS.has(player.position as FieldPosition) && !fieldCells[player.position as FieldPosition]) {
      fieldCells[player.position as FieldPosition] = content;
    }
  }

  const starter = data.pitchers.find((pitcher) => String(pitcher.RoleType ?? "") === "先發") ?? data.pitchers[0];
  const starterId = String(starter?.PitcherAcnt ?? "");
  const starterName = String(starter?.PitcherName ?? "").trim();
  if (starterId && starterName) fieldCells.P = { main: starterName, sub: "先發投手", href: `/players/${starterId}` };

  const groups: RosterGroup[] = [{
    label: "先發打線",
    cells: players.map((player) => ({
      id: player.player_id, name: player.name, badge: player.position,
    })),
  }];
  if (starterId && starterName) groups.push({
    label: "先發投手",
    cells: [{ id: starterId, name: starterName, badge: "P", stat: "先發" }],
    divider: true,
  });
  return { fieldCells, designatedHitter, groups };
}
