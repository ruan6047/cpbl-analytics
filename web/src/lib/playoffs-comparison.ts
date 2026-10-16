// 季後賽第 2 區「隊伍表現」三範圍比較的 view-model 與文案單點（#287 WP5）。
//
// 契約鏡射後端 `playoffs-comparison/v1`（src/cpbl/playoffs/team_comparison/reader.py），
// 端點 `GET /api/v1/playoffs/comparison?season=&series=`（讀取失敗 503；回應即本型別，無外層封套）。
// ⚠️ 型別住本檔、**不寫進 `playoffs-types.ts`**（#285 掛點契約 r3 §2、§7）。
//
// 規則（PLAN r3 §4、§8；需求方 D1／D2／F1 與跨卡頁尾裁定 #281 6194693029）：
// 1. 比較條＝共享尺度＋方向：同一指標同一 scope 一條軸，兩隊共用軸域；缺值格只寫「—」，不畫成 0。
// 2. 排名標籤只在全年 A；對戰／本系列只顯示原始值＋同年聯盟平均參考（D2）；樣本數值（n 場、n 打席…）留格內（F1）。
// 3. 連續紀錄同 scope、不跨賽別；全年 A 標「例行賽結束時」，不稱「進行中」。
// 4. T5 並列「例行賽背景 vs 本系列實際」，文案零「預測／預期／誤差」（測試逐字掃描文案表與頁尾說明）。
// 5. **說明性注意事項不在區內就地顯示**（#285 契約 r3 §2、§2.4、§2.5）：資料來源、樣本限制、方向圖例、
//    具體缺值原因一律由 `comparisonNotes(data)` 交 S04 頁尾；格內只留簡短狀態「—」「待更新」。
// 6. 使用者可見字串集中在 COMPARISON_COPY／T5_COPY／NOTE_COPY（掃描對象）。

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
  /** S02 系列 conflict_reason 原樣帶入（PLAN r4 §4.6）；統計照母體計算、不改判 S02。 */
  conflict_reason: string | null;
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
  heading: "隊伍表現",
  loadFailed: "第 2 區資料暫時無法讀取，其他區不受影響。",
  scopeTabsLabel: "比較範圍",
  scopeLabel: { season_a: "全年（例行賽）", head_to_head_a: "兩隊例行賽對戰", series: "本系列" } as Record<ComparisonScopeKey, string>,
  streakLabel: { season_a: "例行賽結束時", head_to_head_a: "對戰", series: "本系列" } as Record<ComparisonScopeKey, string>,
  /** 方向只留箭頭（格內）；「數值高／低較好」的說明句在頁尾圖例（NOTE_COPY.directionLegend）。 */
  higherBetter: "↑",
  lowerBetter: "↓",
  missingValue: "—",
  /** 格內／區內簡短狀態（跨卡頁尾裁定：缺值格保留「—」「待更新」；具體原因在頁尾）。 */
  status: {
    stale: "待更新",
    summary_missing: "待更新",
    pending_source: "待更新",
    participants_pending: "對戰組合待定",
    not_started: "本系列尚未開打",
  },
  streakHeading: "連續紀錄",
  styleHeading: "球風",
  metricsHeading: "攻守指標",
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

// T5：例行賽背景與本系列實際並列；⛔ 不稱預測誤差。「不是事前判斷」的說明句在頁尾（NOTE_COPY.t5）。
export const T5_COPY = {
  heading: "例行賽背景 vs 本系列實際",
  seasonColumn: "例行賽（全年）",
  seriesColumn: "本系列實際",
} as const;

// —— 數字格式 ——

export function formatMetric(def: ComparisonMetricDef, v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return COMPARISON_COPY.missingValue;
  const s = v.toFixed(def.decimals);
  return def.decimals === 3 ? s.replace(/^0\./, ".") : s;
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
  /** 左段寬度 %（25–75）；任一側缺值為 null＝不畫比例條（格內只見「—」）。 */
  leftPct: number | null;
  direction: string;
  leftSample: string;
  rightSample: string;
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
  if (lv == null || rv == null || !scale) return { ...base, leftPct: null };
  const span = scale.max - scale.min;
  const pos = (v: number) => (span > 0 ? (v - scale.min) / span : 0.5);
  const good = (v: number) => (def.higher_is_better ? pos(v) : 1 - pos(v));
  return { ...base, leftPct: 50 + 25 * (good(lv) - good(rv)) };
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
    return axes.filter((a) => (view.style?.[a.key]?.rank ?? 99) <= 2).map((a) => ({
      axis: a.key, label: a.label,
      text: COMPARISON_COPY.rankChip(a.label, view.style[a.key].rank as number),
      badge: SEMANTICS_BADGE[a.semantics],
    }));
  }
  return axes.map((a) => {
    const e = view.style?.[a.key];
    const text = a.components.map((c) =>
      COMPARISON_COPY.rawVsLeague(rawText(a.key, c, e?.raw[c]), rawText(a.key, c, e?.league_raw_mean[c]))).join("・");
    return { axis: a.key, label: a.label, text, badge: null };
  });
}

// —— 連續紀錄、狀態 ——

export function streakVM(scope: ComparisonScopeKey, view: ComparisonTeamView | undefined): string {
  return `${COMPARISON_COPY.streakLabel[scope]} ${streakLabel(view?.streak)}`;
}

/** 區內簡短狀態（無則 null）；具體原因在頁尾（comparisonNotes）。 */
export function scopeStatusNote(scope: SeasonScope | HeadToHeadScope | SeriesScope): string | null {
  return scope.status === "available" ? null : COMPARISON_COPY.status[scope.status];
}

/** scope 是否有可畫的隊伍資料（stale 仍可畫上一版）。 */
export function scopeHasTeams(scope: SeasonScope | HeadToHeadScope | SeriesScope): boolean {
  return Object.keys(scope.teams ?? {}).length > 0;
}

/** 初始範圍：本系列有已完成場次 ⇒ 本系列；否則全年。之後由使用者切換，資料更新不重置。 */
export function defaultScope(data: ComparisonPayload): ComparisonScopeKey {
  return scopeHasTeams(data.scopes.series) ? "series" : "season_a";
}

/** 端點路徑（registry `path` 用；回應即 ComparisonPayload）。 */
export const comparisonPath = (year: number, series: "E" | "C"): string =>
  `/api/v1/playoffs/comparison?season=${year}&series=${series}`;

/** registry 更新方式（M4）：本系列 box 晚到時 context_version 可能不變 ⇒ 每輪重取。 */
export const COMPARISON_REFRESH = "every_round" as const;

// —— 頁尾說明（#285 契約 r3 §2.4／§2.5：notes(data) 純函式、同步、不讀時鐘／window、不發請求）——

/** 結構與 S04 `PlayoffsNote` 相同（`web/src/lib/playoffs-notes.ts` 合併後改 import 該型別）。 */
export type ComparisonNote = { key: string; text: string; source?: { label: string; url: string } };

export const NOTE_COPY = {
  directionLegend: "比較條兩隊共用同一條尺度：範圍取同年例行賽六隊的最小到最大值，並擴大到涵蓋兩隊在該範圍的數值；↑ 表示數值高較好，↓ 表示數值低較好。",
  source: "全年與對戰數據由本站以官方逐場 box 加總後計算，只計例行賽已完成場次；本系列數據直接讀取季後賽逐場 box。",
  sample: "對戰與本系列場數少，比率容易隨單場起伏，請搭配格內樣本數（場數、打席、局數）閱讀。",
  t5: "「例行賽背景 vs 本系列實際」是兩個範圍的實際表現並列，不是對結果的事前判斷。",
  builtAt: (when: string, games: number) => `例行賽背景摘要建置於 ${when}（台北時間），涵蓋 ${games} 場已完成例行賽。`,
  stalePending: (when: string) => `例行賽背景的來源已有更正，重新建置完成前先顯示 ${when} 建置的版本，格內標「待更新」。`,
  staleGames: (when: string) => `例行賽賽果已更新，背景摘要將於下一次每日更新後重建；目前顯示 ${when} 建置的版本，格內標「待更新」。`,
  summaryMissing: "例行賽背景摘要尚未建置，全年與對戰範圍暫無數據，格內標「待更新」。",
  seriesPending: (missing: string, covered: number) =>
    `本系列${missing}的逐場 box 尚未送達，本系列攻守指標只計已到的 ${covered} 場；勝敗與連續紀錄不受影響。`,
  metricUnavailable: (reasons: string) => `格內「—」表示該指標目前無法計算：${reasons}。`,
  reason: { column_null: "部分逐場欄位缺值", zero_denominator: "樣本為 0", box_missing: "逐場 box 未送達", unknown: "資料不足" },
} as const;

/** ISO 時間（payload 欄位）→ 台北時間「YYYY-MM-DD HH:mm」；只用 payload 內的值，不讀時鐘。 */
export function taipeiStamp(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(d);
  const v = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${v("year")}-${v("month")}-${v("day")} ${v("hour")}:${v("minute")}`;
}

/** 「2026/C/3」→「第 3 場」，多場以「、」串起。 */
function gameNos(keys: string[]): string {
  return `第 ${keys.map((k) => k.split("/").pop()).join("、")} 場`;
}

function metricReasonText(data: ComparisonPayload): string | null {
  const found = new Set<string>();
  for (const scope of Object.values(data.scopes)) {
    for (const team of Object.values(scope.teams ?? {})) {
      for (const [k, reasons] of Object.entries(team.null_reasons ?? {})) {
        if (!k.startsWith("metric:") || team.metrics[k.slice(7) as ComparisonMetricKey] != null) continue;
        for (const r of reasons) {
          found.add(r.startsWith("column_null:") ? NOTE_COPY.reason.column_null
            : r.startsWith("box_missing:") ? NOTE_COPY.reason.box_missing
            : r === "zero_denominator" ? NOTE_COPY.reason.zero_denominator : NOTE_COPY.reason.unknown);
        }
      }
    }
  }
  return found.size ? [...found].join("、") : null;
}

/**
 * registry `notes(data)`：第 2 區交 S04 頁尾的說明（固定在前、依資料在後；key 依「同一件事」穩定）。
 * `notes(null)` 只回固定說明。純函式、同步、不讀時鐘、不讀 window、不發請求。
 */
export function comparisonNotes(data: ComparisonPayload | null): ComparisonNote[] {
  const notes: ComparisonNote[] = [
    { key: "teams.direction_legend", text: NOTE_COPY.directionLegend },
    { key: "teams.data_source", text: NOTE_COPY.source },
    { key: "teams.sample_limit", text: NOTE_COPY.sample },
    { key: "teams.t5_side_by_side", text: NOTE_COPY.t5 },
  ];
  if (!data) return notes;
  const season = data.scopes.season_a;
  const when = taipeiStamp(season.source?.built_at);
  if (season.status === "summary_missing") {
    notes.push({ key: "teams.summary_missing", text: NOTE_COPY.summaryMissing });
  } else if (season.status === "stale" && when) {
    notes.push({ key: "teams.summary_stale", text: season.source?.stale_reason === "pending_rebuild"
      ? NOTE_COPY.stalePending(when) : NOTE_COPY.staleGames(when) });
  }
  if (when && season.source) {
    notes.push({ key: "teams.summary_built_at", text: NOTE_COPY.builtAt(when, season.source.completed_games) });
  }
  const series = data.scopes.series;
  if (series.status === "pending_source" && series.missing_game_keys.length) {
    notes.push({ key: "teams.series_pending_source",
      text: NOTE_COPY.seriesPending(gameNos(series.missing_game_keys), series.covered_game_keys.length) });
  }
  const reasons = metricReasonText(data);
  if (reasons) notes.push({ key: "teams.metric_unavailable", text: NOTE_COPY.metricUnavailable(reasons) });
  return notes;
}
