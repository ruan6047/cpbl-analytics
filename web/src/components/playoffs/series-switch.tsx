"use client";

import Link from "next/link";
import { useEffect, useRef, type MouseEvent } from "react";
import { seriesHref, type PlayoffsSeriesCode } from "@/lib/playoffs-types";

// `/playoffs` 系列切換（#285 批次 B；需求方 B2：第 1 區標題下「挑戰賽｜台灣大賽」）。
// - 路由切換語彙：兩個 Link＋`aria-current="page"`（同 level-year-nav）；`?series=` 由伺服器端選系列，⛔ 在前端
//   重選系列或目標場（overview 紅線 1）。保留網址上的 `year`、拿掉 `game`；`scroll={false}` 不跳頁首。
// - 換系列時頁面以 `year＋series` 為 key 重掛整個外殼（舊輪詢 stop()、舊回應丟棄），本元件也跟著重掛、原本被點的
//   連結節點消失。點擊時記下目標系列，新外殼掛上後把焦點還給所選那個連結（preventScroll，不捲動）。

export const SERIES_SWITCH_LABEL: Record<PlayoffsSeriesCode, string> = { E: "挑戰賽", C: "台灣大賽" };
const ORDER: PlayoffsSeriesCode[] = ["E", "C"];

/** 跨重掛的焦點交接（模組層：同一頁面工作階段內有效，整頁重載即清空）。 */
let focusAfterSwitch: PlayoffsSeriesCode | null = null;

export function SeriesSwitch({ selected, year }: {
  /** 目前畫面的系列（overview `selected_series`）；未知（overview 讀取失敗且網址未指定）時為 null。 */
  selected: PlayoffsSeriesCode | null;
  /** 網址上的 `year`（未指定為 null，連結也不帶）。 */
  year: number | null;
}) {
  const refs = useRef<Partial<Record<PlayoffsSeriesCode, HTMLAnchorElement | null>>>({});
  useEffect(() => {
    if (focusAfterSwitch === null) return;
    const target = focusAfterSwitch;
    focusAfterSwitch = null;
    if (target === selected) refs.current[target]?.focus({ preventScroll: true });
  }, [selected]);
  const onClick = (s: PlayoffsSeriesCode) => (e: MouseEvent<HTMLAnchorElement>) => {
    // 新分頁／新視窗開啟不會讓本頁重掛，不交接焦點
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    focusAfterSwitch = s === selected ? null : s;
  };
  return (
    <nav aria-label="系列" data-series-switch className="flex min-w-0 items-center">
      <span className="flex h-8 items-center rounded-md bg-band px-0.5">
        {ORDER.map((s) => {
          const active = s === selected;
          return (
            <Link key={s} href={seriesHref(s, year)} scroll={false} aria-current={active ? "page" : undefined}
              ref={(el) => { refs.current[s] = el; }} onClick={onClick(s)}
              className="inline-flex min-h-11 touch-manipulation items-center whitespace-nowrap px-0.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
              <span className={`inline-flex items-center rounded-sm px-3 py-1 transition-colors ${
                active ? "bg-ink font-bold text-paper" : "text-muted hover:text-ink"}`}>
                {SERIES_SWITCH_LABEL[s]}
              </span>
            </Link>
          );
        })}
      </span>
    </nav>
  );
}

export default SeriesSwitch;
