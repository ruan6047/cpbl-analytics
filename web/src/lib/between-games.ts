/** #238：有界輸入送既有 journey；不更動 #237 的選場規則。 */
import { announcementFor } from "./postseason-announcement.ts";
import { buildPostseasonJourney } from "./postseason-journey.ts";
import { ApiError } from "./http-error.ts";
import type { Report, ReportKind, ReportTab, ReportView } from "./report-types.ts";

export const REPORT_TABS: readonly { value: ReportTab; label: string }[] = [
  { value: "overview", label: "總覽" }, { value: "pitchers", label: "投手" }, { value: "fielders", label: "野手" },
];
export function reportLink(sno: number, kind: ReportKind, year: number, tab: ReportTab = "overview") {
  return `/games/${sno}/report?kind=${kind}&year=${year}&tab=${tab}`;
}
export function reportTab(raw: string | undefined): ReportTab {
  return REPORT_TABS.some(t => t.value === raw) ? raw as ReportTab : "overview";
}
export function recapReportLink(completed: boolean, sno: string | number, kind: string, year: unknown): string | null {
  const id = Number(sno), season = Number(year);
  if (!completed || !["E", "C"].includes(kind) || !Number.isSafeInteger(id) || id <= 0
    || !Number.isInteger(season) || season < 1990 || season > 2100) return null;
  return reportLink(id, kind as ReportKind, season);
}
export function reportJourney(report: Report) {
  const context = report.journey_context;
  const announcement = announcementFor(report.season);
  if (report.status !== "ok" || !context || !announcement || !context.order_consistent) return null;
  const input = { announcement, summary: context.summary,
    rows: context.rows.map(r => ({ ...r, away_score: 0, home_score: 0, completed: false })),
    nowMs: Date.parse(`${context.cutoff_date}T23:59:59+08:00`), dataAsOf: context.cutoff_date };
  const first = buildPostseasonJourney(input);
  // 既有 journey 只會把沒有 DB 列的條件場標不需進行；已決定輪次的未完成列先移除。
  const finished = new Set(context.summary.flatMap(s => (s.games ?? []).map(g => `${s.kind_code}/${g.game_sno}`)));
  const rows = input.rows.filter(r => !first.series[r.kind_code as ReportKind]?.tally.decided || finished.has(`${r.kind_code}/${r.game_sno}`));
  const bounded = buildPostseasonJourney({ ...input, rows });
  return bounded.series.C.tally.decided ? { ...bounded, next: null, remaining: false } : bounded;
}
export type ReportRead = (target?: { kind: ReportKind; sno: number; contextHash: string }) => Promise<Report>;
export async function loadReport(read: ReportRead): Promise<ReportView> {
  let base: Report | null = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    base = await read();
    const journey = reportJourney(base);
    const next = journey?.next?.row;
    if (!next) return { report: base, journey, updating: false };
    try {
      const enriched = await read({ kind: next.kind_code as ReportKind, sno: next.game_sno, contextHash: base.journey_context!.context_hash });
      return { report: enriched, journey, updating: false };
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 409) throw error;
    }
  }
  return { report: { ...base!, next_game: null }, journey: reportJourney(base!), updating: true };
}
