import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, ErrorState } from "@/components/ui";
import { api } from "@/lib/api";
import PlayerSearch from "@/components/player-search";
import DailyHub from "@/components/daily-hub";
import MiniStandings from "@/components/mini-standings";

export const metadata = {
  title: "CPBL 分析 | 中華職棒數據視覺化",
  description: "非官方中華職棒 [CPBL] 數據視覺化網站——最近比賽日戰果、下一批賽事與賽前勝率、資料新鮮度，以及球員、球隊與投打脈絡的非即時分析。",
};

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = await searchParams;
  if (sp.seg || sp.view || sp.kind || sp.year) {
    const qs = new URLSearchParams(
      Object.entries(sp).filter(([, v]) => v != null) as [string, string][],
    ).toString();
    redirect(`/standings${qs ? `?${qs}` : ""}`);
  }

  // 首頁每日入口：單一 daily summary 契約 + 戰績摘要（blueprint §8.4：12 請求 → ≤3）。
  // 兩者各自 settle：任一失敗都優雅降級，不讓首頁 500。
  const [dailyR, standR] = await Promise.allSettled([
    api.dailySummary(),
    api.officialStandings(0),
  ]);

  const standings = standR.status === "fulfilled" ? standR.value.items : [];

  return (
    <div className="space-y-8">
      {/* Hero：精簡標題 + 全站球員搜尋 + 導覽（移除舊 /predict CTA） */}
      <header className="relative overflow-hidden rounded-xl border border-line bg-surface-2 px-6 py-7 text-center sm:px-12">
        <div className="relative z-10 mx-auto max-w-2xl space-y-3">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
            非官方中華職棒 [CPBL] 數據視覺化
          </h1>
          <p className="mx-auto max-w-lg text-xs text-muted sm:text-sm">
            最近比賽日發生什麼、下一批賽事看什麼——用視覺化把中職數據講清楚
          </p>
          <div className="pt-1">
            <PlayerSearch />
          </div>
          <div className="flex flex-wrap justify-center gap-2 pt-1 text-xs sm:text-sm">
            <Link
              href="/standings"
              className="rounded-full bg-ink px-4 py-1.5 font-medium text-paper transition hover:opacity-90"
            >
              本季戰績
            </Link>
            <Link
              href="/games"
              className="rounded-full border border-line bg-surface px-4 py-1.5 font-medium text-ink transition hover:bg-surface-2"
            >
              賽況與 Box
            </Link>
          </div>
        </div>
      </header>

      {/* 每日入口 hub：最近比賽日 → freshness → 下一批賽事。API 失敗顯示可重試錯誤，
          不把錯誤當成「今天沒比賽」（GAME_RECAP §7.1）。 */}
      {dailyR.status === "fulfilled" ? (
        <DailyHub summary={dailyR.value} />
      ) : (
        <Card padding="p-6">
          <ErrorState>賽事資料暫時無法載入，請稍後重新整理</ErrorState>
        </Card>
      )}

      {/* 第二層：戰績摘要（目前領先者）＋季節性橫幅 slot。 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {standings.length > 0 && <MiniStandings standings={standings} />}
        {/* 季節性橫幅 slot（DATA-EDITORIAL1）：只放可追溯事實，例行賽期間留空，
            季後賽啟用專頁模板。目前無內容故不渲染。 */}
      </div>
    </div>
  );
}
