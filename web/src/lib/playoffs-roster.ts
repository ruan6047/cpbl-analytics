// #286 S05：季後賽第 3 區「系列賽 32 人資格名單」型別、排字與頁尾說明（`playoffs-roster/v1`）。
//
// - 統計、層級、PR 標籤全由後端算（PRD「前後端責任」）；這裡只排字、篩選、排序。
// - 說明性注意事項（28 人登錄、資格≠可用、G 定義、PR 來源、二軍背景）⛔ 在區內就地顯示，一律經
//   `rosterNotes(data)` 交 S04 頁尾（需求方 Q4、#281 6194693029；#285 掛點契約 §2.4、§2.5）。格內只留「—」「待更新」。
// - 頁尾 key 一律 `roster.*`（#285 裁定 6195728927：G1 前不用 `common.*`）。

import { ADV } from "@/app/players/[id]/lib";
import type { Card as AbilityCardData } from "@/components/ability-card";
import type { StatRow } from "@/lib/client";

export type RosterRole = "batting" | "pitching";
export type BackgroundLevel = "A" | "D" | "none";

export type BattingLine = {
  pa: number; ab: number; h: number; hr: number; bb: number;
  /** 三振：本系列打者才有（WP6；review-3 F2）。例行賽背景不帶。 */
  so?: number;
  avg: number | null; obp: number | null; slg: number | null; ops: number | null;
};
export type PitchingLine = { outs: number; ip: string; er: number; so: number; bb: number; era: number | null };

export type PrTag = { key: string; value: number };

export type ArrowStatus = "up" | "down" | "flat" | "insufficient" | "undefined";
export type ArrowWindow = { value: number | null } & Record<string, number | string | null>;
export type RosterArrow = {
  status: ArrowStatus;
  reason: "appearances" | "sample" | "era_zero" | "baseline" | null;
  metric: "ops_plus" | "era_plus";
  appearances: number;
  w1: ArrowWindow | null;
  w0: ArrowWindow | null;
  delta: number | null;
};

export type ArrowPolicy = {
  version: string; status: "proposed" | string; window: number;
  bat_min_ab: number; pit_min_outs: number; ops_plus_delta: number; era_plus_delta: number;
};

export type RosterBackground = {
  level: BackgroundLevel;
  g: number | null;
  line: BattingLine | PitchingLine | null;
  pr_tags: PrTag[];
  arrow: RosterArrow;
};

export type RosterMember = {
  player_id: string;
  name: string;
  official_position: "投手" | "捕手" | "內野手" | "外野手" | string;
  tactical_role: string | null;
  role_format_version?: 1 | 2;
  tactical_roles?: string[];
  role_provenance?: unknown;
  role: RosterRole;
  background: RosterBackground;
  /** 本系列實戰（PR2）：尚無完賽場 ⇒ null；未出賽 ⇒ g=0、line null；
   *  該隊缺這名球員角色的來源（打者缺打擊、投手缺投球）⇒ pending、g null（格內「待更新」，⛔ 當成 0G）。 */
  series?: { g: number | null; line: BattingLine | PitchingLine | null; pending?: boolean } | null;
};

export type RosterTeam = {
  team_code: string;
  team_name: string | null;
  roster_status: "submitted" | "missing" | "unavailable";
  roster: { roster_id: string; published_date: string | null; source_url: string | null; annotation_version: number | null;
    role_format_version?: 1 | 2; revision_hash?: string | null } | null;
  members: RosterMember[];
  /** 該隊已完賽但 box（打擊或投球任一）尚未送達的系列場序（PR2）。 */
  series_pending_games?: number[];
  /** 該隊缺哪種來源："batting"／"pitching"（PR2；review-3 F1）。 */
  series_pending_roles?: RosterRole[];
};

export type SeriesScopeStatus = "not_provided" | "no_games" | "ok" | "pending_source";

export type PlayoffsRoster = {
  contract: "playoffs-roster/v1";
  context_version: string | null;
  series_id: { year: number; kind_code: string; teams: string[] } | null;
  series: "E" | "C";
  year: number;
  as_of: {
    now: string; taipei_date: string; last_refresh_at: string | null;
    last_completed_game_date: string | null; background_cutoff: string | null;
  };
  status: "ok" | "partial" | "roster_missing" | "unavailable" | "series_unknown";
  default_scope: "background" | "series";
  arrow_policy: ArrowPolicy;
  scopes: {
    background: { status: string };
    series: { status: SeriesScopeStatus; completed_games?: number; pending_games?: number[] };
  };
  registration: { status: "unknown"; reason: string };
  roster_version: string;
  teams: RosterTeam[];
  missing_reason: string[];
};

/** 頁尾說明（結構同 #285 `PlayoffsNote`；S04 型別尚未在 main，故於此宣告同形）。 */
export type RosterNote = { key: string; text: string; source?: { label: string; url: string } };

export const ROSTER_COPY = {
  heading: "系列賽 32 人資格名單",
  loadFailed: "第 3 區資料暫時無法讀取，其他區不受影響。",
  seriesUnknown: "對戰組合尚未確定。",
  pending: "待更新",
  missing: "—",
  teamFilterLabel: "球隊篩選",
  posFilterLabel: "守位篩選",
  sortLabel: "排序",
  all: "全部",
  farm: "二軍",
  scopeLabel: "資料範圍",
} as const;

export type RosterPosFilter = "all" | "投手" | "捕手" | "內野手" | "外野手";
export const POS_FILTERS: { key: RosterPosFilter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "投手", label: "投手" },
  { key: "捕手", label: "捕手" },
  { key: "內野手", label: "內野手" },
  { key: "外野手", label: "外野手" },
];

export function filterMembersByPos(members: readonly RosterMember[], pos: RosterPosFilter = "all"): RosterMember[] {
  if (pos === "all") return [...members];
  return members.filter((m) => m.official_position === pos);
}

/** 第 3 區兩種 scope（PRD 第 3 區用語）。切換是元件內狀態，端點一次帶齊（契約 §2.1）。 */
export type RosterScope = "background" | "series";
export const SCOPES: { key: RosterScope; label: string }[] = [
  { key: "background", label: "例行賽與對戰背景" },
  { key: "series", label: "本系列實戰數據" },
];

/** 是否提供「本系列實戰」切換：後端未提供（舊版回應）⇒ 不顯示切換。 */
export const hasSeriesScope = (d: PlayoffsRoster) => d.scopes.series.status !== "not_provided";

/** 初始 scope：後端 default_scope（T5 ⇒ series）；未提供 series ⇒ 一律 background。 */
export const initialScope = (d: PlayoffsRoster): RosterScope =>
  d.default_scope === "series" && hasSeriesScope(d) ? "series" : "background";

export type RosterSort = "games" | "arrow" | "position";
export const SORTS: { key: "games" | "arrow"; label: string }[] = [
  { key: "games", label: "出賽 G" },
  { key: "arrow", label: "箭頭方向" },
];

/** 箭頭方向排序序：上升 → 平穩 → 下降 → 無箭頭。 */
const ARROW_ORDER: Record<ArrowStatus, number> = { up: 0, flat: 1, down: 2, insufficient: 3, undefined: 3 };

const POSITION_ORDER: Record<string, number> = { 投手: 0, 捕手: 1, 內野手: 2, 外野手: 3 };

/** 該 scope 的出賽 G：背景＝例行賽 G；系列＝本系列 G（無完賽場 ⇒ null）。 */
export const scopeG = (m: RosterMember, scope: RosterScope): number | null =>
  scope === "series" ? (m.series && !m.series.pending ? m.series.g : null) : m.background.g;

/** 本系列來源未齊（該隊缺這名球員角色的來源）⇒ 格內「待更新」。 */
export const seriesPending = (m: RosterMember, scope: RosterScope) => scope === "series" && !!m.series?.pending;

/** 排序：守位（官方序、同守位依 player_id）；出賽 G（依目前 scope，多到少，無紀錄排最後）；箭頭方向（例行賽背景）。
 *  不改原陣列。 */
export function sortMembers(members: readonly RosterMember[], sort: RosterSort,
  scope: RosterScope = "background"): RosterMember[] {
  const pos = (m: RosterMember) => POSITION_ORDER[m.official_position] ?? 99;
  const byPos = (a: RosterMember, b: RosterMember) => pos(a) - pos(b) || a.player_id.localeCompare(b.player_id);
  if (sort === "games") {
    return [...members].sort((a, b) => (scopeG(b, scope) ?? -1) - (scopeG(a, scope) ?? -1) || byPos(a, b));
  }
  if (sort === "arrow") {
    const k = (m: RosterMember) => ARROW_ORDER[m.background.arrow?.status ?? "insufficient"] ?? 3;
    return [...members].sort((a, b) => k(a) - k(b) || byPos(a, b));
  }
  return [...members].sort(byPos);
}

const r3 = (v: number | null) => (v == null ? ROSTER_COPY.missing : v.toFixed(3).replace(/^0\./, "."));

/** 出賽 G：無紀錄 ⇒「—」。 */
export const gText = (bg: { g: number | null }) => (bg.g == null ? ROSTER_COPY.missing : `${bg.g}G`);

/** v2只讀完整集合；legacy才允許單值相容，無主角色。 */
export function memberRoles(m: Pick<RosterMember, "tactical_role" | "tactical_roles" | "role_format_version">): string[] {
  if (m.role_format_version === 2) {
    if (!Array.isArray(m.tactical_roles) || !m.tactical_roles.length) throw new Error("角色v2資料不完整");
    return m.tactical_roles;
  }
  if (m.role_format_version != null && m.role_format_version !== 1) throw new Error("未知角色格式");
  return m.tactical_roles ?? (m.tactical_role && m.tactical_role !== "unclassified" ? [m.tactical_role] : []);
}

/** 抽屜標頭副標：守位 · 本站角色（有值才放、只放值）· 例行賽 G（· 二軍）。
 *  需求方裁定 #286 6210276945、6210408828：角色無值整段不顯示，不帶「本站角色」字樣。 */
export function drawerSubtitle(m: RosterMember): string {
  return [m.official_position, memberRoles(m).join("、"), gText(m.background),
    m.background.level === "D" ? ROSTER_COPY.farm : null].filter(Boolean).join(" · ");
}

/** 一行傳統計數（後端已算率）：打者 AVG／OPS、投手 ERA／IP。scope＝series 時用本系列計數。無紀錄 ⇒ null。 */
export function lineText(m: RosterMember, scope: RosterScope = "background"): string | null {
  const l = scope === "series" ? m.series?.line ?? null : m.background.line;
  if (!l) return null;
  if (m.role === "pitching") {
    const p = l as PitchingLine;
    return `ERA ${p.era == null ? ROSTER_COPY.missing : p.era.toFixed(2)} · ${p.ip} IP`;
  }
  const b = l as BattingLine;
  return `AVG ${r3(b.avg)} · OPS ${r3(b.ops)}`;
}

/** 小卡冷熱箭頭：末段 15 次的 OPS+／ERA+ 與方向（方向一律附文字，⛔ 只靠顏色）。無箭頭 ⇒ 方向 null、值「—」。 */
export function arrowView(m: RosterMember): { label: string; value: string; dir: "up" | "down" | "flat" | null; text: string } {
  const a = m.background.arrow;
  const label = a?.metric === "era_plus" ? "近 15 場 ERA+" : "近 15 場 OPS+";
  const v = a?.w1?.value;
  const value = a && (a.status === "up" || a.status === "down" || a.status === "flat") && v != null
    ? String(Math.round(v)) : ROSTER_COPY.missing;
  if (!a || !(a.status === "up" || a.status === "down" || a.status === "flat")) {
    return { label, value, dir: null, text: ROSTER_COPY.missing };
  }
  const text = a.status === "up" ? "↑ 升" : a.status === "down" ? "↓ 降" : "→ 平";
  return { label, value, dir: a.status, text };
}

/** PR 標籤名稱：與球員頁「官方進階・百分位 PR」同一組中文標籤（打者 bl／投手 pl）。 */
export function prLabel(key: string, role: RosterRole): string {
  const a = ADV.find((x) => x.pr === key);
  return a ? (role === "batting" ? a.bl : a.pl) : key;
}

/** 深讀連結：球員頁本季總覽，帶相同角色與層級（A 一軍／D 二軍）。球員頁目前沒有年度參數（只看本季）。 */
export function playerHref(m: RosterMember): string {
  const level = m.background.level === "D" ? "D" : "A";
  return `/players/${m.player_id}?scope=season&view=overview&role=${m.role}&level=${level}`;
}

/** 摘要端點相對路徑（S04 以 `CLIENT_API` 前綴、`no-store` 取；契約 §2、§4）。 */
export const rosterPath = (year: number, series: "E" | "C") => `/api/v1/playoffs/roster?season=${year}&series=${series}`;

export function teamLabel(t: RosterTeam): string {
  return t.team_name ?? t.team_code;
}

// —— 頁尾說明（僅留動態缺值／待更新提示；固定方法說明收進區塊標題 ⓘ Tooltip） ——————————————————

export const ROSTER_METHOD_HELP = [
  "官方公布的系列賽 32 人資格名單（非當場 28 人登錄或先發名單）。",
  "近 15 場箭頭比較例行賽最近與再前各 15 次出賽（打者 OPS+ 差 ≥15、投手 ERA+ 差 ≥20）；PR≥90 採官方進階數據。",
] as const;

/** 純函式、同步、不讀時鐘／window。只回動態缺資料／待更新說明。 */
export function rosterNotes(data: PlayoffsRoster | null): RosterNote[] {
  if (!data) return [];
  const out: RosterNote[] = [];
  for (const t of data.teams) {
    if (t.roster_status === "missing") {
      out.push({ key: `roster.roster_missing.${t.team_code}`,
        text: `${teamLabel(t)} 的系列賽名單尚未提交，暫不列出該隊球員。` });
    }
  }
  if (data.scopes.series.status === "pending_source" && data.scopes.series.pending_games?.length) {
    out.push({ key: "roster.series_box_pending",
      text: `本系列第 ${data.scopes.series.pending_games.join("、")} 場的逐場紀錄尚未送達，本系列實戰數據暫不含這幾場。` });
  }
  return out;
}

// —— 按需詳情（抽屜；契約 §2.2） ——————————————————————————————————————————————

export type RosterPlayerDetail = {
  contract: "playoffs-roster-player/v1";
  context_version: string | null;
  roster_version: string;
  series: "E" | "C";
  year: number;
  team_code: string;
  player: { player_id: string; name: string; official_position: string; tactical_role: string | null;
    role_format_version?: 1 | 2; tactical_roles?: string[]; role_provenance?: unknown;
    role: RosterRole; level: BackgroundLevel };
  ability: { season: AbilityCardData; career: AbilityCardData };
  trend: { player_id: string; role: RosterRole; items: StatRow[]; roll: number } | null;
};

export const DRAWER_COPY = {
  close: "關閉",
  open: "能力與走勢",
  loading: "載入中…",
  failed: "球員詳情暫時無法讀取。",
  stale: "資料已更新，請重開。",
  deepLink: "完整球員頁",
  abilitySeason: "本季能力（一軍）",
  abilityCareer: "生涯能力",
  abilityNone: "沒有可畫的能力圖。",
} as const;

export const rosterPlayerPath = (year: number, series: "E" | "C", playerId: string) =>
  `/api/v1/playoffs/roster/player?season=${year}&series=${series}&player_id=${playerId}`;

export type DrawerState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "stale" }
  | { kind: "ready"; detail: RosterPlayerDetail };

/** 詳情與目前區資料版本不同 ⇒ stale（⛔ 拼接不同版本的摘要與詳情；契約 §2.2）。 */
export function drawerState(detail: RosterPlayerDetail | null | undefined, failed: boolean,
  sectionVersion: string | null, sectionRosterVersion: string): DrawerState {
  if (failed) return { kind: "error" };
  if (!detail) return { kind: "loading" };
  if (detail.context_version !== sectionVersion || detail.roster_version !== sectionRosterVersion) return { kind: "stale" };
  return { kind: "ready", detail };
}

/** 能力卡：本季可畫就用本季，否則生涯；都不可畫 ⇒ null。 */
export function pickAbility(d: RosterPlayerDetail): { label: string; card: AbilityCardData } | null {
  if (d.ability.season?.available && d.ability.season.axes) return { label: DRAWER_COPY.abilitySeason, card: d.ability.season };
  if (d.ability.career?.available && d.ability.career.axes) return { label: DRAWER_COPY.abilityCareer, card: d.ability.career };
  return null;
}

/** 焦點陷阱：Tab 在最後一個 ⇒ 回第一個；Shift+Tab 在第一個 ⇒ 到最後一個；其餘交瀏覽器（回 null）。 */
export function trapFocus(index: number, count: number, shift: boolean): number | null {
  if (count === 0) return null;
  if (index < 0) return shift ? count - 1 : 0;
  if (shift && index === 0) return count - 1;
  if (!shift && index === count - 1) return 0;
  return null;
}
