// UX-PLAYER-IA1 prototype 共用定義：fixture 註冊、四層 IA 骨架、模組安置（遷移 map 的程式化版本）。
// fixture 為 scripts/capture_player_ia_fixtures.py 擷取的真實 API 回應（逐球陣列截斷至 400 筆）。
import type { StatRow } from "@/lib/client";
import batterFx from "./fixtures/batter.json";
import pitcherFx from "./fixtures/pitcher.json";
import twowayFx from "./fixtures/twoway.json";
import farmFx from "./fixtures/farm.json";
import retiredFx from "./fixtures/retired.json";

export type Role = "batting" | "pitching";

export type RoleData = {
  discipline: {
    summary: Record<string, number | null>;
    quality: Record<string, number | null>;
    points: unknown[];
    spray: unknown[];
    batted: unknown[];
    points_total?: number;
    spray_total?: number;
  };
  pitchMix: { items: { bucket: string; n: number; mix: { pitch_type: string; pct: number }[] }[] };
  arsenal: { items: { pitch_type: string; n: number; usage: number; avg_speed: number | null; whiff_pct: number | null }[] };
  trend: { items: StatRow[] };
  trendCareer: { items: StatRow[] };
  vsTeam: { items: StatRow[] };
  career: { seasons: StatRow[] };
  sabr: { years: { year: number; re24: string | null; rnk: number | null; n: number | null; wsb?: string | null }[]; catcher?: unknown[] };
  traits: { traits: Record<string, number | string | null> | null };
  splitsSeason: { items: StatRow[] };
  splitsCareer: { items: StatRow[] };
  movement?: {
    summary: { pt: string; n: number; usage: number; speed: number | null; ivb: number | null; hb: number | null }[];
    release: { consistency_cm: number | null };
  };
};

export type Fixture = {
  _meta: { scenario: string; id: string; name: string; roles: Role[]; kind: "A" | "D" };
  profile: { player: Record<string, unknown> & {
    name: string; team: string | null; position: string | null; roster_level: string | null;
    is_batter: boolean; is_pitcher: boolean; was_batter: boolean; was_pitcher: boolean;
    farm_batter: boolean; farm_pitcher: boolean; bats?: string | null; throws?: string | null;
  } };
  season: { batting: StatRow | null; pitching: StatRow | null };
  advanced: { batting: StatRow | null; pitching: StatRow | null };
  careerStats: {
    batting: (Record<string, number | null> & { seasons: number }) | null;
    pitching?: (Record<string, number | null> & { seasons: number; ip: string }) | null;
    best: Record<string, { year: number; value: number } | null>;
    awards?: { year: number; category: string; award: string }[];
    teams?: { code: string; name: string; from: number; to: number }[];
  };
  abilityCard: {
    batting?: { season?: AbilitySide; career?: AbilitySide };
    pitching?: { season?: AbilitySide; career?: AbilitySide };
  };
  fieldingSeason: { items: StatRow[] };
  fieldingCareer: { items: StatRow[]; from_year?: number };
  batting?: RoleData;
  pitching?: RoleData;
};

type AbilitySide = { available?: boolean; overall?: number | null; axes?: { key: string; label: string; pr: number | null }[] };

export const FIXTURES: Record<string, Fixture> = {
  batter: batterFx as unknown as Fixture,
  pitcher: pitcherFx as unknown as Fixture,
  twoway: twowayFx as unknown as Fixture,
  farm: farmFx as unknown as Fixture,
  retired: retiredFx as unknown as Fixture,
};

export const SCENARIOS: { key: string; label: string; note: string }[] = [
  { key: "batter", label: "打者（郭天信）", note: "一軍打者，全模組有資料" },
  { key: "pitcher", label: "投手（羅戈）", note: "一軍投手，含球路位移" },
  { key: "twoway", label: "雙棲（余德龍）", note: "打擊＋投球雙 role tab" },
  { key: "farm", label: "二軍＋tracking 缺漏（張偉聖）", note: "二軍鏡頭，逐球僅 14 球（缺漏態）" },
  { key: "retired", label: "退役（彭政閔）", note: "本季全空，預設落在生涯層" },
];

// ---- 四層 IA 骨架（藍圖 §5.7 已核可，本 prototype 凍結細節）----

export type LayerId = "overview" | "approach" | "splits" | "career";

export const LAYERS: { id: LayerId; label: (role: Role) => string }[] = [
  { id: "overview", label: () => "總覽" },
  { id: "approach", label: (role) => (role === "pitching" ? "球路" : "打法") },
  { id: "splits", label: () => "分項與對戰" },
  { id: "career", label: () => "生涯" },
];

export const VARIANTS = ["tabs", "anchors", "hybrid"] as const;
export type Variant = (typeof VARIANTS)[number];

export const VARIANT_LABELS: Record<Variant, string> = {
  tabs: "A・Tabs（單層渲染）",
  anchors: "B・錨點長頁（scrollspy）",
  hybrid: "C・Hybrid（總覽常駐＋分層切換）",
};

// role 顯示規則（沿用現行頁：is_* / was_* / farm_* 任一即列該 role tab）
export function rolesOf(fx: Fixture): { v: Role; label: string }[] {
  const p = fx.profile.player;
  const out: { v: Role; label: string }[] = [];
  if (p.is_batter || p.was_batter || p.farm_batter) out.push({ v: "batting", label: "打擊" });
  if (p.is_pitcher || p.was_pitcher || p.farm_pitcher) out.push({ v: "pitching", label: "投球" });
  if (!out.length) out.push({ v: "batting", label: "打擊" });
  return out;
}

export function defaultRole(fx: Fixture): Role {
  return rolesOf(fx)[0].v;
}

// 退役（roster_level=null）：本季模組全空 → 預設層落在生涯
export function isRetired(fx: Fixture): boolean {
  return !fx.profile.player.roster_level;
}

export function defaultLayer(fx: Fixture): LayerId {
  return isRetired(fx) ? "career" : "overview";
}

export function num(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function f3(v: unknown): string {
  const n = num(v);
  return n == null ? "—" : n.toFixed(3).replace(/^0\./, ".");
}
