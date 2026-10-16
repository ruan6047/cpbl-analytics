import type { AreaRegistration } from "@/lib/playoffs-areas";
import { rosterNotes, rosterPath, type PlayoffsRoster } from "@/lib/playoffs-roster";
import { RosterSection } from "@/components/playoffs/roster-section";

// `/playoffs` 第 2／3 區登記（#285 續做 WP2；MOUNT-CONTRACT r3 §4）。
// 各卡在自己的 PR 只加兩行：import 自己的 Section（與 notes 函式）＋這裡一筆登記。
// 沒有登記 ⇒ 該區外框、標題、錨點都不出現（需求方 C1）。陣列順序不影響畫面（依 C2 固定順序排）。
// `any`：各區 payload 型別不同，由各卡登記時自帶（AreaRegistration<各自型別>）。
export const PLAYOFFS_AREAS: AreaRegistration<any>[] = [
  // #286 S05 第 3 區：every_round（需求方裁定 #286 6196085219：名單／角色同步不改 context_version）。
  { id: "roster", path: rosterPath, Section: RosterSection, refresh: "every_round", minHeightPx: 480,
    notes: rosterNotes } satisfies AreaRegistration<PlayoffsRoster>,
];
