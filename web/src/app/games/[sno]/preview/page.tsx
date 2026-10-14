import Link from "next/link";
import type { Metadata } from "next";
import { api } from "@/lib/api";
import { loadReport, previewMatches, reportLink, reportTab } from "@/lib/between-games";
import type { ReportKind } from "@/lib/report-types";
import { projectReportView } from "@/lib/report-view-model";
import { Card } from "@/components/ui";
import ReportPage from "../report/report-page";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "觀戰報告｜CPBL Analytics", description: "季後賽未完賽下一場的開賽前背景與兩隊比較。", robots: { index: false, follow: true } };
export default async function Page({ params, searchParams }: {
  params: Promise<{ sno: string }>;
  searchParams: Promise<{ kind?: string; year?: string; tab?: string }>;
}) {
  const [{ sno }, query] = await Promise.all([params, searchParams]);
  const id = Number(sno), year = Number(query.year);
  if (!Number.isSafeInteger(id) || id <= 0 || !Number.isInteger(year) || year < 1990 || year > 2100 || !["E", "C"].includes(query.kind ?? "")) {
    return <Card><h1 className="text-xl font-bold">請指定季後賽年度與場號</h1><p className="mt-3 text-muted">從場間報告的「觀戰報告」連結進入。</p><Link className="mt-4 inline-block text-accent underline" href="/games">返回賽事</Link></Card>;
  }
  const kind = query.kind as ReportKind;
  try {
    // 只取截至場 X；Y 是否為下一場仍由既有 journey 與帶 context_hash 的第二讀共同核對。
    const found = await api.reportAnchor(id, kind, year);
    if (found.status === "final") return <Card><h1 className="text-xl font-bold">此場已完賽</h1><p className="mt-3 text-muted">觀戰報告只提供未完賽場；完賽後的背景見本場場間報告。</p><Link className="mt-4 inline-block min-h-11 text-accent underline" href={reportLink(id, kind, year)}>本場場間報告</Link></Card>;
    const anchor = found.anchor;
    if (found.status !== "ok" || !anchor) return <Card><h1 className="text-xl font-bold">{found.status === "no_anchor" ? "尚無已完賽季後場可作背景" : "本站尚未取得此場正式場次"}</h1><p className="mt-3 text-muted">不以公告場次猜正式場號或對戰隊伍。</p><Link className="mt-4 inline-block min-h-11 text-accent underline" href="/games">返回賽事</Link></Card>;
    const view = await loadReport(target => api.report(anchor.game_sno, anchor.kind_code, year, target));
    if (!previewMatches(view, kind, id)) return <Card><h1 className="text-xl font-bold">{view.updating ? "資料更新中" : "此場目前不是可核實的下一場"}</h1><p className="mt-3 text-muted">{view.updating ? "背景稍後重新載入。" : "依截至最新完賽場的季後進度，下一場不是此場；不以其他場背景冒充。"}</p><Link className="mt-4 inline-block min-h-11 text-accent underline" href={reportLink(anchor.game_sno, anchor.kind_code, year)}>截至最新完賽場的場間報告</Link></Card>;
    const tab = reportTab(query.tab);
    // #272：client 元件只收該頁籤畫面讀得到的選手與欄位；Y 判定（previewMatches）已用完整 view 做完。
    return <ReportPage view={projectReportView(view, tab)} tab={tab} preview={{ kind, sno: id }} />;
  } catch {
    return <Card><h1 className="text-xl font-bold">報告暫時無法讀取</h1><p className="mt-3 text-muted">重新載入，或先回賽事查看已取得資料。</p><Link className="mt-4 inline-block text-accent underline" href="/games">返回賽事</Link></Card>;
  }
}
