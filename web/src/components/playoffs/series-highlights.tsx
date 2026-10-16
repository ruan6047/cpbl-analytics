"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { TeamLogo } from "@/components/ui";
import { CLIENT_API } from "@/lib/client";
import type { Highlight } from "@/lib/game-highlights";
import {
  HIGHLIGHTS_COPY,
  acceptHighlights,
  highlightsPath,
  highlightsRows,
  type HighlightsPayload,
  type HighlightsState,
} from "@/lib/playoffs-series-highlights";
import type { PlayoffsSeriesCode } from "@/lib/playoffs-types";

// `/playoffs` 第 1 區「逐場焦點」（#288 S07 WP-K3，需求方 6218173554）。
// - 延遲載入：元件接近畫面（前 1 個視窗高度）才抓 `/api/v1/playoffs/highlights`——當前系列捲到附近時、
//   挑戰賽在 `<details>` 展開時（收合時內容沒有版面，不會觸發）。不進 overview 與首屏 SSR（A15）。
// - 重抓只看 `refreshKey`（該系列版本與涵蓋，隨 overview 30 秒輪詢更新）；⛔ 自己開計時器。
// - 回應版本 ≠ 畫面上 overview ⇒ 丟棄、保留上一份；沒有上一份 ⇒「待更新」（⛔ 拼接不同版本）。
// - 標籤用單場頁同一個 `buildHighlights`（列模型在 lib）；樣式沿用單場頁本場焦點 Chip。⛔ 捲動、⛔ 移焦點。

// 同單場頁 recap 本場焦點 Chip（#218 身分標籤：隊色只在印記）。
function Chip({ text, team }: Highlight) {
  return (
    <span className="pm-tag inline-flex items-center gap-1.5 !text-ink">
      {team && <TeamLogo code={team} size={14} decorative />}{text}
    </span>
  );
}

export function HighlightsList({ state, kind }: { state: HighlightsState; kind: PlayoffsSeriesCode }) {
  if (state.kind === "idle") {
    return <p className="min-h-11" aria-busy="true"><span className="sr-only">資料載入中</span></p>;
  }
  if (state.kind === "failed") return <p className="flex min-h-11 items-center text-sm text-muted">{HIGHLIGHTS_COPY.pending}</p>;
  const rows = highlightsRows(state.data);
  if (!rows.length) return <p className="flex min-h-11 items-center text-sm text-muted">{HIGHLIGHTS_COPY.none}</p>;
  return (
    <ol aria-label={`${kind === "E" ? "季後挑戰賽" : "台灣大賽"}逐場焦點`} className="divide-y divide-line">
      {rows.map((r) => (
        <li key={r.key} data-highlights-game={r.key}>
          <Link href={r.href}
            className="flex min-h-11 items-start gap-3 py-1.5 text-sm hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
            <span className="w-8 shrink-0 pt-0.5 font-bold text-ink">{r.label}</span>
            {r.status === "pending" ? (
              <span className="pt-0.5 text-muted">{HIGHLIGHTS_COPY.pending}</span>
            ) : r.tags.length ? (
              <span className="flex min-w-0 flex-wrap gap-1.5">{r.tags.map((t, i) => <Chip key={i} {...t} />)}</span>
            ) : (
              <span className="pt-0.5 text-muted">{HIGHLIGHTS_COPY.none}</span>
            )}
          </Link>
        </li>
      ))}
    </ol>
  );
}

export function SeriesHighlights({ year, kind, contextVersion, refreshKey }: {
  year: number;
  kind: PlayoffsSeriesCode;
  contextVersion: string;
  refreshKey: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  const [state, setState] = useState<HighlightsState>({ kind: "idle" });
  const versionRef = useRef(contextVersion);
  versionRef.current = contextVersion;

  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    if (typeof IntersectionObserver === "undefined") { setNear(true); return; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setNear(true); io.disconnect(); }
    }, { rootMargin: `${typeof window === "undefined" ? 0 : window.innerHeight}px 0px` });
    io.observe(el);
    // 收合在 <details> 裡（挑戰賽）時，展開事件直接觸發，不等觀察器的下一個渲染幀。
    const det = el.closest("details");
    const onToggle = () => { if (det?.open) setNear(true); };
    det?.addEventListener("toggle", onToggle);
    return () => { io.disconnect(); det?.removeEventListener("toggle", onToggle); };
  }, [near]);

  useEffect(() => {
    if (!near) return;
    const ctrl = new AbortController();
    fetch(`${CLIENT_API}${highlightsPath(year, kind)}`, { cache: "no-store", signal: ctrl.signal })
      .then((res) => (res.ok ? (res.json() as Promise<HighlightsPayload>) : null))
      .then((payload) => setState((prev) => acceptHighlights(prev, payload, versionRef.current)))
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name === "AbortError") return;
        setState((prev) => acceptHighlights(prev, null, versionRef.current));
      });
    return () => ctrl.abort();
  }, [near, year, kind, refreshKey]);

  return (
    <div ref={ref} className="min-w-0 md:col-span-2" data-highlights-block={kind}>
      <h4 className="text-xs font-bold text-muted">{HIGHLIGHTS_COPY.heading}</h4>
      <HighlightsList state={state} kind={kind} />
    </div>
  );
}

export default SeriesHighlights;
