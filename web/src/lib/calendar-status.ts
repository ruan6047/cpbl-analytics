// #391：賽程月曆單格的「依條件不需進行」判定（桌機、手機兩處共用，⛔ 不各寫一份）。
// 系列已分勝負後的未舉行列（§63 剩餘比賽取消）不是「未開打」，也不給單場連結。
import type { CalendarGame } from "./api.ts";

/** `slotStatus`＝一軍公告旅程的格狀態（`display_status`）；二軍沒有旅程。已完賽列一律不是 not_needed。 */
export function calendarNotNeeded(g: Pick<CalendarGame, "not_needed">, slotStatus: string | null | undefined,
  done: boolean): boolean {
  return !done && (g.not_needed === true || slotStatus === "not_needed");
}
