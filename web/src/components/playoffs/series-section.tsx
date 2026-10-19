import Link from "next/link";
import { Notice, TeamLogo } from "@/components/ui";
import type { OverviewGameCard, OverviewSeriesBlock, PlayoffsOverview } from "@/lib/playoffs-types";
import {
  SERIES_COPY,
  SERIES_NAME,
  bigScore,
  chipView,
  dateText,
  gameHref,
  gameTitle,
  nextGameMissingText,
  seriesNotices,
  seriesStatusLine,
  startText,
  teamLabel,
  visibleCards,
} from "@/lib/playoffs-series-view";
import { SeriesSummaryBlock } from "./series-summary";

// `/playoffs` 第 1 區「系列賽表現」（#285 S04）。無 hooks、純排字：SSR 首屏與 client 輪詢共用同一元件，
// 輪詢只換 props，⛔ 自行捲動或移焦點。
//
// 需求方 SHA-F2 人工審核（issuecomment-6190739641）後的呈現：
// - 第 1 區桌機與手機都在第一個畫面內看完：當前系列大比分 → 精簡場次卡 → 下一場預告（前一系列不畫，批次 D）。
//   大比分放最上面，一眼看到；第 4 區往下捲才看到。
// - 場次卡改格狀（不橫捲）：手機 4 欄、桌機 7 欄；每張只放場序、日期、兩隊（分數或客主）、一行補充。
// - 整張卡就是單場連結（D3 的「單場連結」），卡內不再另放連結文字。
// - 預告放日期、開賽時刻、球場、主客，以及一行先發「先發：客隊 text・主隊 text」（S11 官方先發，字樣與第 4 區
//   同源；#285 批次 E E-Q2 甲）。精簡卡不放先發。
// - 第 2／3 區 10/17 整區隱藏（Q3），本元件不留它們的標題或占位。

function GameChip({ card }: { card: OverviewGameCard }) {
  const v = chipView(card);
  return (
    <li className="min-w-0" data-game={`${card.game_key.kind_code}${card.game_key.game_sno}`}>
      <Link href={gameHref(card)} aria-label={v.label}
        className="block h-full min-h-11 rounded-md bg-surface px-2 py-1.5 text-xs leading-5 hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
        <span className="flex items-baseline justify-between gap-1 text-muted">
          <span className="font-bold text-ink">{v.title}</span>
          <span className="tabular-nums">{v.date}</span>
        </span>
        {v.rows.map((r, i) => (
          <span key={i} className={`flex items-baseline justify-between gap-1 ${r.win ? "font-bold text-ink" : "text-muted"}`}>
            <span className="truncate">{r.name}</span>
            <span className={/^\d+$/.test(r.value) ? "font-mono text-sm tabular-nums" : "text-[11px] text-faint"}>{r.value}</span>
          </span>
        ))}
        <span className="block truncate text-[11px] text-faint">{v.foot}</span>
      </Link>
    </li>
  );
}

function ChipGrid({ block }: { block: OverviewSeriesBlock }) {
  const cards = visibleCards(block);
  if (!cards.length) return <p className="text-sm text-muted">{SERIES_NAME[block.kind_code]}{SERIES_COPY.noGames}</p>;
  return (
    <ul aria-label={`${SERIES_NAME[block.kind_code]}場次`} className="grid min-w-0 grid-cols-4 gap-1.5 md:grid-cols-7 md:gap-2">
      {cards.map((c) => <GameChip key={`${c.game_key.kind_code}-${c.game_key.game_sno}`} card={c} />)}
    </ul>
  );
}

/** 當前系列：大比分＋一行狀態＋精簡場次卡。 */
function CurrentSeries({ block }: { block: OverviewSeriesBlock }) {
  const [a, b] = bigScore(block);
  return (
    <div className="min-w-0 space-y-2.5" data-series={block.kind_code}>
      <div className="card px-4 py-3" data-big-score>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-ink">{SERIES_NAME[block.kind_code]}</h3>
          <span className="text-xs text-muted" data-series-sentence>{seriesStatusLine(block)}</span>
        </div>
        {a && b ? (
          <p className="mt-1.5 flex items-center justify-center gap-2 sm:gap-4" aria-label={`系列大比分 ${a.name} ${a.wins ?? "?"} 比 ${b.wins ?? "?"} ${b.name}`}>
            <span className="flex min-w-0 flex-1 items-center justify-end gap-2 text-right text-base font-bold text-ink">
              <span className="truncate">{a.name}</span>
              <TeamLogo code={a.code} name={a.name} size={26} decorative />
            </span>
            <span className="shrink-0 font-mono text-3xl font-bold tabular-nums text-ink">
              {a.wins ?? "?"}<span className="mx-1.5 text-faint">:</span>{b.wins ?? "?"}
            </span>
            <span className="flex min-w-0 flex-1 items-center gap-2 text-base font-bold text-ink">
              <TeamLogo code={b.code} name={b.name} size={26} decorative />
              <span className="truncate">{b.name}</span>
            </span>
          </p>
        ) : null}
      </div>
      <ChipGrid block={block} />
    </div>
  );
}

function NextGame({ overview }: { overview: PlayoffsOverview }) {
  const next = overview.series_section.next_game;
  const missing = nextGameMissingText(overview);
  if (!next) return missing ? <p className="text-sm text-muted">{missing}</p> : null;
  const lead = next.target_status === "live" ? "進行中" : "下一場";
  return (
    <Link href={gameHref(next)} data-next-game
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md bg-surface-2 px-3.5 py-2.5 text-sm hover:bg-band focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className="font-bold text-ink">{lead}：{gameTitle(next)}</span>
        <span className="text-ink">
          {teamLabel(next.away_team_code)}（客）<span className="text-faint"> @ </span>{teamLabel(next.home_team_code)}（主）
        </span>
      </span>
      <span className="text-xs text-muted tabular-nums">
        {dateText(next.game_date)} {startText(next)}・{next.venue ?? "球場本站尚未取得"}
      </span>
      {next.starters?.length ? (
        <span className="basis-full text-xs text-ink" data-next-starters>
          先發：{next.starters.map((s) => `${teamLabel(s.team_code)} ${s.text}`).join("・")}
        </span>
      ) : null}
    </Link>
  );
}

export function SeriesSection({ overview, hidden }: { overview: PlayoffsOverview; hidden?: boolean }) {
  const ss = overview.series_section;
  const notices = seriesNotices(overview);
  return (
    <section id="series" aria-labelledby="series-heading" className="min-w-0 scroll-mt-[70px] space-y-3 md:scroll-mt-[76px]" hidden={hidden || undefined}>
      <h2 id="series-heading" className="sr-only">系列賽表現</h2>
      {notices.map((n) => <Notice key={n} label="待更新">{n}</Notice>)}
      {/* 整區空態只在整年 E／C 都沒有場次時。前一系列（C 頁的挑戰賽）不畫：E 的資料只放 E 頁，切換列就在上方
          （需求方 6221797588；批次 D Q1 不退回，C 未開打或缺場次列時也不畫）。overview 仍帶 `previous`，前端不用。 */}
      {ss.status === "empty" ? (
        <p className="text-sm text-muted">{SERIES_COPY.empty}</p>
      ) : (
        <>
          <CurrentSeries block={ss.current} />
          <NextGame overview={overview} />
          <SeriesSummaryBlock summary={overview.series_summary} />
        </>
      )}
    </section>
  );
}

export default SeriesSection;
