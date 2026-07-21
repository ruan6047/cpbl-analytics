// 對戰查詢控制狀態（UX-MATCHUP2 自 /matchups 抽離）。
// /matchups 以 URL 為狀態來源、球員頁以 local state 為來源，兩者共用同一組
// 控制形狀與 deep-link 編碼，確保「球員頁 → /matchups」帶入的查詢完全一致。
// 本檔不得 import React 或 runtime 依賴（node --experimental-strip-types 測試直跑）。
import type { Kind, Role, Scope, SortKey } from "./api";

export const CURRENT_YEAR = new Date().getFullYear();
/** 對戰資料源下限（cpbl-opendata／官網彙總最早年）。 */
export const MIN_YEAR = 1990;

export type MatchupControls = {
  kind: Kind;
  scope: Scope;
  /** 僅 scope === "range" 時生效。 */
  fromYear: number;
  toYear: number;
  /** 對某隊（franchise code）；與 opp／pick 互斥。 */
  team: string | null;
  /** 對某人（player_id）。 */
  opp: string | null;
  /** 「找特定對手」搜尋模式（未選定 opp 前）。 */
  pick: boolean;
  sort: SortKey;
  order: "asc" | "desc";
};

export type ControlsPatch = Partial<MatchupControls>;

export const DEFAULT_CONTROLS: MatchupControls = {
  kind: "A",
  scope: "season",
  fromYear: CURRENT_YEAR - 1,
  toYear: CURRENT_YEAR,
  team: null,
  opp: null,
  pick: false,
  sort: "plate_appearances",
  order: "desc",
};

/**
 * 產生 /matchups 的 deep-link（球員頁「在投打對決頁開啟」）。
 * 參數名與 matchups-client 的 URL 解析一一對應；預設值不寫進 URL，
 * 讓連結與站內導覽產生的網址形狀一致。
 */
export function matchupsHref(pid: string, role: Role, c: MatchupControls): string {
  const p = new URLSearchParams();
  if (role !== "batting") p.set("role", role);
  p.set("pid", pid);
  if (c.scope !== "season") p.set("scope", c.scope);
  if (c.scope === "range") {
    p.set("from", String(c.fromYear));
    p.set("to", String(c.toYear));
  }
  if (c.kind !== "A") p.set("kind", c.kind);
  if (c.team) p.set("team", c.team);
  if (c.opp) p.set("opp", c.opp);
  else if (c.pick) p.set("pick", "1");
  if (c.sort !== "plate_appearances") p.set("sort", c.sort);
  if (c.order !== "desc") p.set("order", c.order);
  return `/matchups?${p.toString()}`;
}
