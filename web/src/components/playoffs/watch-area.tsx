import { Notice } from "@/components/ui";
import { WatchSection } from "@/components/playoffs/watch-section";
import type { WatchState } from "@/lib/playoffs-poll";
import type { PlayoffsOverview } from "@/lib/playoffs-types";
import type { PlayoffsWatch } from "@/lib/playoffs-watch";

// `/playoffs` 第 4 區外框（#285 S04 WP4）：`#watch` 錨點＋掛 #289 的 `WatchSection`（含 4B 兩格與先發灰列，
// 需求方 E3：整個元件照常顯示，⛔ 拆、⛔ 用 CSS 藏任何一部分）。無 hooks、純排字。
//
// - 版本不一致時保留上一份一致畫面＋「資料更新中」（控制器給 stale），⛔ 拼接不同版本。
// - `WatchSection` 固定在同一子節點位置、不給 key：輪詢只換 props，「其他投手」`<details>` 不會被收起。
//   提示一律放在元件之後，出現時不把正在讀的內容往下推。
// - 首次取得前以固定最小高度占位，錨點跳轉後不位移。

export const WATCH_COPY = {
  loading: "第 4 區資料載入中…",
  updating: "第 4 區資料更新中，暫時顯示上一份一致的內容",
  updatingEmpty: "第 4 區資料更新中",
  refreshFailed: "第 4 區最新資料暫時無法取得，暫時顯示上一份內容",
  noTarget: "目前沒有可呈現觀戰重點的目標場次",
} as const;

export function WatchArea({ state, overview, requested }: {
  state: WatchState<PlayoffsWatch>;
  overview: PlayoffsOverview | null;
  /** 目標場來自 `?game`（使用者指定）。 */
  requested: boolean;
}) {
  const shown: PlayoffsWatch | null = state.kind === "data" ? state.data
    : state.kind === "idle" ? null : state.previous;
  const noTarget = state.kind === "idle" && !requested && overview?.sections.watch.status === "no_target";
  // 有內容（或讀取失敗而無上一份，交給 WatchSection 的錯誤態）就掛元件；否則占位文字。
  const mountSection = shown !== null || state.kind === "error";
  const notice = state.kind === "stale" && shown ? WATCH_COPY.updating
    : state.kind === "error" && shown ? WATCH_COPY.refreshFailed : null;
  const placeholder = mountSection ? null
    : noTarget ? WATCH_COPY.noTarget
    : state.kind === "stale" ? WATCH_COPY.updatingEmpty : WATCH_COPY.loading;
  return (
    <div id="watch" className="min-h-48 min-w-0 scroll-mt-[70px] md:scroll-mt-[76px]" data-watch-state={state.kind}>
      {mountSection ? <WatchSection data={shown} /> : null}
      {placeholder ? <p role="status" className="rounded bg-surface p-3 text-sm text-muted">{placeholder}</p> : null}
      {notice ? <Notice label="資料更新中" className="mt-3">{notice}</Notice> : null}
    </div>
  );
}

export default WatchArea;
