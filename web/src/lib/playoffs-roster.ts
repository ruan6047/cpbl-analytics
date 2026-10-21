// #286 S05：季後賽第 3 區「系列賽 32 人資格名單」型別、排字與頁尾說明（`playoffs-roster/v1`）。
// #350 方案 D：兩隊並列、依位置分區、每區先列綜合成績再列人名（分區與合計是本檔純函式）。
//
// - 個人統計、層級由後端算（PRD「前後端責任」）；區塊綜合成績在這裡以後端給的原始計數「先加總再算率」。
// - 說明性注意事項（28 人登錄、資格≠可用、G 定義、PR 來源、二軍背景）⛔ 在區內就地顯示，一律經
//   `rosterNotes(data)` 交 S04 頁尾（需求方 Q4、#281 6194693029；#285 掛點契約 §2.4、§2.5）。格內只留「—」「待更新」。
// - 頁尾 key 一律 `roster.*`（#285 裁定 6195728927：G1 前不用 `common.*`）。

import type { Card as AbilityCardData } from "@/components/ability-card";
import type { StatRow } from "@/lib/client";

export type RosterRole = "batting" | "pitching";
export type BackgroundLevel = "A" | "D" | "none";

export type BattingLine = {
  pa: number; ab: number; h: number; hr: number; bb: number;
  /** #350 補輸出的原始計數（算區塊 OBP／SLG）；舊回應沒有 ⇒ 區塊 OPS「—」。 */
  hbp?: number; sf?: number; tb?: number;
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
  /** #350（只有野手）：例行賽一軍各守位出賽（g 降冪）與主守位；無一軍守備紀錄 ⇒ [] 與 null。舊回應不帶。 */
  positions?: { pos: string; g: number }[];
  primary_position?: string | null;
  /** #350（只有野手）：例行賽 DH 先發場數；`dh_starts_unknown`＝先發但判不出守位的場數（⛔ 當 0）。 */
  dh_starts?: number | null;
  dh_starts_unknown?: number;
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
  series?: { g: number | null; line: BattingLine | PitchingLine | null; pending?: boolean;
    /** #350（只有野手）：本系列 DH 先發；來源待更新 ⇒ null。 */
    dh_starts?: number | null; dh_starts_unknown?: number } | null;
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
  heading: "系列賽名單",
  loadFailed: "第 3 區資料暫時無法讀取，其他區不受影響。",
  seriesUnknown: "對戰組合尚未確定。",
  pending: "待更新",
  missing: "—",
  farm: "二軍",
  scopeLabel: "資料範圍",
  pitchers: "投手",
  fielders: "野手（依主守位）",
  legend: { background: "灰底是該位置的綜合成績（例行賽一軍成員合計）；點名字看個人成績與能力。",
    series: "灰底是該位置的綜合成績（本系列成員合計）；點名字看個人成績與能力。" },
} as const;

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

/** 該 scope 的出賽 G：背景＝例行賽 G；系列＝本系列 G（無完賽場 ⇒ null）。 */
export const scopeG = (m: RosterMember, scope: RosterScope): number | null =>
  scope === "series" ? (m.series && !m.series.pending ? m.series.g : null) : m.background.g;

/** 本系列來源未齊（該隊缺這名球員角色的來源）⇒ 格內「待更新」。 */
export const seriesPending = (m: RosterMember, scope: RosterScope) => scope === "series" && !!m.series?.pending;

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

/** 抽屜標頭的個人數值（#350：主視圖只列人名，個人數值點開才看）。
 *  例：「例行賽 120G · AVG .263 · OPS .664 · 游擊手 35G · DH 先發 22」；本系列來源未齊 ⇒「本系列 待更新」。 */
export function drawerStatLine(m: RosterMember, scope: RosterScope = "background"): string {
  const series = scope === "series";
  const label = series ? "本系列" : "例行賽";
  if (seriesPending(m, scope)) return `${label} ${ROSTER_COPY.pending}`;
  const l = series ? m.series?.line ?? null : m.background.line;
  const parts = [`${label} ${gText({ g: scopeG(m, scope) })}`];
  if (l && m.role === "pitching") {
    const p = l as PitchingLine;
    parts.push(`ERA ${p.era == null ? ROSTER_COPY.missing : p.era.toFixed(2)}`, `${p.ip} 局`);
  } else if (l) {
    const b = l as BattingLine;
    parts.push(`AVG ${r3(b.avg)}`, `OPS ${r3(b.ops)}`);
  }
  if (m.role === "batting") {
    const top = m.background.positions?.[0];
    if (!series && top) parts.push(`${top.pos} ${top.g}G`);
    const dh = series ? m.series?.dh_starts : m.background.dh_starts;
    if (dh != null && dh > 0) parts.push(`DH 先發 ${dh}`);
  }
  return parts.join(" · ");
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

// —— #350 方案 D：位置分區與區塊綜合成績（純函式） ——————————————————————————————————

/** 投手角色區順序（規劃 §1.1）；`輪值` 是 v1 舊值，排在先發之後。其他未列的角色依出現序接在後面。 */
export const PITCHER_ROLE_ORDER = ["先發", "輪值", "長中繼", "中繼", "勝利組", "拆彈組", "終結"] as const;
/** 野手主守位區順序（與後端 `FIELD_POSITION_ORDER` 同序）。 */
export const FIELD_POSITIONS = ["捕手", "一壘手", "二壘手", "三壘手", "游擊手", "左外野手", "中外野手", "右外野手"] as const;
/** DH 區門檻（需求方裁定 #350 6310001489）：例行賽背景「DH 先發超過三場」＝≥4；本系列 ≥1。⛔ 讓使用者調。 */
export const DH_MIN_STARTS: Record<RosterScope, number> = { background: 4, series: 1 };

export const DH_BLOCK_LABEL = "指定打擊（DH）";
export const NO_ROLE_LABEL = "未標角色";
export const NO_FIELDING_LABEL = "其他（無一軍守備紀錄）";

export type BlockMember = {
  m: RosterMember;
  /** 例行賽背景只有二軍成績（不計入綜合成績，名字旁標「二軍」）。 */
  farm: boolean;
  /** DH 區：已知場數未達門檻，但加上判不出守位的場數可能達到 ⇒ 名字旁標「待更新」（⛔ 當成未達）。 */
  uncertain: boolean;
};

/** 區塊綜合成績：可算 ⇒ 兩個數字；整區無資料 ⇒ empty（「—」）；有成員來源未齊或 DH 判不出 ⇒ pending（「待更新」）。 */
export type Composite =
  | { kind: "batting"; avg: number | null; ops: number | null }
  | { kind: "pitching"; era: number | null; ip: string | null }
  | { kind: "pending" }
  | { kind: "empty" };

export type BlockColumn = { team_code: string; submitted: boolean; members: BlockMember[]; composite: Composite };
export type RosterBlock = { key: string; label: string; role: RosterRole; note?: string; columns: BlockColumn[] };

const scopeLine = (m: RosterMember, scope: RosterScope) =>
  scope === "series" ? m.series?.line ?? null : m.background.level === "A" ? m.background.line : null;

/** 打擊綜合：ΣH／ΣAB；OBP＝(ΣH+ΣBB+ΣHBP)／(ΣAB+ΣBB+ΣHBP+ΣSF)、SLG＝ΣTB／ΣAB（先加總再算率，⛔ 平均個人率）。
 *  分母 0 ⇒ null；任一成員缺 tb／hbp／sf（舊回應）⇒ OPS null。背景只計一軍 A（二軍計數不混入）。 */
export function battingComposite(members: readonly RosterMember[], scope: RosterScope): Composite {
  if (members.some((m) => seriesPending(m, scope))) return { kind: "pending" };
  const lines = members.map((m) => scopeLine(m, scope) as BattingLine | null).filter((l): l is BattingLine => !!l);
  if (!lines.length) return { kind: "empty" };
  const sum = (k: keyof BattingLine) => lines.reduce((a, l) => a + ((l[k] as number | undefined) ?? 0), 0);
  const ab = sum("ab"), h = sum("h"), bb = sum("bb"), hbp = sum("hbp"), sf = sum("sf"), tb = sum("tb");
  const complete = lines.every((l) => l.tb != null && l.hbp != null && l.sf != null);
  const den = ab + bb + hbp + sf;
  const obp = complete && den ? (h + bb + hbp) / den : null;
  const slg = complete && ab ? tb / ab : null;
  return { kind: "batting", avg: ab ? h / ab : null, ops: obp != null && slg != null ? obp + slg : null };
}

/** 投球綜合：ERA＝ΣER×27／Σouts、局數＝Σouts 換算 x.y（先加總再算；outs 0 ⇒ ERA null）。 */
export function pitchingComposite(members: readonly RosterMember[], scope: RosterScope): Composite {
  if (members.some((m) => seriesPending(m, scope))) return { kind: "pending" };
  const lines = members.map((m) => scopeLine(m, scope) as PitchingLine | null).filter((l): l is PitchingLine => !!l);
  if (!lines.length) return { kind: "empty" };
  const outs = lines.reduce((a, l) => a + (l.outs ?? 0), 0);
  const er = lines.reduce((a, l) => a + (l.er ?? 0), 0);
  return { kind: "pitching", era: outs ? (er * 27) / outs : null, ip: `${Math.floor(outs / 3)}.${outs % 3}` };
}

/** 綜合成績顯示字：分母 0／無資料 ⇒「—」、待更新 ⇒「待更新」。 */
export function compositeParts(c: Composite): { label: string; value: string }[] | string {
  if (c.kind === "pending") return ROSTER_COPY.pending;
  if (c.kind === "empty") return ROSTER_COPY.missing;
  if (c.kind === "pitching") {
    return [{ label: "ERA", value: c.era == null ? ROSTER_COPY.missing : c.era.toFixed(2) },
      { label: "局", value: c.ip ?? ROSTER_COPY.missing }];
  }
  return [{ label: "AVG", value: r3(c.avg) }, { label: "OPS", value: r3(c.ops) }];
}

/** 兩隊頂部組成：「投手 15 · 捕手 3 · 內野 8 · 外野 6」（官方守位）。 */
export function teamComposition(t: RosterTeam): string {
  const n = (p: string) => t.members.filter((m) => m.official_position === p).length;
  return [["投手", "投手"], ["捕手", "捕手"], ["內野", "內野手"], ["外野", "外野手"]]
    .map(([label, p]) => `${label} ${n(p)}`).join(" · ");
}

const byId = (a: RosterMember, b: RosterMember) => a.player_id.localeCompare(b.player_id);
/** 區內排序鍵：多到少；無紀錄（null）排最後。 */
const desc = (k: (m: RosterMember) => number | null | undefined) =>
  (a: RosterMember, b: RosterMember) => (k(b) ?? -1) - (k(a) ?? -1) || byId(a, b);

function column(t: RosterTeam, members: RosterMember[], scope: RosterScope, role: RosterRole,
  uncertain: ReadonlySet<string> = new Set(), forcePending = false): BlockColumn {
  const counted = members.filter((m) => !uncertain.has(m.player_id));
  const composite: Composite = forcePending || uncertain.size ? { kind: "pending" }
    : role === "pitching" ? pitchingComposite(counted, scope) : battingComposite(counted, scope);
  return {
    team_code: t.team_code, submitted: t.roster_status === "submitted", composite,
    members: members.map((m) => ({ m, farm: scope === "background" && m.background.level === "D",
      uncertain: uncertain.has(m.player_id) })),
  };
}

const submittedMembers = (t: RosterTeam, role: RosterRole) =>
  t.roster_status === "submitted" ? t.members.filter((m) => m.role === role) : [];

/** 投手段：依本站角色分區（同人多角色 ⇒ 多區各列一次）；無角色 ⇒「未標角色」。兩隊都沒有的角色整區省略。
 *  區內依本範圍出賽 G 多到少。v2 角色資料不完整照常拋錯（`memberRoles`）。 */
export function pitcherBlocks(teams: readonly RosterTeam[], scope: RosterScope): RosterBlock[] {
  const roles = new Map<string, RosterMember[][]>();
  const order: string[] = [...PITCHER_ROLE_ORDER];
  teams.forEach((t, i) => {
    for (const m of submittedMembers(t, "pitching")) {
      const rs = memberRoles(m);
      for (const r of rs.length ? rs : [NO_ROLE_LABEL]) {
        if (!order.includes(r)) order.push(r);
        const cols = roles.get(r) ?? teams.map(() => []);
        cols[i].push(m);
        roles.set(r, cols);
      }
    }
  });
  const sort = desc((m) => scopeG(m, scope));
  return order.filter((r) => roles.has(r)).map((r) => ({
    key: `pit-${r}`, label: r, role: "pitching" as const,
    columns: teams.map((t, i) => column(t, [...roles.get(r)![i]].sort(sort), scope, "pitching")),
  }));
}

/** 野手所屬區：主守位（例行賽一軍出賽最多）；有新欄位但無一軍守備紀錄 ⇒「其他」；
 *  舊回應（無 `positions`）⇒ 退回官方守位大類（捕手／內野手／外野手），⛔ 拋錯。 */
export function fielderArea(m: RosterMember): string {
  if (m.background.positions === undefined) return m.official_position;
  return m.background.primary_position ?? NO_FIELDING_LABEL;
}

/** DH 區成員判定（門檻 `DH_MIN_STARTS`）：in＝達門檻；uncertain＝未達但加上 unknown 可能達到；
 *  null ⇒ 該範圍判不出（本系列來源待更新）。舊回應無欄位 ⇒ out。 */
export function dhStatus(m: RosterMember, scope: RosterScope): "in" | "out" | "uncertain" | null {
  if (m.role !== "batting") return "out";
  const src = scope === "series" ? m.series : m.background;
  if (!src || src.dh_starts === undefined) return "out";
  if (src.dh_starts === null) return null;
  const min = DH_MIN_STARTS[scope];
  if (src.dh_starts >= min) return "in";
  return src.dh_starts + (src.dh_starts_unknown ?? 0) >= min ? "uncertain" : "out";
}

/** 野手段：依主守位分區（每人只出現在主守位區）＋DH 區（隨資料範圍切換；列入者仍在主守位區）。
 *  區內排序：背景＝該守位出賽多到少（DH 區＝DH 先發多到少）；本系列＝本系列出賽多到少。 */
export function fielderBlocks(teams: readonly RosterTeam[], scope: RosterScope): RosterBlock[] {
  const legacy = teams.some((t) => t.members.some((m) => m.role === "batting" && m.background.positions === undefined));
  const areas: string[] = legacy ? ["捕手", "內野手", "外野手"] : [...FIELD_POSITIONS, NO_FIELDING_LABEL];
  const out: RosterBlock[] = [];
  for (const area of areas) {
    const cols = teams.map((t) => submittedMembers(t, "batting").filter((m) => fielderArea(m) === area));
    if (!cols.some((c) => c.length)) continue;
    const sort = scope === "series" ? desc((m) => scopeG(m, scope))
      : desc((m) => m.background.positions?.find((p) => p.pos === area)?.g ?? m.background.g);
    out.push({ key: `fld-${area}`, label: area, role: "batting",
      columns: teams.map((t, i) => column(t, cols[i].sort(sort), scope, "batting")) });
  }
  if (!legacy) {
    const sort = scope === "series" ? desc((m) => m.series?.dh_starts ?? null) : desc((m) => m.background.dh_starts);
    const cols = teams.map((t) => {
      const bat = submittedMembers(t, "batting");
      const st = new Map(bat.map((m) => [m.player_id, dhStatus(m, scope)]));
      const members = bat.filter((m) => st.get(m.player_id) === "in" || st.get(m.player_id) === "uncertain").sort(sort);
      const uncertain = new Set(members.filter((m) => st.get(m.player_id) === "uncertain").map((m) => m.player_id));
      // 本系列來源待更新（dh_starts null）⇒ 這隊 DH 區整欄判不出，綜合成績「待更新」。
      return column(t, members, scope, "batting", uncertain, bat.some((m) => st.get(m.player_id) === null));
    });
    if (cols.some((c) => c.members.length || c.composite.kind === "pending")) {
      out.push({ key: "fld-DH", label: DH_BLOCK_LABEL, role: "batting",
        note: `${scope === "series" ? "本系列" : "例行賽"} DH 先發 ≥${DH_MIN_STARTS[scope]} 場`, columns: cols });
    }
  }
  return out;
}

// —— 頁尾說明（僅留動態缺值／待更新提示；固定方法說明收進區塊標題 ⓘ Tooltip） ——————————————————

export const ROSTER_METHOD_HELP = [
  "官方公布的系列賽 32 人資格名單（非當場 28 人登錄或先發名單）。",
  "投手依本站角色分區、野手依例行賽一軍出賽最多的守位（主守位）分區；灰底綜合成績是該區成員的合計（先加總再算率），不是「打該守位時」的成績。",
  "指定打擊區：例行賽背景列例行賽 DH 先發 4 場以上，本系列實戰列本系列 DH 先發 1 場以上；列入者仍留在主守位區。",
  "同一人可能出現在多區（投手多角色、野手同時在守位區與 DH 區），各區分別計入。",
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
