import { redirect } from "next/navigation";
import { Card, SourceUnavailable } from "@/components/ui";
import { SectionTitle } from "@/components/postmark";
import { api } from "@/lib/api";
import { settle } from "@/lib/fetch-result";
import { ApiError } from "@/lib/http-error";
import DailyHub from "@/components/daily-hub";
import MiniStandings from "@/components/mini-standings";
import { PostseasonNextCard, postseasonGameLabels, postseasonPointer, postseasonPreviewLinks, postseasonResultLabels } from "@/components/postseason-next";
import { announcementFor } from "@/lib/postseason-announcement";
import { withGameTeamNames } from "@/lib/teams";
import { liveEntryProbes, liveEntryResults, postseasonJourneyFromContext, withLiveEntries } from "@/lib/postseason-journey";

export const metadata = {
  title: { absolute: "Ruan's 中職數據實驗室｜中華職棒數據視覺化" },
  // 沿用原 hero 副標的框架（手段→目的→範圍；#220 起 hero 併入今日賽事標題），並補回 h1 沒有的「中華職棒」與 CPBL
  // 關鍵字（父卡〈SEO 風險〉要求 title 與 description 兩處補償，當時只做了 title）。
  // og:description 由本欄衍生，不另設 openGraph.description——不製造第二個真相來源。
  // 長度刻意控制在行動版 SERP 的截斷點（約 40–50 中文字）內：免責已在 footer，
  // 不佔用這裡的字數（原版尾端的「非官方獨立專案」在行動版多半看不到，故移除）。
  description: "用視覺化與數據分析，把中華職棒 [CPBL] 的比賽、球員與歷史看得更懂——賽況復盤、進階數據與賽前勝率。",
};

// #441：頁面明示動態渲染（HTML 與降級結果不被保存）；API 成功資料依原 TTL 共享、失敗不共享（api-cache.ts）。
export const dynamic = "force-dynamic";

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
  // #441：各來源 settle 後依區塊標示「暫時無法取得」，不再靜默消失或混成「沒有資料」。
  const seasonsR = await settle(api.seasons("A"));
  const years = seasonsR.ok ? seasonsR.data.years : [];
  // 年度清單取不到時無從判斷當季是否已公告季後：保守走即時讀取，避免恢復 TTL 後季後卡組到不同時間的快照（#441 規劃 v2 §4.2）。
  const live = { live: seasonsR.ok ? years.length > 0 && announcementFor(years[0]) !== null : true };
  const [dailyR, standR, calR, postR] = await Promise.all([
    settle(api.dailySummary()),
    settle(api.officialStandings(0)),
    settle(api.gamesCalendar(undefined, "A", live)),
    settle(api.postseasonSummary(undefined, "A", live)),
  ]);

  const standings = standR.ok ? standR.data.items : [];
  // #268：官方空白隊名（台灣大賽 C 列）以現役隊碼補齊顯示名；與日曆同一個 helper。
  const calendar = calR.ok ? calR.data.items.map(withGameTeamNames) : null;
  const post = postR.ok ? postR.data : null;
  // 季後旅程：與季後總覽、日曆同一個模型，系列事實只讀 API 的 series_context（#283）。
  // 年度取 calendar 的 season（失敗時取 summary 的）。
  const season = calR.ok ? calR.data.season : post?.season ?? null;
  const baseJourney = season != null && post && post.season === season
    ? postseasonJourneyFromContext(post.series_context, calendar)
    : null;
  // 單場賽況入口（#237）：資料庫還沒有 E 列時，依公告官方場號查既有單場狀態（最多 4 支、no-store、
  // 有逾時），身分全部相符才給連結；任何失敗都等於沒有入口。只補連結，不改進度與截至。
  // 年度清單取不到時，改以 calendar 回應的 season（省略 season＝當季）判斷是否已公告季後，入口核實照做（#441）。
  const announced = live.live || (!seasonsR.ok && season != null && announcementFor(season) !== null);
  const probes = baseJourney && announced ? liveEntryProbes(baseJourney) : [];
  // 查核失敗（非 404）仍不給連結，但要說「無法核實」而不是讓它看起來像沒有入口（#441）。
  const probeR = await Promise.allSettled(probes.map((p) => api.liveEntryCheck(p.sno, p.kind, baseJourney!.year)));
  const journey = baseJourney && withLiveEntries(baseJourney, liveEntryResults(probes, probeR));
  const entryUnverified = probeR.some((r) => r.status === "rejected" && !(r.reason instanceof ApiError && r.reason.failure === "not_found"));
  // 季後區塊只在已知適用（當季已公告季後）時才因來源失敗補上提示；年度清單也取不到時無從判斷，不憑空新增。
  const postseasonUnavailable = !postR.ok && announced;
  // #218 首頁：頂部品牌大區併入「今日賽事」標題（品牌已在頂欄字標；全站搜尋在頂欄／行動選單），
  // 主位直接給 7:3 賽事；戰績摘要在下方左欄（7）。
  return (
    <div className="space-y-10">
      {/* 每日入口 hub：左＝今日（或下一批）票券、右＝前一比賽日賽果。API 失敗顯示可重試錯誤，
          不把錯誤當成「今天沒比賽」（GAME_RECAP §7.1）。hub 是 client island：票券要隨 phase
          自行翻態，而它的前景輪詢打的就是這裡 SSR 用的同一支 dailySummary。 */}
      {dailyR.ok ? (
        <div>
          <DailyHub summary={dailyR.data} calendar={calendar} postseason={postseasonPointer(journey)}
            seriesLabels={postseasonGameLabels(journey)} reportLinks={postseasonPreviewLinks(journey)}
            resultLabels={postseasonResultLabels(journey)} />
          {/* calendar 只補右欄（前一比賽日 MVP 等）；取不到時 hub 退回 summary 能給的，這裡就近說明。 */}
          {!calR.ok && <SourceUnavailable label="賽程日曆補充（MVP 等）" className="mt-2 py-2" />}
        </div>
      ) : (
        <Card padding="p-6">
          <h1 className="sr-only">今日賽事</h1>
          <SourceUnavailable label="今日賽事" className="py-8" />
        </Card>
      )}

      {/* 第二層：戰績摘要（7 欄寬）＋季節性橫幅 slot（3 欄，DATA-EDITORIAL1：只放可追溯事實）。
          季後期間放季後下一場卡（#237，官方公告＋正式場次）；手機排在戰績摘要之前。 */}
      <div className="grid grid-cols-1 gap-7 min-[860px]:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
        {standings.length > 0 && <MiniStandings standings={standings} />}
        {!standR.ok && (
          <section aria-labelledby="home-standings-h">
            <SectionTitle as="h2" size="sm" id="home-standings-h" cue="全年・一軍">戰績</SectionTitle>
            <SourceUnavailable label="戰績摘要" />
          </section>
        )}
        {journey && (
          <div className="order-first min-[860px]:order-none">
            <PostseasonNextCard journey={journey} />
            {entryUnverified && <SourceUnavailable label="單場入口" className="py-2" />}
          </div>
        )}
        {postseasonUnavailable && !journey && (
          <section aria-labelledby="ps-next-h" className="order-first min-[860px]:order-none">
            <h2 id="ps-next-h" className="mb-1 text-base font-bold text-ink">季後賽</h2>
            <SourceUnavailable label="季後賽" />
          </section>
        )}
      </div>
    </div>
  );
}
