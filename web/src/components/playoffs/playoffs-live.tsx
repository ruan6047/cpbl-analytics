"use client";

import { useEffect, useRef, useState } from "react";
import { SectionTitle } from "@/components/postmark";
import { ErrorState, Notice } from "@/components/ui";
import { CLIENT_API } from "@/lib/client";
import { PlayoffsPoller, fetchJson, type WatchState } from "@/lib/playoffs-poll";
import { SERIES_COPY, asOfText } from "@/lib/playoffs-series-view";
import { overviewPath, watchPath, type PlayoffsOverview, type PlayoffsSeriesCode } from "@/lib/playoffs-types";
import type { PlayoffsWatch } from "@/lib/playoffs-watch";
import { SeriesSection } from "./series-section";
import { WatchArea } from "./watch-area";

// `/playoffs` 的 client 外殼（#285 S04）：持有 overview 與第 4 區狀態並跑共用輪詢控制器（playoffs-poll.ts）。
// 首屏 SSR 只給 overview（HTML 已含第 1 區）；掛載後立即一輪「overview → watch」由 client 取第 4 區
// （首屏不帶 4A 投手資料），之後每 30 秒一輪。watch 一律 client 端自取 `CLIENT_API`：
// ⛔ 用 #289 的 `fetchPlayoffsWatch`（讀 server 端 API_URL，瀏覽器內會退回 localhost:4001）。
// 輪詢只換資料：區塊位置與 key 固定，⛔ 捲動、⛔ 移焦點、⛔ remount。

export function PlayoffsLive({ initial, year, game }: { initial: PlayoffsOverview | null; year: number; game: number | null }) {
  const [overview, setOverview] = useState<PlayoffsOverview | null>(initial);
  const [watch, setWatch] = useState<WatchState<PlayoffsWatch>>({ kind: "idle" });
  const [pollFailed, setPollFailed] = useState(false);
  const pollerRef = useRef<PlayoffsPoller<PlayoffsOverview, PlayoffsWatch> | null>(null);

  useEffect(() => {
    const poller = new PlayoffsPoller<PlayoffsOverview, PlayoffsWatch>({
      fetchOverview: (signal) => fetchJson<PlayoffsOverview>(`${CLIENT_API}${overviewPath(year)}`, signal),
      fetchWatch: (t, signal) =>
        fetchJson<PlayoffsWatch>(`${CLIENT_API}${watchPath(year, t.series as PlayoffsSeriesCode, t.game)}`, signal),
      isVisible: () => document.visibilityState === "visible",
      setTimer: (fn, ms) => window.setTimeout(fn, ms),
      clearTimer: (h) => window.clearTimeout(h as number),
      onOverview: (o) => setOverview(o),
      onWatch: (s) => setWatch(s),
      onRound: (r) => setPollFailed(!r.overviewOk),
    }, game);
    pollerRef.current = poller;
    const onVisibility = () => poller.visibilityChanged();
    document.addEventListener("visibilitychange", onVisibility);
    poller.start(true);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      poller.stop();
      pollerRef.current = null;
    };
    // game 變更走 setGame（下方 effect），不重建控制器；year 變更由頁面以 key 重新掛載。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  useEffect(() => {
    pollerRef.current?.setGame(game);
  }, [game]);

  return (
    <div className="min-w-0 space-y-6">
      <SectionTitle as="h1" date={year} meta={overview ? <span data-as-of>{asOfText(overview)}</span> : undefined}>
        季後賽
      </SectionTitle>
      {pollFailed && overview && <Notice label="暫時無法更新">{SERIES_COPY.pollFailed}</Notice>}
      {overview ? <SeriesSection overview={overview} /> : <ErrorState>{SERIES_COPY.overviewFailed}</ErrorState>}
      <WatchArea state={watch} overview={overview} requested={game !== null} />
    </div>
  );
}

export default PlayoffsLive;
