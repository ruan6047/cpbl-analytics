import Link from "next/link";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import type { SeriesGame, JourneySeries, JourneySlot, PostseasonJourney, SideTally, SlotStatus } from "@/lib/postseason-journey";
import {
  POSTSEASON_COPY,
  announcementSourceText,
  gameLink,
  gameWinner,
  journeyAsOfText,
  seriesProgressText,
  shortDay,
  slotAllUnknown,
  slotVenueText,
  slotWhen,
  tallySeries,
  teamShortName,
} from "@/lib/postseason-journey";

// 季後系列卡與季後總覽（#237）。系列卡由戰績頁拆出，歷史年份、二軍總冠軍與當季共用；
// 大比分一律走 `tallySeries`（與首頁、日曆的旅程模型同一份算法）。

export function displayTeamName(name: string) {
  return name === "統一7-ELEVEn獅" ? "統一獅" : name;
}

// bracket 系列一方：隊伍代碼、種子註記、是否依規則先勝 1 場（讓分）。
export type SeriesSide = { code: string | null; seed: string; handicap: boolean };

// 系列計分卡：兩隊為列、逐場小比分為欄（類似計分表的局數位）；勝方該場得分標色；
// 「讓」為規則先勝 1 場、以一欄呈現並計入大比分。games 空（進行中/未打）時退為種子預覽。
// `linkYear` 有值且逐場帶官方場號時，場次欄頭連到該場單場頁（必帶 kind 與 year）。
// `totalsBeforeGames`：開打前也顯示大比分（當季公告已定讓勝時＝1：0）；預設沿用既有的「—」。
export function SeriesCard({ title, format, sideA, sideB, games = [], needed, crownWinner, nameOf, kind, linkYear, totalsBeforeGames, children }: {
  title: string; format: string; sideA: SeriesSide; sideB: SeriesSide;
  games?: SeriesGame[]; needed: number; crownWinner?: boolean;
  nameOf: (c: string | null) => string;
  kind?: string; linkYear?: number; totalsBeforeGames?: boolean;
  children?: React.ReactNode;
}) {
  const t = tallySeries(sideA, sideB, games, needed);
  const hasGames = games.length > 0;
  const winnerCode = t.winner;
  const anyHandicap = sideA.handicap || sideB.handicap;
  const runsOf = (g: SeriesGame, code: string) => (g.home_code === code ? g.home_score : g.away_score);
  const won = (g: SeriesGame, code: string | null) => code != null && gameWinner(g) === code;

  const scoreRow = (s: SeriesSide, wins: number) => {
    const isWin = winnerCode != null && s.code === winnerCode;
    return (
      <tr>
        <td className="py-1 pr-2">
          <div className="flex items-center gap-2">
            {s.code ? (
              <TeamLogo code={s.code} name={nameOf(s.code)} size={20} decorative />
            ) : (
              <span className="h-5 w-5 shrink-0 rounded-full border border-dashed border-line" aria-hidden />
            )}
            <span className="min-w-0">
              <span className="flex items-center gap-1 text-sm font-medium text-ink">
                <span className="truncate">{s.code ? displayTeamName(nameOf(s.code)) : POSTSEASON_COPY.eWinner}</span>
                {crownWinner && isWin && <span className="pm-tag font-bold !text-ink" title="年度總冠軍">總冠軍</span>}
              </span>
              <span className="block text-[11px] text-muted">{s.seed}</span>
            </span>
          </div>
        </td>
        {anyHandicap && (
          <td className={`px-1 text-center font-mono text-xs tabular-nums ${s.handicap ? "font-bold text-ink" : "text-faint"}`}>
            {s.handicap ? 1 : "·"}
          </td>
        )}
        {games.map((g, i) => (
          <td key={i} className={`px-1 text-center font-mono text-xs tabular-nums ${won(g, s.code) ? "font-black text-ink" : "text-faint"}`}>
            {s.code ? runsOf(g, s.code) : "—"}
          </td>
        ))}
        <td className={`pl-2.5 text-center font-mono text-sm tabular-nums ${isWin ? "font-bold text-ink" : "text-muted"}`}>
          {hasGames || totalsBeforeGames ? wins : "—"}
        </td>
      </tr>
    );
  };

  return (
    <div className="overflow-x-auto rounded-md bg-surface p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-bold text-ink">{title}</span>
        <span className="text-[11px] font-medium text-muted">{format}</span>
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-band text-[11px] text-muted">
            <th />
            {anyHandicap && <th className="px-1 font-medium" title="依規則先勝 1 場">讓</th>}
            {games.map((g) => (
              <th key={g.game_no} className="px-1 font-medium">
                {kind && linkYear && g.game_sno != null ? (
                  <Link href={gameLink(kind, g.game_sno, linkYear)} className="text-accent hover:underline"
                    aria-label={`${title}第 ${g.game_no} 戰單場紀錄`}>{g.game_no}</Link>
                ) : g.game_no}
              </th>
            ))}
            <th className="pl-2.5 font-medium">大比分</th>
          </tr>
        </thead>
        <tbody>
          {scoreRow(sideA, t.a.total)}
          {scoreRow(sideB, t.b.total)}
        </tbody>
      </table>
      {children}
    </div>
  );
}

// —— 當季季後總覽（公告＋正式場次） ——
// 閱讀層級（#237 可讀性修正）：下一場 → 系列進度（大字勝場＋勝場格）→ 場次清單 → 未定說明。
// 「全部是公告安排」這種整體狀態只在清單上方說一次，列上只標例外狀態；來源細節收進 <details>。

const SLOT_TONE: Record<SlotStatus, StatusTone> = {
  final: "done",
  scheduled: "scheduled",
  announced: "scheduled",
  result_pending: "warn",
  not_needed: "done",
};

/** 「G3」：系列內場序（公告場序，不是官方場號）。 */
export function slotGameLabel(s: Pick<JourneySlot, "seq">): string {
  return `G${s.seq}`;
}

/** 單一場次列：有資料庫列才是連結（實線），公告安排為虛線框、不給連結。
 *  公告安排是清單的常態，不逐列掛徽章；只有終場、已排定、賽果待更新、不需進行才標。 */
export function SlotLine({ s, asOf }: { s: JourneySlot; asOf: string | null }) {
  const open = s.status !== "final" && s.status !== "not_needed";
  const body = (
    <span className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2 gap-y-0.5">
      <span className="font-mono text-xs font-bold leading-5 text-ink">{slotGameLabel(s)}</span>
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-medium tabular-nums text-ink">{slotWhen(s)}</span>
        {s.status !== "announced" && <StatusBadge tone={SLOT_TONE[s.status]}>{POSTSEASON_COPY.status[s.status]}</StatusBadge>}
        {s.conditional && open && <span className="pm-tag !text-ink">{POSTSEASON_COPY.conditional}</span>}
      </span>
      <span className="col-start-2 text-[13px] text-ink">
        {slotAllUnknown(s) ? (
          <span className="text-muted">主客、球場：{POSTSEASON_COPY.unknownVenue}</span>
        ) : (
          <>
            {s.awayLabel}（客）
            {s.score ? <b className="mx-1 font-mono tabular-nums">{s.score.away}：{s.score.home}</b> : <span className="mx-1 text-faint">對</span>}
            {s.homeLabel}（主）
            <span className="text-muted">・{slotVenueText(s)}</span>
          </>
        )}
      </span>
      {s.status === "result_pending" && (
        <span className="col-start-2 text-xs text-down">
          已過預定開賽時間・本站尚無賽果紀錄{asOf ? `（本站賽果紀錄至 ${shortDay(asOf)}）` : ""}
        </span>
      )}
      {s.status === "not_needed" && <span className="col-start-2 text-xs text-muted">{POSTSEASON_COPY.notNeededNote}</span>}
      {s.changeNote && <span className="col-start-2 text-xs text-down">{s.changeNote}</span>}
    </span>
  );
  return s.href ? (
    <li>
      <Link href={s.href} className="block rounded-md bg-surface-2 px-3 py-2 text-inherit no-underline transition-colors hover:bg-band">
        {body}
      </Link>
    </li>
  ) : (
    <li data-announced={s.row ? undefined : "true"} className="rounded-md border border-dashed border-line-strong px-3 py-2">{body}</li>
  );
}

/** 驗收 6：台灣大賽 G3／G4 與未定場次的頁面說明（為何未定、何時確定）。季後總覽與日曆共用。
 *  `showAsOf`：所在頁面已在顯眼處標了資訊截至時設 false，避免同頁重複。 */
export function PostseasonExplainer({ journey, showAsOf = true }: { journey: PostseasonJourney; showAsOf?: boolean }) {
  const { series, slots, announcement: ann } = journey;
  const c34 = slots.filter((s) => s.kind === "C" && (s.seq === 3 || s.seq === 4));
  const c57 = slots.filter((s) => s.kind === "C" && s.seq >= 5);
  const eDecided = series.E.status === "decided";
  const eWinner = series.E.tally.winner;
  const cOpp = eDecided && eWinner ? teamShortName(eWinner) : null;
  const c3 = c34[0];
  const hasCRow = slots.some((s) => s.kind === "C" && s.row);
  const days = (xs: JourneySlot[]) => xs.map((s) => slotWhen(s)).join("、");
  return (
    <section aria-labelledby="ps-explain-h" className="rounded-md bg-surface p-4 text-[13px] leading-relaxed text-ink">
      <h3 id="ps-explain-h" className="mb-2 text-sm font-bold">台灣大賽 G3／G4 與未定場次說明</h3>
      <ul className="list-disc space-y-1.5 pl-5">
        {c3 && (
          <li>
            <b>G3／G4</b>（{days(c34)}）：{c3.awayLabel}（客）對 {cOpp ? c3.homeLabel : POSTSEASON_COPY.eWinner}（主）。
            {cOpp ? `球場：${cOpp}晉級，於${c3.venue ?? "—"}。` : `球場${c3.venueNote ?? `：${c3.venue ?? "—"}`}。`}
            目前：<b>{cOpp ? `已確定（${cOpp}晉級）` : "待定，挑戰賽分出勝負後確定"}</b>
          </li>
        )}
        <li>
          <b>G5–G7</b>（{days(c57)}）：{POSTSEASON_COPY.conditional}，{POSTSEASON_COPY.conditionalNote}；主客與球場{POSTSEASON_COPY.unknownVenue}
        </li>
        {!eDecided && (
          <li><b>挑戰賽 G3／G4</b>：{POSTSEASON_COPY.conditional}，{POSTSEASON_COPY.conditionalNote}</li>
        )}
        {journey.reserveDays.length > 0 && (
          <li><b>{journey.reserveDays.map((d) => shortDay(d.date)).join("、")}</b>：{POSTSEASON_COPY.reserveDay}</li>
        )}
      </ul>
      {showAsOf && <p className="mt-3 text-xs text-muted">{journeyAsOfText(journey)}。</p>}
      <details className="mt-1 text-xs text-muted">
        <summary className="inline-flex min-h-11 cursor-pointer items-center text-accent">資料來源與單場連結</summary>
        <p className="pb-1">
          {!hasCRow && <>{POSTSEASON_COPY.noLink}。</>}
          公告來源：{announcementSourceText(ann)}（
          <a href={ann.source.url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">官方公告</a>
          ）。
        </p>
      </details>
    </section>
  );
}

/** 勝場格：需要幾勝就畫幾格；實際勝場為實心圓、規則勝為實心方塊（形狀不同，旁邊另有文字，不只靠顏色）。 */
function WinPips({ t, needed }: { t: SideTally; needed: number }) {
  return (
    <span className="flex shrink-0 items-center gap-1" aria-hidden="true">
      {Array.from({ length: needed }, (_, i) => (
        <span key={i}
          className={`h-2.5 w-2.5 ${i < t.ruleWins ? "rounded-[2px]" : "rounded-full"} ${i < t.total ? "bg-ink" : "border border-line-strong"}`} />
      ))}
    </span>
  );
}

/** 當季系列進度：兩隊大字勝場＋勝場格，下面一行進度句與門檻。 */
function SeriesProgress({ s, rows, nameOf, rule, crownWinner }: {
  s: JourneySeries;
  rows: { side: SideTally; seed: string }[];
  nameOf: (c: string | null) => string;
  rule?: string;
  crownWinner?: boolean;
}) {
  return (
    <div className="rounded-md bg-surface p-3">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-bold text-ink">{s.name}</h3>
        <span className="text-[11px] font-medium text-muted">{s.bestOf} 戰 {s.winsNeeded} 勝</span>
      </div>
      <ul className="space-y-2">
        {rows.map(({ side, seed }, i) => {
          const isWin = s.tally.winner != null && side.code === s.tally.winner;
          return (
            <li key={side.code ?? `tbd-${i}`} className="flex items-center gap-2">
              {side.code ? (
                <TeamLogo code={side.code} name={nameOf(side.code)} size={20} decorative />
              ) : (
                <span className="h-5 w-5 shrink-0 rounded-full border border-dashed border-line-strong" aria-hidden />
              )}
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1 text-sm font-medium text-ink">
                  <span className="truncate">{side.code ? displayTeamName(nameOf(side.code)) : POSTSEASON_COPY.eWinner}</span>
                  {crownWinner && isWin && <span className="pm-tag font-bold !text-ink">總冠軍</span>}
                </span>
                <span className="block text-[11px] text-muted">{seed}</span>
              </span>
              <WinPips t={side} needed={s.winsNeeded} />
              <span className={`w-8 text-right font-[family-name:var(--font-wide)] text-2xl leading-none tabular-nums [font-stretch:80%] ${
                isWin || side.total > 0 ? "font-black text-ink" : "text-faint"}`}>{side.total}</span>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 space-y-0.5 text-xs leading-relaxed">
        <p className="font-medium text-ink">{seriesProgressText(s)}</p>
        <p className="text-muted">
          先拿 {s.winsNeeded} 勝{s.kind === "E" ? "晉級台灣大賽" : "奪得總冠軍"}。{rule}
        </p>
        {s.tally.ties > 0 && (
          <p className="text-down">本站紀錄有 {s.tally.ties} 場比分相同，不計入任何一方勝場（季後賽不應有和局，資料待查）。</p>
        )}
      </div>
    </div>
  );
}

/** 下一場：頁面上最醒目的一塊。「公告安排」只在這裡與清單說明各出現一次。 */
function NextGame({ journey }: { journey: PostseasonJourney }) {
  const { next, announcement: ann } = journey;
  const nextMonth = (next?.date ?? journey.slots[0]?.date ?? "").slice(0, 7);
  return (
    <div className="mb-3 rounded-md bg-surface-2 px-4 py-3">
      {next ? (
        <>
          <p className="text-xs font-bold text-muted">下一場</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-lg font-bold tabular-nums text-ink">{slotWhen(next)}</span>
            <span className="text-sm font-bold text-ink">
              {next.kind === "E" ? ann.series.E.name : ann.series.C.name} {slotGameLabel(next)}
            </span>
            <StatusBadge tone={SLOT_TONE[next.status]}>{POSTSEASON_COPY.status[next.status]}</StatusBadge>
            {next.conditional && <span className="pm-tag !text-ink">{POSTSEASON_COPY.conditional}</span>}
          </p>
          <p className="mt-1 text-sm text-ink">
            {next.awayLabel}（客）對 {next.homeLabel}（主）<span className="text-muted">・{slotVenueText(next)}</span>
          </p>
          {next.status === "result_pending" && <p className="text-xs text-down">已過預定開賽時間・本站尚無賽果紀錄</p>}
        </>
      ) : (
        <p className="text-sm">本站紀錄中已無未完成的季後場次。</p>
      )}
      <div className="flex flex-wrap gap-x-4">
        {next?.href && (
          <Link href={next.href} className="inline-flex min-h-11 items-center text-sm text-accent hover:underline">單場頁 →</Link>
        )}
        {nextMonth && (
          <Link href={`/games?month=${nextMonth}`} className="inline-flex min-h-11 items-center text-sm text-accent hover:underline">
            {Number(nextMonth.slice(5))} 月賽程日曆 →
          </Link>
        )}
      </div>
    </div>
  );
}

/** 當季季後總覽：公告已定的組合與待定席位分開、讓勝固定、接到下一場與日曆。 */
export function PostseasonOverview({ journey, nameOf, seedOf }: {
  journey: PostseasonJourney;
  nameOf: (c: string | null) => string;
  seedOf: (code: string | null) => string;
}) {
  const { series, announcement: ann } = journey;
  const handicap = ann.series.E.handicapTeam;
  const { a: ea, b: eb } = series.E.tally;
  // 讓勝隊列在上（與既有 bracket 的「半季冠軍在上」一致）。
  const eRows = (ea.code === handicap ? [ea, eb] : [eb, ea]).map((side) => ({ side, seed: seedOf(side.code) }));
  const { a: ca, b: cb } = series.C.tally;
  const cRows = [
    { side: ca, seed: seedOf(ca.code) ? `${seedOf(ca.code)}・保送` : "保送" },
    { side: cb, seed: cb.code ? `${ann.series.E.name}勝隊` : "挑戰賽分出勝負後確定" },
  ];
  const ruleE = `${teamShortName(handicap)}依規則先勝 1 場（方塊，不是實際比賽）。`;
  const eSlots = journey.slots.filter((s) => s.kind === "E");
  const cSlots = journey.slots.filter((s) => s.kind === "C");
  const anyAnnounced = journey.slots.some((s) => !s.row);

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-xl font-bold tracking-[0.04em] text-ink">季後賽</h2>
        <span className="text-[12.5px] text-muted">{journeyAsOfText(journey)}</span>
      </div>

      <NextGame journey={journey} />

      {anyAnnounced && (
        <p className="mb-3 text-xs leading-relaxed text-muted">
          以下場次中，虛線框為官方公告安排（本站尚無正式場次，不提供單場連結）；實線框可點進單場。
        </p>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <SeriesProgress s={series.E} rows={eRows} nameOf={nameOf} rule={ruleE} />
          <ol aria-label={`${ann.series.E.name}賽程`} className="space-y-1.5">
            {eSlots.map((s) => <SlotLine key={s.key} s={s} asOf={journey.dataAsOf} />)}
          </ol>
        </div>
        <div className="space-y-2">
          <SeriesProgress s={series.C} rows={cRows} nameOf={nameOf} crownWinner />
          <ol aria-label={`${ann.series.C.name}賽程`} className="space-y-1.5">
            {cSlots.map((s) => <SlotLine key={s.key} s={s} asOf={journey.dataAsOf} />)}
          </ol>
        </div>
      </div>

      <div className="mt-4">
        <PostseasonExplainer journey={journey} showAsOf={false} />
      </div>
    </section>
  );
}
