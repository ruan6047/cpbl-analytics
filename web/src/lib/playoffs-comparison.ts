// 季後賽第 2 區「隊伍表現」三範圍比較的 view-model 與文案單點（#287 WP5）。
//
// 契約鏡射後端 `playoffs-comparison/v1`（src/cpbl/playoffs/team_comparison/reader.py），
// 端點 `GET /api/v1/playoffs/comparison?season=&series=`（讀取失敗 503；回應即本型別，無外層封套）。
// ⚠️ 型別住本檔、**不寫進 `playoffs-types.ts`**（#285 掛點契約 §2、§7）；第 2 區元件與 registry 登記屬第 2 次合併。
//
// 規則（PLAN r2 §4、§8；需求方 D1／D2 裁定）：
// 1. 比較條＝共享尺度＋方向：同一指標同一 scope 一條軸，兩隊共用軸域；缺值顯示「—＋原因」，不畫成 0。
// 2. 排名標籤只在全年 A；對戰／本系列只顯示原始值＋同年聯盟平均參考，並標樣本（D2）。
// 3. 連續紀錄同 scope、不跨賽別；全年 A 標「例行賽結束時」，不稱「進行中」。
// 4. T5 並列「例行賽背景 vs 本系列實際」，文案零「預測／預期／誤差」（測試逐字掃描本檔文案表）。
// 5. 使用者可見字串集中在 COMPARISON_COPY／T5_COPY（掃描對象）。

import { SEMANTICS_BADGE, TEAM_STYLE_COPY, outsToIp, type TeamStyleAxisKey, type TeamStyleSemantics } from "@/lib/team-style";
import { streakLabel, type StreakFact } from "@/lib/team-streak";

// —— 契約型別 ——

export type ComparisonMetricKey = "ops" | "rf_pg" | "ra_pg" | "era" | "whip" | "der";

export type ComparisonMetricDef = {
  key: ComparisonMetricKey;
  label: string;
  unit: string;
  higher_is_better: boolean;
  decimals: number;
};

export type ComparisonStyleEntry = {
  raw: Record<string, number | null>;
  league_raw_mean: Record<string, number | null>;
  /** 只在全年 A 出現（D2）。 */
  z?: number | null;
  rank?: number | null;
};

export type ComparisonTeamView = {
  counts: Record<string, number | null>;
  metrics: Record<ComparisonMetricKey, number | null>;
  null_reasons: Record<string, string[]>;
  sample: { games: number | null; pa: number | null; bf: number | null; outs: number | null };
  streak: StreakFact | null;
  style: Record<TeamStyleAxisKey, ComparisonStyleEntry>;
};

export type ComparisonScale = { min: number; max: number } | null;

export type SeasonScope = {
  status: "available" | "stale" | "summary_missing";
  label?: string;
  source: {
    build_id: string; builder_version: string; source_hash: string; built_at: string | null;
    promoted_at: string | null; pending_since: string | null; completed_games: number;
    stale_reason: "pending_rebuild" | "games_changed" | null;
  } | null;
  teams: Record<string, ComparisonTeamView>;
  scales: Partial<Record<ComparisonMetricKey, ComparisonScale>>;
  league: { n_teams: number; style_raw_mean: Record<string, number | null>;
            metrics_mean: Record<ComparisonMetricKey, number | null> } | null;
};

export type HeadToHeadScope = {
  status: "available" | "stale" | "summary_missing" | "participants_pending";
  games: number | null;
  teams: Record<string, ComparisonTeamView>;
  scales: Partial<Record<ComparisonMetricKey, ComparisonScale>>;
};

export type SeriesScope = {
  status: "not_started" | "available" | "pending_source" | "participants_pending";
  label: string;
  expected_game_keys: string[];
  covered_game_keys: string[];
  missing_game_keys: string[];
  teams: Record<string, ComparisonTeamView>;
  scales: Partial<Record<ComparisonMetricKey, ComparisonScale>>;
};

/** 區層級狀態（#285 掛點契約 §2）：ok＝三 scope 皆可用或本系列未開打；partial＝有 scope 缺席／待更新；
 *  unavailable＝沒有任何 scope 有隊伍資料。讀取失敗是 HTTP 503，不在此值域。 */
export type ComparisonStatus = "ok" | "partial" | "unavailable";

export type ComparisonPayload = {
  contract: "playoffs-comparison/v1";
  status: ComparisonStatus;
  series_id: { year: number; kind_code: "E" | "C"; rule_version: string | null; teams: (string | null)[] };
  participants_status: "known" | "pending_e_winner" | "unknown";
  context_version: string;
  as_of: string;
  metric_defs: ComparisonMetricDef[];
  style_axes: { key: TeamStyleAxisKey; label: string; semantics: TeamStyleSemantics; components: string[] }[];
  scopes: { season_a: SeasonScope; head_to_head_a: HeadToHeadScope; series: SeriesScope };
};

export type ComparisonScopeKey = keyof ComparisonPayload["scopes"];

// —— 文案表（掃描對象）——

export const COMPARISON_COPY = {
  scopeLabel: { season_a: "全年（例行賽）", head_to_head_a: "兩隊例行賽對戰", series: "本系列" } as Record<ComparisonScopeKey, string>,
  streakLabel: { season_a: "例行賽結束時", head_to_head_a: "對戰", series: "本系列" } as Record<ComparisonScopeKey, string>,
  higherBetter: "↑ 數值高較好",
  lowerBetter: "↓ 數值低較好",
  missingValue: "—",
  status: {
    stale: "待更新：來源已更正，背景摘要尚未重建",
    summary_missing: "背景摘要尚未建置",
    participants_pending: "對戰組合待定",
    not_started: "本系列尚未開打",
    pending_source: (n: number) => `尚有 ${n} 場 box 未送達，指標只計已到場次`,
  },
  reason: {
    box_missing: "缺 box",
    column_null: "欄位未知",
    zero_denominator: "樣本為 0",
    unknown: "資料不足",
  },
  leagueRef: "聯盟平均",
  topTraitsLabel: "聯盟前段特徵",
  rankChip: (label: string, rank: number) => `${label} · 第 ${rank}`,
  rawVsLeague: (raw: string, league: string) => `${raw}（聯盟平均 ${league}）`,
  sample: {
    games: (n: number) => `${n} 場`,
    pa: (n: number) => `${n} 打席`,
    bf: (n: number) => `${n} 打者`,
    ip: (outs: number) => `${outsToIp(outs)} 局`,
  },
} as const;

// T5（系列 decided）：例行賽背景與本系列實際並列；⛔ 不稱預測誤差。
export const T5_COPY = {
  heading: "例行賽背景 vs 本系列實際",
  seasonColumn: "例行賽（全年）",
  seriesColumn: "本系列實際",
  note: "兩欄是不同範圍的實際表現並列，不是對結果的事前判斷。",
} as const;

// —— 數字格式 ——

export function formatMetric(def: ComparisonMetricDef, v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return COMPARISON_COPY.missingValue;
  const s = v.toFixed(def.decimals);
  return def.decimals === 3 ? s.replace(/^0\./, ".") : s;
}

/** null 原因碼 → 一句話（`box_missing:<game_key>`／`column_null:<col>`／`zero_denominator`）。 */
export function reasonText(reasons: string[] | undefined): string {
  if (!reasons || reasons.length === 0) return COMPARISON_COPY.reason.unknown;
  const parts = new Set<string>();
  const boxes: string[] = [];
  for (const r of reasons) {
    if (r.startsWith("box_missing:")) boxes.push(r.slice("box_missing:".length));
    else if (r.startsWith("column_null:")) parts.add(COMPARISON_COPY.reason.column_null);
    else if (r === "zero_denominator") parts.add(COMPARISON_COPY.reason.zero_denominator);
    else parts.add(COMPARISON_COPY.reason.unknown);
  }
  if (boxes.length) parts.add(`${COMPARISON_COPY.reason.box_missing} ${boxes.join("、")}`);
  return [...parts].join("；");
}

const METRIC_SAMPLE: Record<ComparisonMetricKey, (s: ComparisonTeamView["sample"]) => string> = {
  ops: (s) => (s.pa == null ? COMPARISON_COPY.missingValue : COMPARISON_COPY.sample.pa(s.pa)),
  rf_pg: (s) => (s.games == null ? COMPARISON_COPY.missingValue : COMPARISON_COPY.sample.games(s.games)),
  ra_pg: (s) => (s.games == null ? COMPARISON_COPY.missingValue : COMPARISON_COPY.sample.games(s.games)),
  era: (s) => (s.outs == null ? COMPARISON_COPY.missingValue : COMPARISON_COPY.sample.ip(s.outs)),
  whip: (s) => (s.outs == null ? COMPARISON_COPY.missingValue : COMPARISON_COPY.sample.ip(s.outs)),
  der: (s) => (s.bf == null ? COMPARISON_COPY.missingValue : COMPARISON_COPY.sample.bf(s.bf)),
};

// —— 比較條（共享尺度＋方向）——

export type ComparisonBarVM = {
  metric: ComparisonMetricKey;
  label: string;
  leftText: string;
  rightText: string;
  /** 左段寬度 %（25–75）；任一側缺值為 null＝不畫比例條。 */
  leftPct: number | null;
  direction: string;
  leftSample: string;
  rightSample: string;
  missingNote: string | null;
};

/**
 * 共享尺度換算：兩隊值放上同一軸域 [min, max]，先換成「較好程度」n∈[0,1]
 * （低較好的指標反轉），左段寬度＝50 + 25·(n左 − n右) ∈ [25, 75]。
 * ⇒ 兩隊同值為 50/50；差距以「同年聯盟全距」為尺度，不因小樣本極端值被拉滿或裁切。
 */
export function comparisonBarVM(def: ComparisonMetricDef, left: ComparisonTeamView | undefined,
  right: ComparisonTeamView | undefined, scale: ComparisonScale | undefined): ComparisonBarVM {
  const lv = left?.metrics[def.key] ?? null;
  const rv = right?.metrics[def.key] ?? null;
  const fmt = (v: number | null) => (v == null ? COMPARISON_COPY.missingValue : `${formatMetric(def, v)}${def.unit}`);
  const base = {
    metric: def.key, label: def.label, leftText: fmt(lv), rightText: fmt(rv),
    direction: def.higher_is_better ? COMPARISON_COPY.higherBetter : COMPARISON_COPY.lowerBetter,
    leftSample: left ? METRIC_SAMPLE[def.key](left.sample) : COMPARISON_COPY.missingValue,
    rightSample: right ? METRIC_SAMPLE[def.key](right.sample) : COMPARISON_COPY.missingValue,
  };
  if (lv == null || rv == null || !scale) {
    const notes: string[] = [];
    if (lv == null) notes.push(reasonText(left?.null_reasons[`metric:${def.key}`]));
    if (rv == null) notes.push(reasonText(right?.null_reasons[`metric:${def.key}`]));
    return { ...base, leftPct: null, missingNote: notes.join("／") || COMPARISON_COPY.reason.unknown };
  }
  const span = scale.max - scale.min;
  const pos = (v: number) => (span > 0 ? (v - scale.min) / span : 0.5);
  const good = (v: number) => (def.higher_is_better ? pos(v) : 1 - pos(v));
  return { ...base, leftPct: 50 + 25 * (good(lv) - good(rv)), missingNote: null };
}

// —— 球風標籤（D2）——

export type StyleTag = { axis: TeamStyleAxisKey; label: string; text: string; badge: string | null };

const pct1 = (v: number) => `${(v * 100).toFixed(1)}%`;

function rawText(axis: TeamStyleAxisKey, comp: string, v: number | null | undefined): string {
  if (v == null) return COMPARISON_COPY.missingValue;
  if (axis === "discipline") return `${comp === "bb_rate" ? "BB%" : "K%"} ${pct1(v)}`;
  return TEAM_STYLE_COPY[axis].formatRaw?.(v) ?? String(v);
}

/**
 * 全年 A：沿球隊頁「聯盟前段特徵」——名次 ≤ 2 的軸給 chip（名次＋語意徽章）。
 * 對戰／本系列：⛔ 不出排名；每軸原始值＋同年聯盟平均參考（選球紀律分列 BB%／K%）。
 */
export function styleTagsVM(scope: ComparisonScopeKey, view: ComparisonTeamView,
  axes: ComparisonPayload["style_axes"]): StyleTag[] {
  if (scope === "season_a") {
    return axes.filter((a) => (view.style[a.key]?.rank ?? 99) <= 2).map((a) => ({
      axis: a.key, label: a.label,
      text: COMPARISON_COPY.rankChip(a.label, view.style[a.key].rank as number),
      badge: SEMANTICS_BADGE[a.semantics],
    }));
  }
  return axes.map((a) => {
    const e = view.style[a.key];
    const text = a.components.map((c) =>
      COMPARISON_COPY.rawVsLeague(rawText(a.key, c, e?.raw[c]), rawText(a.key, c, e?.league_raw_mean[c]))).join("・");
    return { axis: a.key, label: a.label, text, badge: null };
  });
}

// —— 連續紀錄、狀態 ——

export function streakVM(scope: ComparisonScopeKey, view: ComparisonTeamView | undefined): string {
  return `${COMPARISON_COPY.streakLabel[scope]} ${streakLabel(view?.streak)}`;
}

export function scopeStatusNote(scope: SeasonScope | HeadToHeadScope | SeriesScope): string | null {
  switch (scope.status) {
    case "available":
      return null;
    case "pending_source":
      return COMPARISON_COPY.status.pending_source((scope as SeriesScope).missing_game_keys.length);
    default:
      return COMPARISON_COPY.status[scope.status];
  }
}
