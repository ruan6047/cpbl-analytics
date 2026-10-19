// #289 S08：第 4 區 watch 讀取面型別與顯示文字（後端 `playoffs-watch/v1`）。
//
// 燈號、完整性、門檻全在後端 `cpbl.playoffs.watch_rules` 算好；這裡只做「代碼 → 中文」對照，
// ⛔ 不重做統計門檻、⛔ 不把灰色補成任何等級。獨立於 S04 的 `playoffs-types.ts`。

export type GameKey = { year: number; kind_code: string; game_sno: number };

export type LoadLevel = "high" | "medium" | "low" | "unknown" | "starter_exempt";
export type LoadMetric = "P0" | "P1" | "S2" | "S3" | "C" | "Q";

export type LoadDay = {
  date: string;
  offset: number;
  pitches: number;
  appearances: number;
  complete: boolean;
  live: boolean;
};

export type Load = {
  policy_version: string;
  target_date: string;
  level: LoadLevel;
  label: string;
  complete: boolean;
  metrics: Record<LoadMetric, number | null>;
  c_at_least: boolean;
  triggers: { metric: LoadMetric; value: number; threshold: number }[];
  days: LoadDay[];
  incomplete: { date: string; offset: number; reasons: string[]; text: string[] }[];
  unattributed: { game_key: GameKey; pitches: number | null; possible_dates: string[] }[];
  live: boolean;
  last_pitch_date: string | null;
  full_rest_days: number | null;
  rest_unknown_reason: string | null;
};

export type RecentAppearance = {
  game_key: GameKey;
  date: string | null;
  date_trusted: boolean;
  role_type: string | null;
  pitches: number | null;
  outs: number | null;
  ip: string | null;
};

export type ConsecutiveEra = {
  scope: string;
  appearances: number;
  outs: number | null;
  ip: string | null;
  er: number | null;
  era: number | null;
  complete: boolean;
  excluded_untrusted: number;
};

export type WatchPitcher = {
  player_id: string;
  name: string | null;
  tactical_role: string | null;
  role_format_version?: 1 | 2;
  tactical_roles?: string[];
  role_provenance?: unknown;
  role_source: string;
  default_visible: boolean;
  load: Load;
  recent: RecentAppearance[];
  registration: { status: string; text: string };
  consecutive_era: ConsecutiveEra | null;
};

export type WatchTeam = {
  side: "away" | "home";
  team_code: string;
  roster_status: "submitted" | "missing" | "unavailable";
  roster: { roster_id: string; published_date: string | null; source_url: string | null;
    annotation_version: number | null; role_format_version?: 1 | 2; revision_hash?: string | null; note: string } | null;
  roster_text: string | null;
  days: { date: string; offset: number; complete: boolean; reasons: string[]; text: string[]; live: boolean }[];
  pitchers: WatchPitcher[];
};

/** 官方先發的賽前歷程分類（#320 A2；後端 `cpbl.playoffs.starter_classification`）。
 *  changed＝賽前出現過其他先發（`text`「{姓名}（已更換）」）；retracted＝先前公告後清空（`text`
 *  「待公告（先前公告已撤回）」）；`status` 值域不變。舊 API 沒有此欄。 */
export type StarterClassification = "announced" | "changed" | "retracted" | "pending" | "unknown";

/** 官方先發投手（#314、#320）：後端讀官方賽程現行列判定，前端只排 `text`。
 *  announced＝已公告（`text` 為姓名，查無姓名時為「已公告（姓名待更新）」，更換時加「（已更換）」）；
 *  pending＝「待公告」（撤回時為「待公告（先前公告已撤回）」）；unknown＝來源讀取失敗「暫時無法取得」。
 *  ⛔ 無公告時間（需求方裁定 #314 Q1）；更換標示依 #320 6261389955（取代 #314 Q3）。 */
export type WatchStarter = {
  team_code: string;
  status: "announced" | "pending" | "unknown";
  reason: string | null;
  player_id: string | null;
  name: string | null;
  text: string;
  classification?: StarterClassification;
};

/** 多重角色平列；只允許legacy資料讀單值，v2缺陣列不可降級。 */
export function pitcherRoles(p: WatchPitcher): string[] {
  if (p.role_format_version === 2) {
    if (!Array.isArray(p.tactical_roles) || !p.tactical_roles.length) throw new Error("角色v2資料不完整");
    return p.tactical_roles;
  }
  if (p.role_format_version != null && p.role_format_version !== 1) throw new Error("未知角色格式");
  return p.tactical_roles ?? (p.tactical_role && p.tactical_role !== "unclassified" ? [p.tactical_role] : []);
}

export type PlayoffsWatch = {
  contract: "playoffs-watch/v1";
  status: "ok" | "historical_not_published" | "not_target" | "no_target" | "game_unknown" | "series_unknown";
  text?: string;
  policy_version: string;
  year: number;
  series: "E" | "C";
  series_id: unknown;
  context_version: string | null;
  watch_version: string;
  target_game_key: GameKey | null;
  requested_game_key: GameKey | null;
  target?: { game_key: GameKey; game_date: string | null; target_status: string | null;
    away_team_code: string; home_team_code: string };
  as_of: { now: string; taipei_date: string; last_refresh_at: string | null; last_completed_game_date: string | null };
  scope: { kinds: string[]; note: string };
  coverage: "complete" | "partial" | "incomplete" | "unknown";
  missing_reason: string[];
  source_manifest: { source: string; status: string }[];
  registration: { status: string; reason: string; text: string };
  starters?: WatchStarter[];
  /** 整場先發分類（#320 A2）：剛好一隊已公告（含更換）＝partial；畫面不另加標籤。舊 API 沒有。 */
  starters_classification?: "announced" | "partial" | "pending" | "unknown";
  teams: WatchTeam[];
};

const API_URL = process.env.API_URL ?? "http://localhost:4001";

/** 第 4 區讀取（失敗回 null，由元件顯示錯誤態，不影響其他區）。
 *  本元件不自設輪詢：S04 頁面每 30 秒刷新時重新呼叫本函式（或自行 fetch 同一端點）帶動重取。
 *  `revalidate` 預設 0（不經 Next 資料快取），避免快取疊在 30 秒輪詢上變成兩個間隔的延遲；
 *  S04 若要跨訪客共用快取，可傳不超過輪詢間隔的秒數。 */
export async function fetchPlayoffsWatch(
  season: number, series: "E" | "C", game?: number, opts: { revalidate?: number } = {},
): Promise<PlayoffsWatch | null> {
  const q = new URLSearchParams({ season: String(season), series });
  if (game != null) q.set("game", String(game));
  const revalidate = opts.revalidate ?? 0;
  try {
    const res = await fetch(`${API_URL}/api/v1/playoffs/watch?${q}`,
      revalidate > 0 ? { next: { revalidate } } : { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as PlayoffsWatch;
  } catch {
    return null;
  }
}

/** 燈號文字：顏色旁一律有文字（狀態不只靠顏色）。 */
export const LEVEL_TEXT: Record<LoadLevel, string> = {
  high: "高負荷",
  medium: "中負荷",
  low: "低負荷",
  unknown: "未知",
  starter_exempt: "先發投手，不套用牛棚負荷燈號",
};

/** 燈號色（設計系統 token）：紅＝down、橘＝strike、綠＝ball、灰＝faint；先發不套燈號＝無色。 */
export const LEVEL_TONE: Record<LoadLevel, { dot: string; text: string }> = {
  high: { dot: "bg-down", text: "text-down" },
  medium: { dot: "bg-strike", text: "text-strike" },
  low: { dot: "bg-ball", text: "text-ball" },
  unknown: { dot: "bg-faint", text: "text-faint" },
  starter_exempt: { dot: "border border-line-strong bg-transparent", text: "text-muted" },
};

/** 觸發理由 → 一句話（值與門檻都由後端給，前端只排字）。 */
export function triggerText(t: { metric: LoadMetric; value: number; threshold: number }): string {
  switch (t.metric) {
    case "P0": return `今日已投 ${t.value} 球（≥${t.threshold}）`;
    case "P1": return `前一日 ${t.value} 球（≥${t.threshold}）`;
    case "S2": return `近 2 日共 ${t.value} 球（≥${t.threshold}）`;
    case "S3": return `近 3 日共 ${t.value} 球（≥${t.threshold}）`;
    case "C": return `連續 ${t.value} 日登板（≥${t.threshold}）`;
    case "Q": return `今日已登板 ${t.value} 次（≥${t.threshold}）`;
  }
}

export const ROSTER_ROLE_TEXT = "角色為本站註記，非官方數據";

/** 台北時間「10/17 16:05」；無值回 null。 */
export function taipeiTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Taipei", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const v = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${v("month")}/${v("day")} ${v("hour")}:${v("minute")}`;
}

/** 「2026-10-14」→「10/14」。 */
export function shortDate(iso: string | null | undefined): string {
  return iso ? `${iso.slice(5, 7)}/${iso.slice(8, 10)}` : "—";
}

/** D−k 標籤：0 ＝「今日」。 */
export function offsetLabel(k: number): string {
  return k === 0 ? "今日" : `D−${k}`;
}

const KIND_SHORT: Record<string, string> = { A: "例行", E: "挑戰賽", C: "台灣大賽", D: "二軍" };

export function appearanceText(a: RecentAppearance): string {
  const when = a.date ? shortDate(a.date) : "日期未定";
  const kind = KIND_SHORT[a.game_key.kind_code] ?? a.game_key.kind_code;
  const g = a.game_key.kind_code === "E" || a.game_key.kind_code === "C" ? `G${a.game_key.game_sno}` : "";
  const pitches = a.pitches == null ? "球數未知" : `${a.pitches} 球`;
  const ip = a.ip == null ? "" : `・${a.ip} 局`;
  return `${when} ${kind}${g} ${pitches}${ip}${a.date_trusted ? "" : "（保留賽，日期未定）"}`;
}
