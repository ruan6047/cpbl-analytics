// `/playoffs` 區塊順序、錨點與第 2／3 區登記型別（#285 續做 WP2；MOUNT-CONTRACT r3 §1、§4）。
//
// - 順序固定 1→4→3→2（需求方 C2）：`#series` → `#watch` → `#roster` → `#teams`；錨點 id 固定，⛔ 依狀態改名，
//   ⛔ T 狀態推導。
// - 第 2／3 區只在 `area-registry.ts` 有登記時出現（需求方 C1）：沒登記＝外框、標題、錨點都不出現。
// - 各卡在自己的 PR 加一筆登記（契約 §4、§8 M1）；陣列順序不影響畫面，一律依 `PLAYOFFS_AREA_ORDER` 排。

import type { ComponentType } from "react";
import type { PlayoffsNote } from "./playoffs-notes.ts";

export const PLAYOFFS_AREA_ORDER = ["series", "watch", "roster", "teams"] as const;
export type PlayoffsAreaId = (typeof PLAYOFFS_AREA_ORDER)[number];
export type RegisteredAreaId = "roster" | "teams";

/** 錨點外框共用：與已上線的 `#series`／`#watch` 同值，跳轉後標題不被 sticky header 蓋住。 */
export const AREA_SCROLL_MARGIN = "scroll-mt-[70px] md:scroll-mt-[76px]";
/** 延遲載入占位高度（各卡可在登記中提供建議值）。 */
export const DEFAULT_AREA_MIN_HEIGHT_PX = 240;

export type AreaRegistration<T extends { context_version: string | null }> = {
  id: RegisteredAreaId;
  /** 回傳 `/api/v1/playoffs/...` 相對路徑（client 端以 `CLIENT_API` 前綴取，`no-store`）。 */
  path: (year: number, series: "E" | "C") => string;
  /** 純呈現、可放在 client 樹；只收 `data`，S04 不給變動 key、不 remount。 */
  Section: ComponentType<{ data: T | null }>;
  refresh: "every_round" | "on_context_change";
  minHeightPx?: number;
  /** 選填：頁尾說明（契約 §2.4、§2.5）。純函式、同步；`notes(null)` 只回不依資料的固定說明。 */
  notes?: (data: T | null) => PlayoffsNote[];
};

export function areaOrder(id: PlayoffsAreaId): number {
  return PLAYOFFS_AREA_ORDER.indexOf(id);
}

/** 依 C2 固定順序排登記，與陣列內順序無關；同 id 重複登記只取第一筆。 */
export function orderedRegistrations<R extends { id: RegisteredAreaId }>(regs: readonly R[]): R[] {
  const seen = new Set<string>();
  return [...regs]
    .filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)))
    .sort((a, b) => areaOrder(a.id) - areaOrder(b.id));
}
