// 球員頁 IA 分層（UX-PLAYER-IA1 決策：C・Hybrid）。
// 總覽常駐於層外，其餘三層以 ?sec= 切換；純邏輯集中於此以便測試，元件不重複判斷。
// 只引型別（node --experimental-strip-types 會整句抹除，測試不必解析同目錄 .tsx 依賴）
import type { Role } from "./lib";

export const SUB_LAYERS = ["approach", "splits", "career"] as const;
export type SubLayer = (typeof SUB_LAYERS)[number];

/** L2 標籤跟隨 active role：打者＝打法、投手＝球路（IA 決策 §1）。 */
export const subLayerLabel = (layer: SubLayer, role: Role): string =>
  layer === "approach" ? (role === "batting" ? "打法" : "球路")
  : layer === "splits" ? "分項與對戰"
  : "生涯";

/**
 * ?sec= 解析。無效或未給時的預設：退役／教練（roster_level=null）直落生涯，
 * 其餘落打法／球路——IA 決策 §1.1「退役者預設層＝生涯」。
 */
export function subLayerFromParam(param: string | null, isRetired: boolean): SubLayer {
  if (param && (SUB_LAYERS as readonly string[]).includes(param)) return param as SubLayer;
  return isRetired ? "career" : "approach";
}

/** ?role= 解析：只接受該球員實際具備的 role，否則回退預設。 */
export function roleFromParam(param: string | null, available: Role[], fallback: Role): Role {
  return param && available.includes(param as Role) ? (param as Role) : fallback;
}

/**
 * 資料群組 → 需要它的層。常駐群組（hero／總覽）恆為 true；
 * 其餘只有進入對應層才抓，避免首屏一次打完全部端點（現況 20+ 請求）。
 * 同一群組被多層共用時仍只抓一次（由呼叫端以 key 快取），不重複請求。
 */
export function needsData(group: DataGroup, layer: SubLayer): boolean {
  return DATA_GROUP_LAYERS[group] === null || DATA_GROUP_LAYERS[group] === layer;
}

/** 逐球樣本低於此值仍顯示數字，但必須標示僅供參考（IA 狀態契約 §1.2 稀疏警示）。 */
export const SPARSE_PITCHES = 50;

/**
 * 逐球追蹤的稀疏警示文案；不稀疏、無樣本或尚未載入時回 null
 * （「無資料」由各卡自己的空態負責，與稀疏是不同狀態）。
 */
export function sparsePitchNote(pitches: number | null | undefined): string | null {
  if (pitches == null || pitches <= 0 || pitches >= SPARSE_PITCHES) return null;
  return `本季僅 ${pitches} 顆逐球樣本（部分球場未配置追蹤設備），以下分布與比率僅供參考。`;
}

export type DataGroup =
  | "profile" | "season" | "advanced" | "trend"      // 常駐／總覽
  | "tracking" | "movement"                            // L2 打法／球路
  | "splits"                                           // L3 分項與對戰
  | "career" | "fielding";                             // L4 生涯

/** null＝常駐（hero 或總覽需要），否則為唯一需要它的子層。 */
const DATA_GROUP_LAYERS: Record<DataGroup, SubLayer | null> = {
  profile: null,
  season: null,
  advanced: null, // 總覽的官方進階 PR 摘要與 L2 細項共用同一份回應
  trend: null,
  tracking: "approach",
  movement: "approach",
  splits: "splits",
  career: "career",
  fielding: "career",
};
