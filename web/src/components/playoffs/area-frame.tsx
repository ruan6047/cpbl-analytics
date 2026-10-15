"use client";

import { useEffect, useRef, type ComponentType } from "react";
import { Notice } from "@/components/ui";
import { AREA_SCROLL_MARGIN, DEFAULT_AREA_MIN_HEIGHT_PX, type RegisteredAreaId } from "@/lib/playoffs-areas";
import type { WatchState } from "@/lib/playoffs-poll";

// `/playoffs` 第 2／3 區外框（#285 續做 WP2；MOUNT-CONTRACT r3 §1–§3）。與已上線的 `#watch`（watch-area.tsx）同一套規則：
// - 錨點 `<div id>`＋同值 scroll-margin；首次取得前固定最小高度占位，錨點跳轉後不位移。
// - 外框接近 viewport（前 1 個視窗高度）才呼叫 `onNear` 啟用該區；不支援 IntersectionObserver 時掛載即啟用。
// - 各卡的 Section 固定為外框第一個子節點、不給 key：輪詢只換 `data`，元件內的篩選、輸入、抽屜不被 remount。
// - 提示放在 Section 之後；⛔ 在外框設 transform／filter／contain／overflow-hidden（會困住 portal 以外的
//   position: fixed，契約 §2.3 疊層保證）。

export const AREA_COPY = {
  loading: "資料載入中…",
  updating: "資料更新中，暫時顯示上一份一致的內容",
  updatingEmpty: "資料更新中",
  refreshFailed: "最新資料暫時無法取得，暫時顯示上一份內容",
} as const;

/** 外框 className（測試會檢查不含困住 fixed 的樣式）。 */
export const AREA_FRAME_CLASS = `min-w-0 ${AREA_SCROLL_MARGIN}`;

export function AreaFrame<T>({ id, state, Section, minHeightPx, onNear }: {
  id: RegisteredAreaId;
  state: WatchState<T>;
  Section: ComponentType<{ data: T | null }>;
  minHeightPx?: number;
  onNear?: (id: RegisteredAreaId) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !onNear) return;
    if (typeof IntersectionObserver === "undefined") {
      onNear(id);
      return;
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        onNear(id);
        io.disconnect();
      }
    }, { rootMargin: "100% 0px 100% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [id, onNear]);

  const shown: T | null = state.kind === "data" ? state.data : state.kind === "idle" ? null : state.previous;
  const mountSection = shown !== null || state.kind === "error";
  const notice = state.kind === "stale" && shown ? AREA_COPY.updating
    : state.kind === "error" && shown ? AREA_COPY.refreshFailed : null;
  const placeholder = mountSection ? null : state.kind === "stale" ? AREA_COPY.updatingEmpty : AREA_COPY.loading;
  return (
    <div id={id} ref={ref} className={AREA_FRAME_CLASS} style={{ minHeight: `${minHeightPx ?? DEFAULT_AREA_MIN_HEIGHT_PX}px` }}
      data-area-state={state.kind}>
      {mountSection ? <Section data={shown} /> : null}
      {placeholder ? <p role="status" className="rounded bg-surface p-3 text-sm text-muted">{placeholder}</p> : null}
      {notice ? <Notice label="資料更新中" className="mt-3">{notice}</Notice> : null}
    </div>
  );
}

export default AreaFrame;
