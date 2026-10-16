import type { Metadata } from "next";
import { PlayoffsLive } from "@/components/playoffs/playoffs-live";
import { taipeiDate } from "@/lib/taipei-date";
import { fetchPlayoffsOverview } from "@/lib/playoffs-types";

import { parsePlayoffsSelection, type PlayoffsQuery } from "@/lib/playoffs-selection";
import { ErrorState } from "@/components/ui";

// 首屏只取 overview；第 4 區保留網址指定的場號／版本，其他區仍是該年系列現在資料。
// 非法選擇明示錯誤，未指定才用預設；年／系列切換重掛以中止舊輪詢。

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "季後賽",
  description: "中華職棒季後賽系列進度、逐場比分與官方單場 MVP。",
};

export default async function PlayoffsPage({ searchParams }: {
  searchParams: Promise<PlayoffsQuery>;
}) {
  const sp = await searchParams;
  const selection = parsePlayoffsSelection(sp);
  if (!selection.valid) return <div id="watch"><h1 className="text-2xl font-bold">季後賽</h1><ErrorState>網址參數無效</ErrorState></div>;
  const { year: yearParam, series, game, revision } = selection;
  const year = yearParam ?? Number(taipeiDate().slice(0, 4));
  const overview = await fetchPlayoffsOverview(year, series);
  return <PlayoffsLive key={`${year}:${series ?? "default"}`} initial={overview} year={year} game={game}
    series={series} yearParam={yearParam} revision={revision} />;
}
