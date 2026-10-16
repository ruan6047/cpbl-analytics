"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SectionTitle } from "@/components/postmark";
import { ErrorState, Notice } from "@/components/ui";
import { CLIENT_API } from "@/lib/client";
import { orderedRegistrations, type AreaRegistration, type RegisteredAreaId } from "@/lib/playoffs-areas";
import { PAGE_NOTES, mergeNotes, shownData, warnNoteConflicts } from "@/lib/playoffs-notes";
import { PlayoffsPoller, fetchJson, type VersionedArea, type WatchState } from "@/lib/playoffs-poll";
import { seriesSummaryNotes } from "@/lib/playoffs-series-summary";
import { SERIES_COPY, asOfText } from "@/lib/playoffs-series-view";
import { overviewPath, watchPath, type PlayoffsOverview, type PlayoffsSeriesCode } from "@/lib/playoffs-types";
import type { PlayoffsWatch } from "@/lib/playoffs-watch";
import { AreaFrame } from "./area-frame";
import { PLAYOFFS_AREAS } from "./area-registry";
import { PageNotes } from "./page-notes";
import { SeriesSection } from "./series-section";
import { SeriesSwitch } from "./series-switch";
import { WatchArea } from "./watch-area";

// `/playoffs` 的 client 外殼（#285 S04）：持有 overview、第 4 區與第 2／3 區狀態並跑共用輪詢控制器（playoffs-poll.ts）。
// 首屏 SSR 只給 overview（HTML 已含第 1 區）；掛載後立即一輪「overview → watch → 已啟用的區」，之後每 30 秒一輪。
// watch 與各區一律 client 端自取 `CLIENT_API`：⛔ 用各卡讀 server 端 API_URL 的取數函式（瀏覽器內會退回 localhost:4001）。
// 區塊順序固定 1→4→3→2（需求方 C2）；第 2／3 區只在 `area-registry.ts` 有登記時出現（C1），接近 viewport 才載入。
// 頁尾說明（6194706200）：PAGE_NOTES＋各區 `notes(畫面上那份資料)`，0 條不渲染。
// 系列（#285 批次 B）：`series`＝網址 `?series=`（未指定為 null，跟隨 S02 預設）。SSR 與輪詢用同一個值取 overview；
// 第 2／3／4 區的 series 一律取 overview `selected_series`。換系列由頁面以 key 重掛本元件，⛔ 在本元件內切換。
// 輪詢只換資料：區塊位置與 key 固定，⛔ 捲動、⛔ 移焦點、⛔ remount；本元件與外框 ⛔ 設 transform／filter／contain／
// overflow-hidden（各區抽屜以 portal z-50 疊在 sticky header 之上，契約 §2.3）。

export const PLAYOFFS_LIVE_CLASS = "min-w-0 space-y-6";

export function PlayoffsLive({ initial, year, game, series = null, yearParam = null, areas }: {
  initial: PlayoffsOverview | null;
  year: number;
  game: number | null;
  /** 網址 `?series=`；null＝未指定（跟隨 S02 預設系列）。 */
  series?: PlayoffsSeriesCode | null;
  /** 網址上的 `?year=`（未指定為 null）：系列切換連結只在網址有帶時保留。 */
  yearParam?: number | null;
  /** 第 2／3 區登記；預設讀 `area-registry.ts`（測試可注入）。 */
  // `any`：各區 payload 型別不同（AreaRegistration<各自型別>）。
  areas?: AreaRegistration<any>[];
}) {
  const regs = useMemo(() => orderedRegistrations(areas ?? PLAYOFFS_AREAS), [areas]);
  const [overview, setOverview] = useState<PlayoffsOverview | null>(initial);
  const [watch, setWatch] = useState<WatchState<PlayoffsWatch>>({ kind: "idle" });
  const [areaStates, setAreaStates] = useState<Partial<Record<RegisteredAreaId, WatchState<VersionedArea>>>>({});
  const [pollFailed, setPollFailed] = useState(false);
  const pollerRef = useRef<PlayoffsPoller<PlayoffsOverview, PlayoffsWatch> | null>(null);
  const pendingNear = useRef(new Set<RegisteredAreaId>());

  useEffect(() => {
    const poller = new PlayoffsPoller<PlayoffsOverview, PlayoffsWatch>({
      fetchOverview: (signal) => fetchJson<PlayoffsOverview>(`${CLIENT_API}${overviewPath(year, series)}`, signal),
      fetchWatch: (t, signal) =>
        fetchJson<PlayoffsWatch>(`${CLIENT_API}${watchPath(year, t.series as PlayoffsSeriesCode, t.game)}`, signal),
      areas: regs.map((r) => ({
        id: r.id,
        refresh: r.refresh,
        fetch: (series: string, signal: AbortSignal) =>
          fetchJson<VersionedArea>(`${CLIENT_API}${r.path(year, series as PlayoffsSeriesCode)}`, signal),
      })),
      isVisible: () => document.visibilityState === "visible",
      setTimer: (fn, ms) => window.setTimeout(fn, ms),
      clearTimer: (h) => window.clearTimeout(h as number),
      onOverview: (o) => setOverview(o),
      onWatch: (s) => setWatch(s),
      onArea: (id, s) => setAreaStates((prev) => ({ ...prev, [id]: s })),
      onRound: (r) => setPollFailed(!r.overviewOk),
    }, game);
    pollerRef.current = poller;
    // 外框的 effect 先於本 effect 執行：控制器建立前就接近 viewport 的區，隨第一輪一起取。
    poller.preactivate(pendingNear.current);
    pendingNear.current.clear();
    const onVisibility = () => poller.visibilityChanged();
    document.addEventListener("visibilitychange", onVisibility);
    poller.start(true);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      poller.stop();
      pollerRef.current = null;
    };
    // game 變更走 setGame（下方 effect），不重建控制器；year／series 變更由頁面以 key 重新掛載；regs 只隨登記（建置期常數）變。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, regs]);

  useEffect(() => {
    pollerRef.current?.setGame(game);
  }, [game]);

  const onNear = useCallback((id: RegisteredAreaId) => {
    if (pollerRef.current) pollerRef.current.activate(id);
    else pendingNear.current.add(id);
  }, []);

  const { notes, conflicts } = mergeNotes([
    { area: "series", notes: [...PAGE_NOTES.series, ...seriesSummaryNotes(overview)] },
    { area: "watch", notes: PAGE_NOTES.watch },
    ...regs.map((r) => ({ area: r.id, notes: r.notes ? r.notes(shownData(areaStates[r.id])) : [] })),
  ]);
  const conflictKey = JSON.stringify(conflicts);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- 以內容字串為依賴，避免每次渲染重複 warn
  useEffect(() => warnNoteConflicts(conflicts), [conflictKey]);

  return (
    <div className={PLAYOFFS_LIVE_CLASS}>
      <SectionTitle as="h1" date={year} meta={overview ? <span data-as-of>{asOfText(overview)}</span> : undefined}>
        季後賽
      </SectionTitle>
      <SeriesSwitch selected={overview?.selected_series ?? series ?? overview?.default_series ?? null} year={yearParam} />
      {pollFailed && overview && <Notice label="暫時無法更新">{SERIES_COPY.pollFailed}</Notice>}
      {overview ? <SeriesSection overview={overview} /> : <ErrorState>{SERIES_COPY.overviewFailed}</ErrorState>}
      <WatchArea state={watch} overview={overview} requested={game !== null} />
      {regs.map((r) => (
        <AreaFrame key={r.id} id={r.id} state={areaStates[r.id] ?? { kind: "idle" }} Section={r.Section}
          minHeightPx={r.minHeightPx} onNear={onNear} />
      ))}
      <PageNotes notes={notes} />
    </div>
  );
}

export default PlayoffsLive;
