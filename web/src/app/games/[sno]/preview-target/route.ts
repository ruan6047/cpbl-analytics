import { NextResponse } from "next/server";
import { api } from "@/lib/api";
import { loadReport, nextPreviewFor } from "@/lib/between-games";
import type { ReportKind } from "@/lib/report-types";

export const dynamic = "force-dynamic";
/** 賽況頁「下一場觀戰報告」唯讀接線：只回可靠 Y 的觀戰網址；無 target 回 null，不猜場號。 */
export async function GET(request: Request, { params }: { params: Promise<{ sno: string }> }) {
  const { sno } = await params;
  const query = new URL(request.url).searchParams;
  const id = Number(sno), year = Number(query.get("year")), kind = query.get("kind") ?? "";
  if (!Number.isSafeInteger(id) || id <= 0 || !Number.isInteger(year) || year < 1990 || year > 2100 || !["E", "C"].includes(kind)) {
    return NextResponse.json({ href: null });
  }
  try {
    const view = await loadReport(target => api.report(id, kind as ReportKind, year, target));
    return NextResponse.json({ href: await nextPreviewFor(view, (y, k) => api.reportAnchor(y, k, year)) });
  } catch {
    return NextResponse.json({ href: null });
  }
}
