import type { Metadata } from "next";
import { PlayoffsLive } from "@/components/playoffs/playoffs-live";
import { taipeiDate } from "@/lib/taipei-date";
import { fetchPlayoffsOverview, parseGameParam, parseSeriesParam, parseYearParam } from "@/lib/playoffs-types";

// `/playoffs` 季後專頁（#285 S04）。10/17 骨架＝第 1 區（系列賽表現）＋第 4 區 `#watch`（#289 WatchSection，
// client 端取）；第 2／3 區整區隱藏（需求方 Q3），
// 不留標題或「待更新」。首屏 SSR 只取 overview（no-store，⛔ 600 秒 revalidate），64 人資料不進首屏。
// 版面固定 1→4、錨點 #series／#watch（需求方 Q4），不做 T 狀態佈局。
// `?series=E|C`（#285 批次 B）：伺服器端選系列，未指定或不合法時跟隨 S02 預設系列；外殼 key＝year＋series，
// 換系列整個外殼重掛（舊輪詢中止、舊系列資料不殘留）。

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "季後賽",
  description: "中華職棒季後賽系列進度、逐場比分與官方單場 MVP。",
};

export default async function PlayoffsPage({ searchParams }: {
  searchParams: Promise<{ year?: string | string[]; series?: string | string[]; game?: string | string[] }>;
}) {
  const sp = await searchParams;
  const yearParam = parseYearParam(sp.year, 0) || null;
  const year = yearParam ?? Number(taipeiDate().slice(0, 4));
  const series = parseSeriesParam(sp.series);
  const overview = await fetchPlayoffsOverview(year, series);
  // ?game＝官方場號，只在所選系列內當第 4 區目標場（D2 只限預測類，6214203757）。
  const game = parseGameParam(sp.game);
  return <PlayoffsLive key={`${year}:${series ?? "default"}`} initial={overview} year={year} game={game}
    series={series} yearParam={yearParam} />;
}
