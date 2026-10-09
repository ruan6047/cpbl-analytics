import Link from "next/link";
import type { Metadata } from "next";
import { api } from "@/lib/api";
import { loadReport, reportTab } from "@/lib/between-games";
import { gameLink } from "@/lib/postseason-journey";
import type { ReportKind } from "@/lib/report-types";
import { Card } from "@/components/ui";
import ReportPage from "./report-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "場間報告｜CPBL Analytics", description: "季後賽完賽後的系列進度、兩隊投手使用與野手背景。", robots: { index: false, follow: true } };
export default async function Page({ params, searchParams }: {
  params: Promise<{ sno: string }>;
  searchParams: Promise<{ kind?: string; year?: string; tab?: string }>;
}) {
  const [{ sno }, query] = await Promise.all([params, searchParams]);
  const id = Number(sno), year = Number(query.year);
  if (!Number.isSafeInteger(id) || id <= 0 || !Number.isInteger(year) || year < 1990 || year > 2100 || !["E", "C"].includes(query.kind ?? "")) {
    return <Card><h1 className="text-xl font-bold">請指定季後賽年度與場號</h1><p className="mt-3 text-muted">從季後賽賽況頁的「場間報告」進入。</p><Link className="mt-4 inline-block text-accent underline" href="/games">返回賽事</Link></Card>;
  }
  const kind = query.kind as ReportKind;
  try {
    const view = await loadReport(target => api.report(id, kind, year, target));
    return <ReportPage view={view} tab={reportTab(query.tab)} />;
  } catch {
    return <Card><h1 className="text-xl font-bold">報告暫時無法讀取</h1><p className="mt-3 text-muted">重新載入，或先回原賽況查看已取得資料。</p><Link className="mt-4 inline-block text-accent underline" href={gameLink(kind, id, year)}>返回原賽況</Link></Card>;
  }
}
