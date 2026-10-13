/** #238：有界輸入送既有 journey；不更動 #237 的選場規則。 */
import { announcementFor } from "./postseason-announcement.ts";
import { buildPostseasonJourney } from "./postseason-journey.ts";
import { ApiError } from "./http-error.ts";
import type { Report, ReportAnchor, ReportKind, ReportRequest, ReportTab, ReportView } from "./report-types.ts";

export const REPORT_TABS: readonly { value: ReportTab; label: string }[] = [
  { value: "overview", label: "總覽" }, { value: "pitchers", label: "投手" }, { value: "fielders", label: "野手" },
];
export function reportLink(sno: number, kind: ReportKind, year: number, tab: ReportTab = "overview") {
  return `/games/${sno}/report?kind=${kind}&year=${year}&tab=${tab}`;
}
/** Y 觀戰報告網址固定 Y 身分；不以 X 回顧網址冒充。 */
export function previewLink(sno: number, kind: ReportKind, year: number, tab: ReportTab = "overview") {
  return `/games/${sno}/preview?kind=${kind}&year=${year}&tab=${tab}`;
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
export type ReportRead = (request?: ReportRequest) => Promise<Report>;
/** 第一讀只取 context 給既有 journey 選 Y；完整組裝只讀一次，並帶同 context_hash 由後端核對同源。 */
export async function loadReport(read: ReportRead): Promise<ReportView> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const base = await read({ contextOnly: true });
    const journey = reportJourney(base);
    // 查無／未完賽在第一讀與完整讀同樣提早回傳，不必再讀。
    if (base.status !== "ok") return { report: base, journey, updating: false };
    const next = journey?.next?.row, contextHash = base.journey_context?.context_hash;
    try {
      const report = await read(next && contextHash ? { kind: next.kind_code as ReportKind, sno: next.game_sno, contextHash }
        : contextHash ? { contextHash } : undefined);
      return { report, journey, updating: false };
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 409) throw error;
    }
  }
  // 兩次皆變更：第一讀沒有背景，另讀完整 X 回顧，不給 Y。
  const report = await read();
  return { report: { ...report, next_game: null }, journey: reportJourney(report), updating: true };
}
/** 既有 journey 與第二讀都指向同一正式 Y 才成立觀戰報告；否則不以 X 背景冒充 Y。 */
export function previewMatches(view: ReportView, kind: ReportKind, sno: number): boolean {
  const row = view.journey?.next?.row, next = view.report.next_game;
  return !view.updating && !!row && !!next && row.kind_code === kind && row.game_sno === sno
    && next.kind_code === kind && next.game_sno === sno;
}
/** 入口只在 Y 有既存正式列時給觀戰網址；公告場沒有正式場號回 null，不造 ID。 */
export function nextPreviewLink(row: { kind_code: string; game_sno: number; year?: unknown } | null | undefined): string | null {
  const year = Number(row?.year);
  if (!row || !["E", "C"].includes(row.kind_code) || !Number.isSafeInteger(row.game_sno) || row.game_sno <= 0
    || !Number.isInteger(year) || year < 1990 || year > 2100) return null;
  return previewLink(row.game_sno, row.kind_code as ReportKind, year);
}
/** X 的下一場：journey 正式 Y 與第二讀同指，且 Y 定位回同一 X 才成立；否則 null，入口不顯示。 */
export async function nextPreviewFor(view: ReportView, anchorOf: (sno: number, kind: ReportKind) => Promise<ReportAnchor>): Promise<string | null> {
  const row = view.journey?.next?.row, href = nextPreviewLink(row);
  if (!row || !href || !previewMatches(view, row.kind_code as ReportKind, row.game_sno)) return null;
  const found = await anchorOf(row.game_sno, row.kind_code as ReportKind);
  return found.status === "ok" && found.anchor?.kind_code === view.report.kind_code && found.anchor.game_sno === view.report.game_sno ? href : null;
}
