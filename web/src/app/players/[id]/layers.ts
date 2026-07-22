// 球員頁 IA 分層（UX-PLAYER-IA2 修訂 UX-PLAYER-IA1 的凍結骨架）。
// role 不再是切換鈕，而是攤成標籤頁：雙棲球員同時出現「打擊」與「投球」兩個內容頁。
// 總覽常駐；分項與對戰／生涯／總覽在雙棲時把兩種身分上下堆疊，全頁不存在隱性 role 狀態。
// 只引型別（node --experimental-strip-types 會整句抹除，測試不必解析同目錄 .tsx 依賴）
import type { Role } from "./lib";

// UX-PLAYER-SCOPE1：scope、role、view、level 是四條獨立軸，URL 為單一事實來源。
export const PLAYER_SCOPES = ["season", "career"] as const;
export type PlayerScope = (typeof PLAYER_SCOPES)[number];

export const PLAYER_VIEWS = ["overview", "tracking", "yearly", "splits", "fielding", "value"] as const;
export type PlayerView = (typeof PLAYER_VIEWS)[number];
export type PlayerLevel = "A" | "D";

const SCOPE_VIEWS: Record<PlayerScope, PlayerView[]> = {
  season: ["overview", "tracking", "splits", "fielding"],
  career: ["overview", "yearly", "splits", "fielding", "value"],
};

export const viewsFor = (scope: PlayerScope): PlayerView[] => SCOPE_VIEWS[scope];

export function scopeFromParams(
  scope: string | null, legacySec: string | null, isRetired: boolean,
): PlayerScope {
  if ((PLAYER_SCOPES as readonly string[]).includes(scope ?? "")) return scope as PlayerScope;
  if (legacySec === "career" || isRetired) return "career";
  return "season";
}

export function roleFromParams(
  role: string | null, legacySec: string | null, roles: Role[],
): Role {
  if ((role === "batting" || role === "pitching") && roles.includes(role)) return role;
  if (legacySec === "pitching" && roles.includes("pitching")) return "pitching";
  if (legacySec === "batting" && roles.includes("batting")) return "batting";
  return primaryRole(roles);
}

const LEGACY_VIEW: Partial<Record<string, PlayerView>> = {
  batting: "tracking",
  pitching: "tracking",
  approach: "tracking",
  splits: "splits",
  fielding: "fielding",
  career: "overview",
};

export function viewFromParams(
  view: string | null, legacySec: string | null, scope: PlayerScope,
): PlayerView {
  const available = viewsFor(scope);
  if (view && (available as readonly string[]).includes(view)) return view as PlayerView;
  const legacy = legacySec ? LEGACY_VIEW[legacySec] : null;
  return legacy && available.includes(legacy) ? legacy : "overview";
}

export function levelFromParams(level: string | null, rosterLevel: string | null | undefined): PlayerLevel {
  if (level === "A" || level === "D") return level;
  return rosterLevel === "二軍" ? "D" : "A";
}

export function playerNavFromParams(
  params: { scope: string | null; view: string | null; role: string | null; level: string | null; sec: string | null },
  roles: Role[],
  isRetired: boolean,
  rosterLevel: string | null | undefined,
): { scope: PlayerScope; view: PlayerView; role: Role; level: PlayerLevel } {
  const scope = scopeFromParams(params.scope, params.sec, isRetired);
  // IA2 時期 `?role=` 本身會打開對應身分的逐球內容頁；只有在新 scope/view
  // 皆未出現時才視為舊連結，避免影響新 URL 省略 view 時的 overview 預設。
  const legacyView = !params.scope && !params.view && !params.sec &&
    (params.role === "batting" || params.role === "pitching") ? params.role : params.sec;
  return {
    scope,
    view: viewFromParams(params.view, legacyView, scope),
    role: roleFromParams(params.role, params.sec, roles),
    level: levelFromParams(params.level, rosterLevel),
  };
}

/** 可切換的分層。batting／pitching 是「身分內容頁」，其餘三層與 role 無關或內部堆疊。 */
export const ALL_LAYERS = ["batting", "pitching", "splits", "fielding", "career"] as const;
export type SubLayer = (typeof ALL_LAYERS)[number];

const LABEL: Record<SubLayer, string> = {
  batting: "打擊",
  pitching: "投球",
  splits: "分項與對戰",
  fielding: "守備",
  career: "生涯",
};

export const subLayerLabel = (layer: SubLayer): string => LABEL[layer];

/**
 * 該球員實際會出現的標籤列。
 * 身分內容頁只在球員具備該身分時出現（純打者沒有「投球」頁）；
 * 其餘三層恆在——標籤數不隨資料多寡跳動，避免導覽在不同球員間變形。
 */
export function layersFor(roles: Role[]): SubLayer[] {
  const out: SubLayer[] = [];
  if (roles.includes("batting")) out.push("batting");
  if (roles.includes("pitching")) out.push("pitching");
  return [...out, "splits", "fielding", "career"];
}

/** 主身分：有打擊先打擊，否則投球（沿用 IA1 的預設 role 邏輯，該項仍有效）。 */
export const primaryRole = (roles: Role[]): Role =>
  roles.includes("batting") || roles.length === 0 ? "batting" : "pitching";

/** 身分內容頁對應的 role；非身分頁回 null。 */
export const layerRole = (layer: SubLayer): Role | null =>
  layer === "batting" ? "batting" : layer === "pitching" ? "pitching" : null;

const roleLayer = (r: Role, available: SubLayer[]): SubLayer => {
  const wanted: SubLayer = r === "pitching" ? "pitching" : "batting";
  return available.includes(wanted) ? wanted : available[0];
};

/**
 * `?sec=` 解析，含舊連結相容（IA2 前的值已上線於 production，不可直接失效）：
 * - `approach`（舊 L2）→ 該球員的主身分內容頁
 * - 舊 `?role=pitching` 且未給 `?sec=` → 投球頁
 * - 退役／教練（無本季登錄）→ 生涯層（沿用 IA1 §1.1，該項仍有效）
 * 非法值一律回退，不 404、不空白。
 */
export function subLayerFromParams(
  sec: string | null, role: string | null, roles: Role[], isRetired: boolean,
): SubLayer {
  const available = layersFor(roles);
  if (sec && (available as readonly string[]).includes(sec)) return sec as SubLayer;
  if (sec === "approach") return roleLayer(primaryRole(roles), available);
  if (!sec && role === "pitching" && available.includes("pitching")) return "pitching";
  if (isRetired) return "career";
  return roleLayer(primaryRole(roles), available);
}

/**
 * 堆疊層（總覽／分項與對戰／生涯）要渲染哪些身分。
 * 雙棲回兩個（主身分在前）；單一身分回一個；完全無身分回主身分以免整頁空白。
 */
export function stackedRoles(roles: Role[]): Role[] {
  const primary = primaryRole(roles);
  const other: Role = primary === "batting" ? "pitching" : "batting";
  return roles.includes(other) ? [primary, other] : [primary];
}

/** 堆疊層是否需要身分小標——只有兩個身分並存時才需要，單一身分加標題是雜訊。 */
export const needsRoleHeading = (roles: Role[]): boolean => stackedRoles(roles).length > 1;

export const roleLabel = (r: Role): string => (r === "batting" ? "打擊" : "投球");

/** 逐球樣本低於此值仍顯示數字，但必須標示僅供參考（IA1 狀態契約 §1.2，該項仍有效）。 */
export const SPARSE_PITCHES = 50;

/**
 * 逐球追蹤的稀疏警示文案；不稀疏、無樣本或尚未載入時回 null
 * （「無資料」由各卡自己的空態負責，與稀疏是不同狀態）。
 */
export function sparsePitchNote(pitches: number | null | undefined): string | null {
  if (pitches == null || pitches <= 0 || pitches >= SPARSE_PITCHES) return null;
  return `本季僅 ${pitches} 顆逐球樣本（部分球場未配置追蹤設備），以下分布與比率僅供參考。`;
}

/**
 * 資料群組 → 需要它的層。null＝常駐（Hero 或總覽需要）。
 * 守備自生涯層移出後獨立成 fielding 群組。
 */
export type DataGroup =
  | "profile" | "season" | "advanced" | "trend"
  | "tracking" | "movement"
  | "splits"
  | "fielding"
  | "career";

const DATA_GROUP_LAYERS: Record<DataGroup, SubLayer | null> = {
  profile: null,
  season: null,
  advanced: null,
  trend: null,
  tracking: "batting",   // 見 needsData：打擊／投球兩頁都要
  movement: "pitching",
  splits: "splits",
  fielding: "fielding",
  career: "career",
};

export function needsData(group: DataGroup, layer: SubLayer): boolean {
  const owner = DATA_GROUP_LAYERS[group];
  if (owner === null) return true;
  // 逐球追蹤在打擊與投球兩個身分內容頁都需要（各自取該 role 的視角）
  if (group === "tracking") return layer === "batting" || layer === "pitching";
  return owner === layer;
}

/**
 * 依層載入的快取分組名。
 *
 * **同一資料群組若會依身分抓不同資料，role 必須進「組名」而不只是 key。**
 * 每個組名只記得住一個 key，若組名固定、key 隨 role 變動，雙棲球員在打擊↔投球
 * 之間來回時會互相覆蓋，切回已看過的頁必定被判為 miss 而重抓（REVIEW-005 P1）。
 */
export const loadGroup = (group: DataGroup, role?: Role | null): string =>
  role ? `${group}:${role}` : group;

/**
 * 載入快取（純邏輯，便於回歸測試）：回傳 true 代表這次要真的去抓。
 * 同組同 key 只會回 true 一次；key 變動（換球員／換一二軍鏡頭）才重抓。
 */
export function createLoadTracker(): (group: string, key: string) => boolean {
  const seen = new Map<string, string>();
  return (group, key) => {
    if (seen.get(group) === key) return false;
    seen.set(group, key);
    return true;
  };
}
