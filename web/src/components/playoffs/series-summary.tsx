import { Card, InfoDot, TeamLogo } from "@/components/ui";
import { WpSwingBadge } from "@/components/wp-swing-badge";
import {
  SUMMARY_COPY,
  batterValueText,
  boardReady,
  mvpBadge,
  pitcherValueText,
  playerName,
  showSummary,
  summaryTitle,
  turningCaption,
  turningHeading,
  turningRe24Text,
  turningScoreChange,
  turningSituation,
  type SeriesSummary,
  type SeriesSummaryBlock,
  type TurningPoint,
  highlightsEnabled,
} from "@/lib/playoffs-series-summary";
import { highlightsKey, HIGHLIGHTS_NOTE } from "@/lib/playoffs-series-highlights";
import { teamLabel } from "@/lib/playoffs-series-view";
import { SeriesHighlights } from "./series-highlights";

function Who({ p }: { p: { name: string | null; team_code: string | null } }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {p.team_code && <TeamLogo code={p.team_code} name={teamLabel(p.team_code)} size={18} decorative />}
      <span className="truncate font-bold text-ink">{playerName(p)}</span>
    </span>
  );
}

function Badge({ n }: { n: number }) {
  const t = mvpBadge(n);
  return t ? <span className="pm-tag shrink-0">{t}</span> : null;
}

function Cell({ text }: { text: string }) {
  return <p className="flex min-h-11 items-center text-sm text-muted">{text}</p>;
}

function TurningRow({ t }: { t: TurningPoint }) {
  const score = turningScoreChange(t);
  const re24 = turningRe24Text(t);
  const hitter = t.hitter?.name ?? t.hitter?.player_id ?? SUMMARY_COPY.missing;
  return (
    <li className="flex min-h-11 min-w-0 flex-col justify-center gap-0.5 py-2 text-sm" data-turning={`${t.series_game_no}-${t.pa_index}`}>
      <span className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-2">
        <span className="min-w-0 text-xs text-muted">{turningSituation(t)}</span>
        {t.delta_wp !== null && (
          <WpSwingBadge value={t.delta_wp} homeName={teamLabel(t.home_team_code)} awayName={teamLabel(t.away_team_code)}
            homeColor="" awayColor="" />
        )}
      </span>
      <span className="flex flex-wrap items-baseline justify-between gap-2 text-ink">
        <span>
          <span className="font-bold">{hitter}</span>
          {t.result_action ? ` ${t.result_action}` : ""}
          {t.pitcher?.name ? <span className="text-muted">（vs {t.pitcher.name}）</span> : null}
        </span>
        <span className="flex flex-wrap gap-x-2 text-xs text-muted tabular-nums">
          {score && <span>比分（客：主）{score.before} → {score.after}</span>}
          {t.delta_wp === null && re24 && <span>{re24}</span>}
        </span>
      </span>
    </li>
  );
}

function Turning({ block, ready }: { block: SeriesSummaryBlock; ready: boolean }) {
  const t = block.turning_points;
  if (t === undefined) return null;
  return (
    <div className="min-w-0 rounded-md bg-surface-2 px-3 py-2.5 md:col-span-2" data-turning-block={block.kind_code}>
      <h4 className="flex items-center gap-1.5 text-xs font-bold text-muted">
        <span>{t ? turningHeading(t) : SUMMARY_COPY.turningHeading}</span>
        {t && ready && <span className="font-normal text-faint">（{turningCaption(t)}）</span>}
      </h4>
      {!ready || !t ? <Cell text={SUMMARY_COPY.pending} /> : t.items.length ? (
        <ol aria-label={`${summaryTitle(block)}・${turningHeading(t)}`} className="mt-1 divide-y divide-line">
          {t.items.map((item) => <TurningRow key={`${item.series_game_no}-${item.pa_index}`} t={item} />)}
        </ol>
      ) : <Cell text={SUMMARY_COPY.missing} />}
    </div>
  );
}

function Board({ block, summary }: { block: SeriesSummaryBlock; summary: SeriesSummary }) {
  const ready = boardReady(block);
  const row = "flex min-h-11 items-center justify-between gap-2 py-1 text-sm";
  const mvpEmpty = block.mvp_missing_games.length ? SUMMARY_COPY.pending : SUMMARY_COPY.missing;
  return (
    <div className="grid min-w-0 gap-3 md:grid-cols-2" data-summary-board={block.kind_code}>
      <div className="min-w-0 rounded-md bg-surface-2 px-3 py-2.5">
        <div className="flex items-baseline justify-between text-xs text-muted">
          <h4 className="font-bold">{SUMMARY_COPY.batterHeading}</h4>
          <span>得分期望累計（ΔRE24）</span>
        </div>
        {!ready ? <Cell text={SUMMARY_COPY.pending} /> : block.batters.length ? (
          <ol aria-label={`${summaryTitle(block)}・${SUMMARY_COPY.batterHeading}`} className="mt-1 divide-y divide-line">
            {block.batters.map((b) => (
              <li key={b.player_id} className={row} data-player={b.player_id}>
                <Who p={b} />
                <span className="flex shrink-0 items-center gap-2 tabular-nums">
                  <span className="text-xs text-muted">PA {b.pa}</span>
                  <span className="font-mono font-bold text-ink">{batterValueText(b.re24_raw)}</span>
                  <Badge n={b.mvp_count} />
                </span>
              </li>
            ))}
          </ol>
        ) : <Cell text={SUMMARY_COPY.missing} />}
      </div>
      <div className="min-w-0 rounded-md bg-surface-2 px-3 py-2.5">
        <div className="flex items-baseline justify-between text-xs text-muted">
          <h4 className="font-bold">{SUMMARY_COPY.pitcherHeading}</h4>
          <span>壓制貢獻累計（−ΔRE24）</span>
        </div>
        {!ready ? <Cell text={SUMMARY_COPY.pending} /> : block.pitchers.length ? (
          <ol aria-label={`${summaryTitle(block)}・${SUMMARY_COPY.pitcherHeading}`} className="mt-1 divide-y divide-line">
            {block.pitchers.map((p) => (
              <li key={p.player_id} className={row} data-player={p.player_id}>
                <Who p={p} />
                <span className="flex shrink-0 items-center gap-2 tabular-nums">
                  <span className="text-xs text-muted">BF {p.bf}</span>
                  <span className="font-mono font-bold text-ink">{pitcherValueText(p.value_raw)}</span>
                  <Badge n={p.mvp_count} />
                </span>
              </li>
            ))}
          </ol>
        ) : <Cell text={SUMMARY_COPY.missing} />}
      </div>
      <div className="min-w-0 md:col-span-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-surface-2 px-3 py-2 text-sm">
          <h4 className="text-xs font-bold text-muted">{SUMMARY_COPY.mvpListHeading}</h4>
          {block.mvp_counts.length ? (
            <ul className="flex flex-wrap gap-x-4 gap-y-1" data-mvp-counts>
              {block.mvp_counts.map((m) => (
                <li key={m.player_id} className="flex min-h-9 items-center gap-1.5">
                  <Who p={m} />
                  <span className="font-mono text-xs text-muted tabular-nums">×{m.count}</span>
                </li>
              ))}
            </ul>
          ) : <span className="text-sm text-muted">{mvpEmpty}</span>}
        </div>
      </div>
      <Turning block={block} ready={ready} />
      {highlightsEnabled(summary) && (
        <SeriesHighlights year={summary.year!} kind={block.kind_code} contextVersion={summary.context_version!}
          refreshKey={highlightsKey(summary.context_version, block)} />
      )}
    </div>
  );
}

function SummaryMethodHelp({ showHighlights }: { showHighlights: boolean }) {
  return (
    <InfoDot
      label="累計榜與轉折計算說明"
      content={
        <div className="space-y-1">
          <p>累計榜依本系列已完賽場逐打席 ΔRE24 計算（打者得分期望、投手轉號壓制貢獻），非官方獎項。</p>
          <p>三大轉折取本系列勝率變化絕對值最大的 3 個打席，依時間排列。</p>
          {showHighlights && <p>{HIGHLIGHTS_NOTE.text}</p>}
        </div>
      }
    />
  );
}

export function SeriesSummaryBlock({ summary }: { summary: SeriesSummary | null | undefined }) {
  if (!summary) return null;
  const prev = showSummary(summary.previous) ? summary.previous : null;
  const cur = showSummary(summary.current) ? summary.current : null;
  if (!prev && !cur) return null;
  const hasHl = highlightsEnabled(summary);
  return (
    <div className="min-w-0 space-y-3" data-series-summary>
      {prev && (
        <details className="group card min-w-0 px-3.5 py-2" data-summary={prev.kind_code}>
          <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
            <span>{summaryTitle(prev)}</span>
            <span className="ml-auto text-xs font-normal text-accent" aria-hidden>
              <span className="group-open:hidden">展開</span><span className="hidden group-open:inline">收合</span>
            </span>
          </summary>
          <div className="pt-2 pb-1.5"><Board block={prev} summary={summary} /></div>
        </details>
      )}
      {cur && (
        <div className="card p-3.5" data-summary={cur.kind_code}>
          <h3 className="mb-2.5 text-sm font-bold text-ink">{summaryTitle(cur)}</h3>
          <div className="mb-2 flex items-center gap-1.5 text-xs text-muted">
            <span>累計貢獻與轉折</span>
            <SummaryMethodHelp showHighlights={hasHl} />
          </div>
          <Board block={cur} summary={summary} />
        </div>
      )}
    </div>
  );
}

export default SeriesSummaryBlock;
