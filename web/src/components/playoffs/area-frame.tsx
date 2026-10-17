"use client";

import { useEffect, useRef, type ComponentType } from "react";
import { Notice } from "@/components/ui";
import { AREA_SCROLL_MARGIN, DEFAULT_AREA_MIN_HEIGHT_PX, type RegisteredAreaId } from "@/lib/playoffs-areas";
import type { WatchState } from "@/lib/playoffs-poll";

// `/playoffs` 第 2／3 區外框（#285 續做 WP2；MOUNT-CONTRACT r3 §1–§3）。與已上線的 `#watch`（watch-area.tsx）同一套規則：
// - 錨點 `<div id>`＋同值 scroll-margin；首次取得前固定最小高度占位，錨點跳轉後不位移。最小高度只在占位時套用
//   （契約 §2「占位高度」；#285 批次 B 發現 2）：區元件掛上後外框高＝元件高，名單缺等短內容不在下方留白。
// - 外框接近 viewport（前 1 個視窗高度）才呼叫 `onNear` 啟用該區；不支援 IntersectionObserver 時掛載即啟用。
// - 各卡的 Section 固定為外框第一個子節點、不給 key：輪詢只換 `data`，元件內的篩選、輸入、抽屜不被 remount。
// - 提示放在 Section 之後；⛔ 在外框設 transform／filter／contain／overflow-hidden（會困住 portal 以外的
//   position: fixed，契約 §2.3 疊層保證）。
// - 錨點補正：以 `/playoffs#teams` 等直接進入時，瀏覽器在區資料到之前就捲動，頁面還不夠高、標題會停在畫面外
//   （P2 桌機實測 #teams 標題頂 1061／視窗 900）。網址錨點指向本區、且使用者自載入後還沒捲動或操作（滾輪、觸控、
//   點擊、鍵盤）時，**本區或它前面任一區第一次取得內容**就重新對齊（#285 批次 B，需求方「錨點位移：甲」）：
//   前面的區晚到時會把本區往下推（名單齊）或往上拉（名單缺、外框不再固定占位高度），只對齊本區自己會被推出畫面。
//   「有內容」＝外框第一個子節點不是占位 `<p role="status">`（本外框與 watch-area 同一套占位標記）：
//   `stale` 且沒有上一份仍是占位，⛔ 算第一次內容（審核 B-01：曾以「非 idle」判定，首輪錯版占位就耗掉補正）。
//   每區只算第一次；之後的輪詢更新、stale／error 轉換 ⛔ 捲動。使用者一操作就停止。

let userInteracted = false;
function watchInteraction(): void {
  if (typeof window === "undefined" || (window as { __playoffsAnchorWatch?: boolean }).__playoffsAnchorWatch) return;
  (window as { __playoffsAnchorWatch?: boolean }).__playoffsAnchorWatch = true;
  const mark = () => { userInteracted = true; };
  for (const ev of ["wheel", "touchstart", "keydown", "pointerdown"]) window.addEventListener(ev, mark, { once: true, passive: true });
}

export const AREA_COPY = {
  loading: "資料載入中…",
  updating: "資料更新中，暫時顯示上一份一致的內容",
  updatingEmpty: "資料更新中",
  refreshFailed: "最新資料暫時無法取得，暫時顯示上一份內容",
} as const;

/** 外框 className（測試會檢查不含困住 fixed 的樣式）。 */
export const AREA_FRAME_CLASS = `min-w-0 ${AREA_SCROLL_MARGIN}`;

/** 外殼直接子節點中、目標（含）之前帶狀態屬性的區：[id, 是否已有內容]（第 2／3 區 `data-area-state`、第 4 區 `data-watch-state`）。 */
export type AnchorStates = [string, boolean][];

/**
 * 錨點補正判斷（純函式）：`seen` 記已第一次取得內容的區。回傳本次是否有區**第一次**取得內容（要重新對齊），
 * 以及是否全部都已取得過（之後不會再有「第一次」，可停止觀察）。
 */
export function takeFirstContent(states: AnchorStates, seen: Set<string>): { realign: boolean; settled: boolean } {
  let realign = false;
  for (const [id, filled] of states) {
    if (filled && !seen.has(id)) {
      seen.add(id);
      realign = true;
    }
  }
  return { realign, settled: states.every(([id]) => seen.has(id)) };
}

/** 占位時外框只有 `<p role="status">`（idle、stale 無上一份、第 4 區無目標場）；其他第一個子節點＝區元件已掛上。 */
export function isPlaceholder(first: { tagName: string; getAttribute(name: string): string | null } | null): boolean {
  return first === null || (first.tagName === "P" && first.getAttribute("role") === "status");
}

function anchorStates(parent: Element, target: Element): AnchorStates {
  const out: AnchorStates = [];
  for (const c of Array.from(parent.children)) {
    const st = c.getAttribute("data-area-state") ?? c.getAttribute("data-watch-state");
    if (st !== null && c.id) out.push([c.id, !isPlaceholder(c.firstElementChild)]);
    if (c === target) break;
  }
  return out;
}

export function AreaFrame<T>({ id, state, Section, minHeightPx, onNear, hidden }: {
  id: RegisteredAreaId;
  state: WatchState<T>;
  Section: ComponentType<{ data: T | null }>;
  minHeightPx?: number;
  onNear?: (id: RegisteredAreaId) => void;
  hidden?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { watchInteraction(); }, []);
  useEffect(() => {
    const el = ref.current;
    const parent = el?.parentElement;
    if (!el || !parent || typeof MutationObserver === "undefined" || window.location.hash !== `#${id}`) return;
    const seen = new Set<string>();
    takeFirstContent(anchorStates(parent, el), seen);   // 掛載當下已有內容者不算「第一次」
    const mo = new MutationObserver(() => {
      if (userInteracted) {
        mo.disconnect();
        return;
      }
      const r = takeFirstContent(anchorStates(parent, el), seen);
      if (r.realign) el.scrollIntoView({ block: "start" });
      if (r.settled) mo.disconnect();
    });
    mo.observe(parent, { subtree: true, attributes: true, attributeFilter: ["data-area-state", "data-watch-state"] });
    return () => mo.disconnect();
  }, [id]);
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
    <div id={id} ref={ref} className={AREA_FRAME_CLASS}
      style={mountSection ? undefined : { minHeight: `${minHeightPx ?? DEFAULT_AREA_MIN_HEIGHT_PX}px` }}
      data-area-state={state.kind}
      hidden={hidden || undefined}>
      {mountSection ? <Section data={shown} /> : null}
      {placeholder ? <p role="status" className="rounded bg-surface p-3 text-sm text-muted">{placeholder}</p> : null}
      {notice ? <Notice label="資料更新中" className="mt-3">{notice}</Notice> : null}
    </div>
  );
}

export default AreaFrame;
