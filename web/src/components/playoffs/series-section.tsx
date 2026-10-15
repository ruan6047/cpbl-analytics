import Link from "next/link";
import { SectionTitle } from "@/components/postmark";
import { Notice, StatusBadge, TeamLogo } from "@/components/ui";
import type { OverviewGameCard, OverviewSeriesBlock, PlayoffsOverview } from "@/lib/playoffs-types";
import {
  SERIES_COPY,
  SERIES_NAME,
  cardStatus,
  dateText,
  gameHref,
  gameTitle,
  mvpText,
  nextGameMissingText,
  scoreLine,
  seriesNotices,
  seriesSentence,
  startText,
  teamLabel,
  visibleCards,
} from "@/lib/playoffs-series-view";

// `/playoffs` 第 1 區「系列賽表現」（#285 S04）。無 hooks、純排字：SSR 首屏與 client 輪詢共用同一元件，
// 輪詢只換 props，⛔ 自行捲動或移焦點。
//
// 層級（PLAN r4 §9）：前一系列總結 → 當前系列 → 下一場預告。
// - 場次卡橫向清單，區內可橫捲，頁面不水平溢出（min-w-0＋overflow-x-auto）。
// - 預告只放日期、開賽時刻＋來源、球場、主客；⛔ 先發投手（需求方 D7）。
// - 第 2／3 區 10/17 整區隱藏（Q3），本元件不留它們的標題或占位。

function GameCard({ card }: { card: OverviewGameCard }) {
  const status = cardStatus(card);
  const score = scoreLine(card);
  const mvp = mvpText(card);
  return (
    <li className="w-[13.5rem] shrink-0 snap-start rounded-md bg-surface p-3" data-game={`${card.game_key.kind_code}${card.game_key.game_sno}`}>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-bold text-ink">{gameTitle(card)}</span>
        <StatusBadge tone={status.tone}>{status.text}</StatusBadge>
      </div>
      <div className="mt-1 text-xs text-muted">
        {dateText(card.game_date)}・{card.venue ?? "球場本站尚未取得"}
        {card.conditional && !card.completed ? `・${SERIES_COPY.conditional}` : ""}
      </div>
      {score ? (
        <dl className="mt-2 space-y-1 text-sm">
          {([["客", card.away_team_code, score.away, score.awayScore, score.homeScore], ["主", card.home_team_code, score.home, score.homeScore, score.awayScore]] as const).map(([side, code, name, mine, theirs]) => (
            <div key={side} className="flex items-center justify-between gap-2">
              <dt className="relative flex min-w-0 items-center gap-1.5">
                <TeamLogo code={code} name={name} size={18} decorative />
                <span className={`truncate ${mine > theirs ? "font-bold text-ink" : "text-faint"}`}>{name}</span>
                <span className="sr-only">（{side}）</span>
              </dt>
              <dd className={`font-mono text-base tabular-nums ${mine > theirs ? "font-bold text-ink" : "text-faint"}`}>{mine}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 text-sm text-ink">
          {teamLabel(card.away_team_code)} <span className="text-faint">@</span> {teamLabel(card.home_team_code)}
        </p>
      )}
      {mvp && <p className="mt-2 text-xs text-muted">{mvp}</p>}
      <Link href={gameHref(card)} className="mt-2 inline-flex min-h-11 items-center text-sm text-accent underline-offset-2 hover:underline">
        {card.completed ? "單場賽況 →" : "單場頁 →"}
      </Link>
    </li>
  );
}

// relative：卡內的 sr-only（absolute）以清單為包含塊才會被橫捲裁切；少了它，捲出畫面的卡會把
// 整頁撐寬（375 寬實測 scrollWidth 698）。scroll-px-1 讓 snap 對齊內距，不在首屏偏移 4px。
function CardList({ block, label }: { block: OverviewSeriesBlock; label: string }) {
  const cards = visibleCards(block);
  return (
    <ul aria-label={label} className="relative -mx-1 flex min-w-0 snap-x scroll-px-1 gap-2 overflow-x-auto px-1 pb-2">
      {cards.map((c) => <GameCard key={`${c.game_key.kind_code}-${c.game_key.game_sno}`} card={c} />)}
    </ul>
  );
}

function SeriesBlockView({ block, heading }: { block: OverviewSeriesBlock; heading: string }) {
  return (
    <div className="min-w-0 space-y-2" data-series={block.kind_code}>
      <SectionTitle as="h3" size="sm">{heading}</SectionTitle>
      <p className="text-sm text-ink" data-series-sentence>{seriesSentence(block)}</p>
      <CardList block={block} label={`${SERIES_NAME[block.kind_code]}場次`} />
    </div>
  );
}

function NextGame({ overview }: { overview: PlayoffsOverview }) {
  const next = overview.series_section.next_game;
  const missing = nextGameMissingText(overview);
  if (!next) return missing ? <p className="text-sm text-muted">{missing}</p> : null;
  return (
    <div className="rounded-md bg-surface-2 p-3" data-next-game>
      {/* 目標場進行中時不叫「下一場」（狀態由 S02 target_status 給，不自行推導） */}
      <SectionTitle as="h3" size="sm">{next.target_status === "live" ? "進行中" : "下一場"}：{gameTitle(next)}</SectionTitle>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">日期</dt>
        <dd className="text-ink">{dateText(next.game_date)}</dd>
        <dt className="text-muted">開賽</dt>
        <dd className="text-ink">{startText(next, overview)}</dd>
        <dt className="text-muted">球場</dt>
        <dd className="text-ink">{next.venue ?? "本站尚未取得"}</dd>
        <dt className="text-muted">對戰</dt>
        <dd className="flex flex-wrap items-center gap-x-1.5 text-ink">
          <span>{teamLabel(next.away_team_code)}（客）</span>
          <span className="text-faint">@</span>
          <span>{teamLabel(next.home_team_code)}（主）</span>
        </dd>
      </dl>
      <Link href={gameHref(next)} className="mt-1 inline-flex min-h-11 items-center text-sm text-accent underline-offset-2 hover:underline">
        單場頁 →
      </Link>
    </div>
  );
}

export function SeriesSection({ overview }: { overview: PlayoffsOverview }) {
  const ss = overview.series_section;
  const notices = seriesNotices(overview);
  return (
    <section id="series" aria-labelledby="series-heading" className="min-w-0 scroll-mt-[70px] space-y-4 md:scroll-mt-[76px]">
      <SectionTitle as="h2" id="series-heading">系列賽表現</SectionTitle>
      {notices.map((n) => <Notice key={n} label="待更新">{n}</Notice>)}
      {ss.status === "empty" ? (
        <p className="text-sm text-muted">{SERIES_COPY.empty}</p>
      ) : (
        <>
          {ss.previous && <SeriesBlockView block={ss.previous} heading={`${SERIES_NAME[ss.previous.kind_code]}結果`} />}
          <SeriesBlockView block={ss.current} heading={SERIES_NAME[ss.current.kind_code]} />
          <NextGame overview={overview} />
        </>
      )}
    </section>
  );
}

export default SeriesSection;
