// 本季走勢卡（SeasonTrendCard）的純資料判斷：何時改列逐場紀錄、逐場紀錄要顯示什麼。無 JSX。
//
// 為什麼不用「出賽 N 場以下」：滾動比率（OPS+／ERA+…）由後端在近 15 場累計樣本不足時回 null，
// 正式站量測 0 點者最多 51 場、有走勢者最少 15 場，場數區間重疊（#318 規劃 §1.3）。
// 因此只看「當下所選指標」實際有幾個可畫的點；投手 ERA+ 與 ERA 的點數可能不同，
// ⛔ 不得改成以球員為單位的「小樣本」旗標。
import type { StatRow } from "@/lib/client";
import { BAT_METRICS, type Metric, PIT_METRICS, type Role } from "./lib.ts";

/** 折線至少要 2 點才連得成線；少於此值（0 點空圖、1 點孤點）改列逐場紀錄（#318 需求方裁定）。 */
export const MIN_TREND_POINTS = 2;

/** 所選指標在本季逐場資料中可畫的（非 null）點數。 */
export function trendPointCount(rows: StatRow[], metric: Metric): number {
  let n = 0;
  for (const r of rows) if (metric.get(r) != null) n++;
  return n;
}

/**
 * 是否以逐場紀錄取代折線。只有滾動型指標會切換：計數型柱狀不受滾動門檻影響。
 * 無任何出賽列時維持原本的空態（由呼叫端處理），不進逐場紀錄。
 */
export function showGameLog(rows: StatRow[], metric: Metric): boolean {
  return Boolean(metric.roll) && rows.length > 0 && trendPointCount(rows, metric) < MIN_TREND_POINTS;
}

/** 逐場紀錄欄位＝該 role 的計數型指標（與下拉中的計數型選項同一來源，避免各自維護）。 */
export function gameLogMetrics(role: Role): Metric[] {
  return (role === "batting" ? BAT_METRICS : PIT_METRICS).filter((m) => !m.roll);
}

export type GameLogSummary = {
  games: number;
  /** 首場與末場的顯示日期（API `name`，如 "4/11"）。 */
  first: string;
  last: string;
  totals: { key: string; label: string; value: number | null }[];
};

/** 本季累計摘要：出賽數、日期範圍、各計數型指標加總（全場皆缺值時為 null，不補 0）。 */
export function gameLogSummary(rows: StatRow[], role: Role): GameLogSummary {
  const totals = gameLogMetrics(role).map((m) => {
    let sum: number | null = null;
    for (const r of rows) {
      const v = m.get(r);
      if (v != null) sum = (sum ?? 0) + v;
    }
    return { key: m.key, label: m.label, value: sum };
  });
  return {
    games: rows.length,
    first: rows.length ? String(rows[0].name) : "",
    last: rows.length ? String(rows[rows.length - 1].name) : "",
    totals,
  };
}

/** 逐場小表的列：新到舊（最近一場在最上面）。 */
export function gameLogRows(rows: StatRow[]): StatRow[] {
  return [...rows].reverse();
}
