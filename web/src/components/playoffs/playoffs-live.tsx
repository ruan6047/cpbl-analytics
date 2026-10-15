"use client";

import { useEffect, useState } from "react";
import { SectionTitle } from "@/components/postmark";
import { ErrorState, Notice } from "@/components/ui";
import { CLIENT_API } from "@/lib/client";
import { PlayoffsPoller, fetchJson } from "@/lib/playoffs-poll";
import { SERIES_COPY, asOfText } from "@/lib/playoffs-series-view";
import { overviewPath, type PlayoffsOverview } from "@/lib/playoffs-types";
import { SeriesSection } from "./series-section";

// `/playoffs` 的 client 外殼（#285 S04）：持有 overview 狀態並跑共用輪詢控制器（playoffs-poll.ts）。
// 首屏由 SSR 給 overview（HTML 已含第 1 區），30 秒後才第一輪；SSR 失敗時立即補取一輪。
// 輪詢只換資料：區塊位置與 key 固定，⛔ 捲動、⛔ 移焦點、⛔ remount。

export function PlayoffsLive({ initial, year }: { initial: PlayoffsOverview | null; year: number }) {
  const [overview, setOverview] = useState<PlayoffsOverview | null>(initial);
  const [pollFailed, setPollFailed] = useState(false);

  useEffect(() => {
    const poller = new PlayoffsPoller<PlayoffsOverview, never>({
      fetchOverview: (signal) => fetchJson<PlayoffsOverview>(`${CLIENT_API}${overviewPath(year)}`, signal),
      isVisible: () => document.visibilityState === "visible",
      setTimer: (fn, ms) => window.setTimeout(fn, ms),
      clearTimer: (h) => window.clearTimeout(h as number),
      onOverview: (o) => setOverview(o),
      onRound: (r) => setPollFailed(!r.ok),
    });
    const onVisibility = () => poller.visibilityChanged();
    document.addEventListener("visibilitychange", onVisibility);
    poller.start(initial === null);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      poller.stop();
    };
    // initial 只決定首輪是否立即取；之後由控制器自己更新 overview，不因 SSR props 變動重建。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  return (
    <div className="min-w-0 space-y-6">
      <SectionTitle as="h1" date={year} meta={overview ? <span data-as-of>{asOfText(overview)}</span> : undefined}>
        季後賽
      </SectionTitle>
      {pollFailed && overview && <Notice label="暫時無法更新">{SERIES_COPY.pollFailed}</Notice>}
      {overview ? <SeriesSection overview={overview} /> : <ErrorState>{SERIES_COPY.overviewFailed}</ErrorState>}
    </div>
  );
}

export default PlayoffsLive;
