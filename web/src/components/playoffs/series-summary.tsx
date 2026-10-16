import { TeamLogo } from "@/components/ui";
import {
  SUMMARY_COPY,
  batterValueText,
  boardReady,
  mvpBadge,
  pitcherValueText,
  playerName,
  showSummary,
  summaryTitle,
  type SeriesSummary,
  type SeriesSummaryBlock,
} from "@/lib/playoffs-series-summary";
import { teamLabel } from "@/lib/playoffs-series-view";

// `/playoffs` 第 1 區系列累計榜（#288 S07 WP-G2）。無 hooks、純排字：SSR 首屏與 client 輪詢共用，輪詢只換 props，
// ⛔ 自行捲動或移焦點。
//
// 需求方裁定（#288 6206035029）：
// - K2 甲：當前系列累計榜放第 1 區最下方、展開；原本四項（大比分／場次卡／預告／前一系列一句）不動。
// - K4：前一系列（挑戰賽）累計榜也做，預設收合（`<details>`，鍵盤可開關），不與當前系列混排。
// 格內缺值只用「—」「待更新」，原因寫頁尾（#281 6194693029；`seriesSummaryNotes`）。
// 沒有完賽場的系列整塊省略（PRD「沒有就省略，不套模板」）。

function Who({ p }: { p: { name: string | null; team_code: string | null } }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {p.team_code && <TeamLogo code={p.team_code} name={teamLabel(p.team_code)} size={20} />}
      <span className="truncate font-bold text-ink">{playerName(p)}</span>
    </span>
  );
}

function Badge({ n }: { n: number }) {
  const t = mvpBadge(n);
  return t ? <span className="shrink-0 rounded-sm bg-surface-2 px-1.5 text-[11px] leading-5 text-ink">{t}</span> : null;
}

function Cell({ text }: { text: string }) {
  return <p className="flex min-h-11 items-center text-sm text-muted">{text}</p>;
}

function Board({ block }: { block: SeriesSummaryBlock }) {
  const ready = boardReady(block);
  const row = "flex min-h-11 flex-wrap items-center gap-x-2 gap-y-0.5 py-1 text-sm";
  const mvpEmpty = block.mvp_missing_games.length ? SUMMARY_COPY.pending : SUMMARY_COPY.missing;
  return (
    <div className="grid min-w-0 gap-3 md:grid-cols-2" data-summary-board={block.kind_code}>
      <div className="min-w-0">
        <h4 className="text-xs font-bold text-muted">{SUMMARY_COPY.batterHeading}</h4>
        {!ready ? <Cell text={SUMMARY_COPY.pending} /> : block.batters.length ? (
          <ol aria-label={`${summaryTitle(block)}・${SUMMARY_COPY.batterHeading}`} className="divide-y divide-line">
            {block.batters.map((b) => (
              <li key={b.player_id} className={row} data-player={b.player_id}>
                <Who p={b} />
                <span className="text-xs text-muted tabular-nums">PA {b.pa}</span>
                <span className="text-ink tabular-nums">{batterValueText(b.re24_raw)}</span>
                <Badge n={b.mvp_count} />
              </li>
            ))}
          </ol>
        ) : <Cell text={SUMMARY_COPY.missing} />}
      </div>
      <div className="min-w-0">
        <h4 className="text-xs font-bold text-muted">{SUMMARY_COPY.pitcherHeading}</h4>
        {!ready ? <Cell text={SUMMARY_COPY.pending} /> : block.pitchers.length ? (
          <ol aria-label={`${summaryTitle(block)}・${SUMMARY_COPY.pitcherHeading}`} className="divide-y divide-line">
            {block.pitchers.map((p) => (
              <li key={p.player_id} className={row} data-player={p.player_id}>
                <Who p={p} />
                <span className="text-xs text-muted tabular-nums">BF {p.bf}</span>
                <span className="text-ink tabular-nums">{pitcherValueText(p.value_raw)}</span>
                <Badge n={p.mvp_count} />
              </li>
            ))}
          </ol>
        ) : <Cell text={SUMMARY_COPY.missing} />}
      </div>
      <div className="min-w-0">
        <h4 className="text-xs font-bold text-muted">{SUMMARY_COPY.mvpListHeading}</h4>
        {block.mvp_counts.length ? (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 py-1 text-sm" data-mvp-counts>
            {block.mvp_counts.map((m) => (
              <li key={m.player_id} className="flex min-h-11 items-center gap-1.5">
                <Who p={m} />
                <span className="text-ink tabular-nums">×{m.count}</span>
              </li>
            ))}
          </ul>
        ) : <Cell text={mvpEmpty} />}
      </div>
      <div className="min-w-0">
        <h4 className="text-xs font-bold text-muted">{SUMMARY_COPY.awardsLabel}</h4>
        <Cell text={SUMMARY_COPY.pending} />
      </div>
    </div>
  );
}

export function SeriesSummaryBlock({ summary }: { summary: SeriesSummary | null | undefined }) {
  if (!summary) return null;
  const prev = showSummary(summary.previous) ? summary.previous : null;
  const cur = showSummary(summary.current) ? summary.current : null;
  if (!prev && !cur) return null;
  return (
    <div className="min-w-0 space-y-3" data-series-summary>
      {prev && (
        <details className="group min-w-0 rounded-md bg-surface px-3" data-summary={prev.kind_code}>
          <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
            {summaryTitle(prev)}
            {/* flex 會拿掉預設三角：補文字提示（狀態不只靠圖示） */}
            <span className="ml-auto text-xs font-normal text-accent" aria-hidden>
              <span className="group-open:hidden">展開</span><span className="hidden group-open:inline">收合</span>
            </span>
          </summary>
          <div className="pb-3"><Board block={prev} /></div>
        </details>
      )}
      {cur && (
        <div className="min-w-0 rounded-md bg-surface px-3 py-2.5" data-summary={cur.kind_code}>
          <h3 className="mb-1 text-sm font-bold text-ink">{summaryTitle(cur)}</h3>
          <Board block={cur} />
        </div>
      )}
    </div>
  );
}

export default SeriesSummaryBlock;
