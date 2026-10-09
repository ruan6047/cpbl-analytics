import { redirect } from "next/navigation";
import { Card, ErrorState } from "@/components/ui";
import { api } from "@/lib/api";
import DailyHub from "@/components/daily-hub";
import MiniStandings from "@/components/mini-standings";
import { PostseasonNextCard, postseasonPointer } from "@/components/postseason-next";
import { announcementFor } from "@/lib/postseason-announcement";
import { liveEntryProbes, liveEntryResults, postseasonJourneyFor, withLiveEntries } from "@/lib/postseason-journey";

export const metadata = {
  title: { absolute: "Ruan's 中職數據實驗室｜中華職棒數據視覺化" },
  // 沿用原 hero 副標的框架（手段→目的→範圍；#220 起 hero 併入今日賽事標題），並補回 h1 沒有的「中華職棒」與 CPBL
  // 關鍵字（父卡〈SEO 風險〉要求 title 與 description 兩處補償，當時只做了 title）。
  // og:description 由本欄衍生，不另設 openGraph.description——不製造第二個真相來源。
  // 長度刻意控制在行動版 SERP 的截斷點（約 40–50 中文字）內：免責已在 footer，
  // 不佔用這裡的字數（原版尾端的「非官方獨立專案」在行動版多半看不到，故移除）。
  description: "用視覺化與數據分析，把中華職棒 [CPBL] 的比賽、球員與歷史看得更懂——賽況復盤、進階數據與賽前勝率。",
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

  // 首頁每日入口：單一 daily summary 契約 + 本季 calendar（右欄前一比賽日與 MVP）+ 戰績摘要。
  // 三者各自 settle：任一失敗都優雅降級，不讓首頁 500。calendar 失敗時右欄退回 summary 能給的。
  // 賽前降級提示**不**另外取：點機率與 serving 狀態必須同源，否則會出現「快取的舊機率
  // ＋ 即時的正常狀態」＝沒有提示的舊模型機率。dailySummary 已改 no-store 且兩者同在
  // 一份 response 內（ML-OUTCOME-SIMPLE-LEAK2）。
  // 季後摘要（#237）同樣各自 settle：失敗時季後卡退回只用 calendar，不影響首頁其他區塊。
  // 當季（與賽程、戰績頁同一判準：seasons 第一筆）已有季後公告時，calendar 與季後摘要不走跨請求快取，
  // 避免季後卡組到不同時間的快照（api.ts journeyGet）。seasons 取不到就照舊快取，不擋首頁。
  const { years } = await api.seasons("A").catch(() => ({ years: [] as number[] }));
  const live = { live: years.length > 0 && announcementFor(years[0]) !== null };
  const [dailyR, standR, calR, postR] = await Promise.allSettled([
    api.dailySummary(),
    api.officialStandings(0),
    api.gamesCalendar(undefined, "A", live),
    api.postseasonSummary(undefined, "A", live),
  ]);

  const standings = standR.status === "fulfilled" ? standR.value.items : [];
  const calendar = calR.status === "fulfilled" ? calR.value.items : null;
  const post = postR.status === "fulfilled" ? postR.value : null;
  // 季後旅程：與季後總覽、日曆同一個模型。年度取 calendar 的 season（失敗時取 summary 的）。
  const season = calR.status === "fulfilled" ? calR.value.season : post?.season ?? null;
  const baseJourney = season != null
    ? postseasonJourneyFor(season, post && post.season === season ? post.series : null, calendar, Date.now())
    : null;
  // 單場賽況入口（#237）：資料庫還沒有 E 列時，依公告官方場號查既有單場狀態（最多 4 支、no-store、
  // 有逾時），身分全部相符才給連結；任何失敗都等於沒有入口。只補連結，不改進度與截至。
  const probes = baseJourney && live.live ? liveEntryProbes(baseJourney) : [];
  const probeR = await Promise.allSettled(probes.map((p) => api.liveEntryStatus(p.sno, p.kind, baseJourney!.year)));
  const journey = baseJourney && withLiveEntries(baseJourney, liveEntryResults(probes, probeR));
  // #218 首頁：頂部品牌大區併入「今日賽事」標題（品牌已在頂欄字標；全站搜尋在頂欄／行動選單），
  // 主位直接給 7:3 賽事；戰績摘要在下方左欄（7）。
  return (
    <div className="space-y-10">
      {/* 每日入口 hub：左＝今日（或下一批）票券、右＝前一比賽日賽果。API 失敗顯示可重試錯誤，
          不把錯誤當成「今天沒比賽」（GAME_RECAP §7.1）。hub 是 client island：票券要隨 phase
          自行翻態，而它的前景輪詢打的就是這裡 SSR 用的同一支 dailySummary。 */}
      {dailyR.status === "fulfilled" ? (
        <DailyHub summary={dailyR.value} calendar={calendar} postseason={postseasonPointer(journey)} />
      ) : (
        <Card padding="p-6">
          <h1 className="sr-only">今日賽事</h1>
          <ErrorState>賽事資料暫時無法載入，請稍後重新整理</ErrorState>
        </Card>
      )}

      {/* 第二層：戰績摘要（7 欄寬）＋季節性橫幅 slot（3 欄，DATA-EDITORIAL1：只放可追溯事實）。
          季後期間放季後下一場卡（#237，官方公告＋正式場次）；手機排在戰績摘要之前。 */}
      <div className="grid grid-cols-1 gap-7 min-[860px]:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
        {standings.length > 0 && <MiniStandings standings={standings} />}
        {journey && (
          <div className="order-first min-[860px]:order-none">
            <PostseasonNextCard journey={journey} />
          </div>
        )}
      </div>
    </div>
  );
}
