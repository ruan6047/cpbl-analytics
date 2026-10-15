import type { Metadata } from "next";
import { PlayoffsLive } from "@/components/playoffs/playoffs-live";
import { taipeiDate } from "@/lib/taipei-date";
import { fetchPlayoffsOverview, parseGameParam, parseYearParam } from "@/lib/playoffs-types";

// `/playoffs` 季後專頁（#285 S04）。10/17 骨架＝第 1 區（系列賽表現）＋第 4 區 `#watch`（#289 WatchSection，
// client 端取）；第 2／3 區整區隱藏（需求方 Q3），
// 不留標題或「待更新」。首屏 SSR 只取 overview（no-store，⛔ 600 秒 revalidate），64 人資料不進首屏。
// 版面固定 1→4、錨點 #series／#watch（需求方 Q4），不做 T 狀態佈局。

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "季後賽",
  description: "中華職棒季後賽系列進度、逐場比分與官方單場 MVP。",
};

export default async function PlayoffsPage({ searchParams }: { searchParams: Promise<{ year?: string | string[]; game?: string | string[] }> }) {
  const sp = await searchParams;
  const year = parseYearParam(sp.year, Number(taipeiDate().slice(0, 4)));
  const overview = await fetchPlayoffsOverview(year);
  // ?game＝官方場號，只當第 4 區目標場（需求方 D2：10/17 不做系列／歷史場切換）。
  const game = parseGameParam(sp.game);
  return <PlayoffsLive key={year} initial={overview} year={year} game={game} />;
}
