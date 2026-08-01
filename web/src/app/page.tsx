import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, ErrorState } from "@/components/ui";
import { api } from "@/lib/api";
import PlayerSearch from "@/components/player-search";
import DailyHub from "@/components/daily-hub";
import MiniStandings from "@/components/mini-standings";
import { BrandMark } from "@/components/brand-mark";

export const metadata = {
  title: { absolute: "Ruan's 中職數據實驗室｜中華職棒數據視覺化" },
  description: "從最近賽事到下一場對戰，用可追溯的數據看懂中職。",
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
  // 賽前降級提示**不**另外取：點機率與 serving 狀態必須同源，否則會出現「快取的舊機率
  // ＋ 即時的正常狀態」＝沒有提示的舊模型機率。dailySummary 已改 no-store 且兩者同在
  // 一份 response 內（ML-OUTCOME-SIMPLE-LEAK2）。
  const [dailyR, standR] = await Promise.allSettled([
    api.dailySummary(),
    api.officialStandings(0),
  ]);

  const standings = standR.status === "fulfilled" ? standR.value.items : [];
  return (
    <div className="space-y-8">
      <header className="relative overflow-hidden rounded-xl border border-line bg-surface-2 px-6 py-10 sm:px-12">
        {/* 浮水印用剪影：五官是為 16–32px 調的，放大到 288px 會讓眼睛變孤立大圓、
            微笑弧被容器裁掉，臉反而讀不出來。完整版留給 logo 與 favicon。 */}
        <BrandMark variant="silhouette" className="absolute -right-12 -top-12 h-72 w-72 text-ink/5" />
        {/* 目的優先：hero 只講「這個站讓你得到什麼」。視覺化與模型是手段，屬 /methodology
            與各頁揭露，不放首屏（需求方 2026-08-02 人工審定案：果與因不可倒置）。
            導覽已有賽程／戰績入口，故不重複 CTA。 */}
        <div className="relative z-10 max-w-2xl space-y-4 text-left max-lg:text-center">
          <p className="font-[family-name:var(--font-display)] text-sm font-bold tracking-wide text-accent">RUAN&apos;S CPBL LAB</p>
          <h1 className="text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">
            Ruan&apos;s 中職數據實驗室
          </h1>
          <p className="max-w-lg text-base text-muted max-lg:mx-auto sm:text-lg">
            用視覺化與數據分析，把棒球看得更懂。
          </p>
          <div className="pt-1 md:hidden">
            <PlayerSearch />
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
