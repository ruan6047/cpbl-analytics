// #391 退回修正：單場頁的「依條件不需進行」（後端 series_context 該格 `display_status=not_needed`，
// 即系列已分勝負後未舉行的場次，§63 剩餘比賽取消）。這種場次不會再有賽況：即時快照（worker 在開賽前
// 觀測窗留下、可能已停更）不得再決定狀態章、「更新中斷」提示、先發名單或即時輪詢。
// ⛔ 只處理 not_needed；其他場次照原本即時行為（呼叫端在 notNeeded=false 時原樣傳回）。
import type { LiveSnapshot } from "./live-game.ts";

export type LiveView = {
  /** 呈現用快照（狀態章、先發名單、比分疊加）。 */
  snapshot: LiveSnapshot | null;
  /** 是否顯示「更新中斷」提示。 */
  interrupted: boolean;
  /** 是否繼續即時輪詢。 */
  poll: boolean;
};

export function liveViewFor(notNeeded: boolean, snapshot: LiveSnapshot | null,
  refreshIssue: "network" | "source" | null): LiveView {
  if (notNeeded) return { snapshot: null, interrupted: false, poll: false };
  return { snapshot, interrupted: refreshIssue !== null || snapshot?.freshness === "stale", poll: true };
}
