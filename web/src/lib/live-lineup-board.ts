import type { FieldCells, FieldPosition } from "@/components/field-diagram";
import type { LiveSide } from "@/lib/live-game";

const FIELD_POSITIONS = new Set<FieldPosition>(["LF", "CF", "RF", "3B", "SS", "2B", "1B", "P", "C"]);

export type LiveLineupBoard = {
  fieldCells: FieldCells;
  designatedHitter: { main: string; meta: string; href: string } | null;
  groups: [];
};

/** 將 live snapshot 的先發棒次轉為與隊伍頁相同的 RosterBoard 顯示模型。 */
export function liveLineupBoard(data: LiveSide): LiveLineupBoard {
  const players = data.lineup.items.slice().sort((a, b) => a.batting_order - b.batting_order);
  const fieldCells: FieldCells = {};
  let designatedHitter: LiveLineupBoard["designatedHitter"] = null;

  for (const player of players) {
    const content = { main: player.name, meta: String(player.batting_order), href: `/players/${player.player_id}` };
    if (player.position === "DH") designatedHitter = content;
    else if (FIELD_POSITIONS.has(player.position as FieldPosition) && !fieldCells[player.position as FieldPosition]) {
      fieldCells[player.position as FieldPosition] = content;
    }
  }

  const starter = data.pitchers.find((pitcher) => String(pitcher.RoleType ?? "") === "先發") ?? data.pitchers[0];
  const starterId = String(starter?.PitcherAcnt ?? "");
  const starterName = String(starter?.PitcherName ?? "").trim();
  if (starterId && starterName) fieldCells.P = { main: starterName, sub: "先發投手", href: `/players/${starterId}` };

  return { fieldCells, designatedHitter, groups: [] };
}
