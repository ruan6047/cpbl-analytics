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
  role: RosterRole;
  background: RosterBackground;
};

export type RosterTeam = {
  team_code: string;
  team_name: string | null;
  roster_status: "submitted" | "missing" | "unavailable";
  roster: { roster_id: string; published_date: string | null; source_url: string | null; annotation_version: number | null } | null;
  members: RosterMember[];
};

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
  scopes: { background: { status: string }; series: { status: string } };
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
  sortLabel: "排序",
  all: "全部",
  farm: "二軍",
  roleSource: "本站角色",
} as const;

export type RosterSort = "position" | "games" | "arrow";
export const SORTS: { key: RosterSort; label: string }[] = [
  { key: "position", label: "官方守位" },
  { key: "games", label: "出賽 G" },
  { key: "arrow", label: "箭頭方向" },
];

/** 箭頭方向排序序：上升 → 平穩 → 下降 → 無箭頭。 */
const ARROW_ORDER: Record<ArrowStatus, number> = { up: 0, flat: 1, down: 2, insufficient: 3, undefined: 3 };

const POSITION_ORDER: Record<string, number> = { 投手: 0, 捕手: 1, 內野手: 2, 外野手: 3 };

/** 排序：守位（官方序、同守位依 player_id）；出賽 G（多到少，無紀錄排最後，同 G 依守位）。不改原陣列。 */
export function sortMembers(members: readonly RosterMember[], sort: RosterSort): RosterMember[] {
  const pos = (m: RosterMember) => POSITION_ORDER[m.official_position] ?? 99;
  const byPos = (a: RosterMember, b: RosterMember) => pos(a) - pos(b) || a.player_id.localeCompare(b.player_id);
  if (sort === "games") {
    return [...members].sort((a, b) => (b.background.g ?? -1) - (a.background.g ?? -1) || byPos(a, b));
  }
  if (sort === "arrow") {
    const k = (m: RosterMember) => ARROW_ORDER[m.background.arrow?.status ?? "insufficient"] ?? 3;
    return [...members].sort((a, b) => k(a) - k(b) || byPos(a, b));
  }
  return [...members].sort(byPos);
}

const r3 = (v: number | null) => (v == null ? ROSTER_COPY.missing : v.toFixed(3).replace(/^0\./, "."));

/** 出賽 G：無紀錄 ⇒「—」。 */
export const gText = (bg: RosterBackground) => (bg.g == null ? ROSTER_COPY.missing : `${bg.g}G`);

/** 背景一行（傳統計數，後端已算率）：打者打擊率／OPS、投手防禦率／局數。無紀錄 ⇒ null。 */
export function lineText(m: RosterMember): string | null {
  const l = m.background.line;
  if (!l) return null;
  if (m.role === "pitching") {
    const p = l as PitchingLine;
    return `防禦率 ${p.era == null ? ROSTER_COPY.missing : p.era.toFixed(2)} · ${p.ip} 局`;
  }
  const b = l as BattingLine;
  return `打擊率 ${r3(b.avg)} · OPS ${r3(b.ops)}`;
}

/** 小卡冷熱箭頭：末段 15 次的 OPS+／ERA+ 與方向（方向一律附文字，⛔ 只靠顏色）。無箭頭 ⇒ 方向 null、值「—」。 */
export function arrowView(m: RosterMember): { label: string; value: string; dir: "up" | "down" | "flat" | null; text: string } {
  const a = m.background.arrow;
  const label = a?.metric === "era_plus" ? "末段 15 次 ERA+" : "末段 15 次 OPS+";
  const v = a?.w1?.value;
  const value = a && (a.status === "up" || a.status === "down" || a.status === "flat") && v != null
    ? String(Math.round(v)) : ROSTER_COPY.missing;
  if (!a || !(a.status === "up" || a.status === "down" || a.status === "flat")) {
    return { label, value, dir: null, text: ROSTER_COPY.missing };
  }
  const text = a.status === "up" ? "↑ 較前 15 次上升" : a.status === "down" ? "↓ 較前 15 次下降" : "→ 平穩";
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

// —— 頁尾說明（契約 §2.4、§2.5、§9；交 #285 對齊的文字） ——————————————————————————

const FIXED: RosterNote[] = [
  { key: "roster.registration_unknown", text: "當場 28 人登錄本站尚未取得。" },
  { key: "roster.eligibility_not_availability",
    text: "名單是官方公布的系列賽 32 人資格名單，不代表當場登錄、先發或可出賽。" },
  { key: "roster.appearance_g", text: "出賽 G 依官方逐場紀錄計算，代跑、守備出場也算一場；保留續賽與原比賽算同一場。" },
  { key: "roster.official_pr_only",
    text: "PR≥90 標籤只採官方進階數據的百分位（本季一軍例行賽、同角色）；官方沒有提供的球員不標，本站不自行排名。",
    source: { label: "官方進階數據", url: "https://stats.cpbl.com.tw" } },
  { key: "roster.arrow_proposed",
    text: "冷熱箭頭比較一軍例行賽最近與再前各 15 次出賽：打者 OPS+ 差 15 以上、投手 ERA+ 差 20 以上才標示，門檻為本站建議值，不代表未來表現。" },
];

/** 純函式、同步、不讀時鐘／window。`notes(null)` 只回固定說明；依資料者隨畫面上那份資料重算。 */
export function rosterNotes(data: PlayoffsRoster | null): RosterNote[] {
  const out = [...FIXED];
  if (!data) return out;
  for (const t of data.teams) {
    if (t.roster_status === "missing") {
      out.push({ key: `roster.roster_missing.${t.team_code}`,
        text: `${teamLabel(t)} 的系列賽名單尚未提交，暫不列出該隊球員。` });
    }
  }
  if (data.teams.some((t) => t.members.some((m) => m.background.arrow
    && (m.background.arrow.status === "insufficient" || m.background.arrow.status === "undefined")))) {
    out.push({ key: "roster.arrow_unavailable",
      text: "未滿 30 次出賽、任一段打者打數或投手局數不足（打數 30、10 局），或防禦率為 0 無法計算 ERA+ 時，不顯示箭頭。" });
  }
  if (data.teams.some((t) => t.members.some((m) => m.background.level === "D"))) {
    out.push({ key: "roster.farm_background",
      text: "本季一軍沒有出賽紀錄的球員仍列在名單，改列二軍成績並標「二軍」，不換算一軍 PR 或 OPS+。" });
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
  sectionVersion: string | null): DrawerState {
  if (failed) return { kind: "error" };
  if (!detail) return { kind: "loading" };
  if (detail.context_version !== sectionVersion) return { kind: "stale" };
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
