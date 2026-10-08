import Link from "next/link";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import type { SeriesGame, JourneySeries, JourneySlot, PostseasonJourney, SlotStatus } from "@/lib/postseason-journey";
import {
  POSTSEASON_COPY,
  announcementSourceText,
  gameLink,
  gameWinner,
  journeyAsOfText,
  seriesProgressText,
  shortDay,
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

/** 單一場次列：有資料庫列才是連結（實線），公告安排為虛線框、不給連結。 */
export function SlotLine({ s, asOf }: { s: JourneySlot; asOf: string | null }) {
  const open = s.status !== "final" && s.status !== "not_needed";
  const body = (
    <span className="flex flex-col gap-1">
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono text-xs font-bold text-ink">{slotGameLabel(s)}</span>
        <span className="text-sm tabular-nums text-ink">{slotWhen(s)}</span>
        <StatusBadge tone={SLOT_TONE[s.status]}>{POSTSEASON_COPY.status[s.status]}</StatusBadge>
        {s.conditional && open && <span className="pm-tag">{POSTSEASON_COPY.conditional}</span>}
      </span>
      <span className="text-[13px] text-ink">
        {s.awayLabel}（客）
        {s.score ? <b className="mx-1 font-mono tabular-nums">{s.score.away}：{s.score.home}</b> : <span className="mx-1 text-faint">對</span>}
        {s.homeLabel}（主）
        <span className="ml-1.5 text-muted">・{s.venue ?? s.venueNote}</span>
      </span>
      {s.status === "result_pending" && (
        <span className="text-xs text-down">
          已過預定開賽時間・本站尚無賽果紀錄{asOf ? `（本站賽果紀錄至 ${shortDay(asOf)}）` : ""}
        </span>
      )}
      {s.status === "not_needed" && <span className="text-xs text-muted">{POSTSEASON_COPY.notNeededNote}</span>}
      {s.changeNote && <span className="text-xs text-down">{s.changeNote}</span>}
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

/** 驗收 6：台灣大賽 G3／G4 與未定場次的頁面說明。季後總覽與日曆共用。 */
export function PostseasonExplainer({ journey }: { journey: PostseasonJourney }) {
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
      <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[7rem_minmax(0,1fr)]">
        {c3 && (
          <>
            <dt className="font-bold">G3／G4</dt>
            <dd>
              {days(c34)}，{c3.awayLabel}（客）對 {cOpp ? c3.homeLabel : POSTSEASON_COPY.eWinner}（主）。
              <br />
              球場：{cOpp ? `${cOpp}晉級，於${c3.venue ?? "—"}` : (c3.venueNote ?? c3.venue ?? "—")}。
              <br />
              確認條件：挑戰賽分出勝負後確定。目前：
              <b>{cOpp ? `已確定（${cOpp}晉級）` : "待定（挑戰賽尚未分出勝負）"}</b>
            </dd>
          </>
        )}
        <dt className="font-bold">未定事項</dt>
        <dd>
          <ul className="list-disc space-y-0.5 pl-5">
            <li>台灣大賽對手：{cOpp ? `已確定為${cOpp}` : `${POSTSEASON_COPY.eWinner}，挑戰賽分出勝負後確定`}</li>
            <li>G5–G7（{days(c57)}）是否進行：{POSTSEASON_COPY.conditional}，{POSTSEASON_COPY.conditionalNote}</li>
            <li>G5–G7 球場與主客：{POSTSEASON_COPY.unknownVenue}</li>
            {journey.reserveDays.length > 0 && (
              <li>{journey.reserveDays.map((d) => shortDay(d.date)).join("、")}：{POSTSEASON_COPY.reserveDay}</li>
            )}
            {!eDecided && <li>挑戰賽 G3／G4：{POSTSEASON_COPY.conditional}，{POSTSEASON_COPY.conditionalNote}</li>}
          </ul>
        </dd>
      </dl>
      <p className="mt-3 text-xs text-muted">
        {!hasCRow && <>{POSTSEASON_COPY.noLink}。</>}
        公告來源：{announcementSourceText(ann)}（
        <a href={ann.source.url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">官方公告</a>
        ）。{journeyAsOfText(journey)}。
      </p>
    </section>
  );
}

function SeriesNote({ s, rule }: { s: JourneySeries; rule?: string }) {
  return (
    <div className="mt-2 space-y-0.5 text-xs leading-relaxed text-muted">
      <p>
        {s.bestOf} 戰 {s.winsNeeded} 勝：先拿 {s.winsNeeded} 勝{s.kind === "E" ? "晉級台灣大賽" : "奪得總冠軍"}。{rule}
      </p>
      <p className="font-medium text-ink">{seriesProgressText(s)}</p>
      {s.tally.ties > 0 && (
        <p className="text-down">本站紀錄有 {s.tally.ties} 場比分相同，不計入任何一方勝場（季後賽不應有和局，資料待查）。</p>
      )}
    </div>
  );
}

/** 當季季後總覽：公告已定的組合與待定席位分開、讓勝固定、接到下一場與日曆。 */
export function PostseasonOverview({ journey, nameOf, seedOf }: {
  journey: PostseasonJourney;
  nameOf: (c: string | null) => string;
  seedOf: (code: string | null) => string;
}) {
  const { series, announcement: ann, next } = journey;
  const handicap = ann.series.E.handicapTeam;
  const [eA, eB] = ann.series.E.teams;
  // 讓勝隊列在上（與既有 bracket 的「半季冠軍在上」一致）。
  const eTop = eA === handicap ? eA : eB;
  const eBottom = eTop === eA ? eB : eA;
  const cSeed = ann.series.C.seededTeam;
  const eWinner = series.E.tally.winner;
  const nextMonth = (next?.date ?? journey.slots[0]?.date ?? "").slice(0, 7);
  const ruleE = `${teamShortName(handicap)}依規則先勝 1 場（不是實際比賽，已計入大比分，表內「讓」欄）。`;
  const eSlots = journey.slots.filter((s) => s.kind === "E");
  const cSlots = journey.slots.filter((s) => s.kind === "C");

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-xl font-bold tracking-[0.04em] text-ink">季後賽</h2>
        <span className="pm-st">公告賽程・依實際賽果</span>
        <span className="text-[12.5px] text-muted">{journeyAsOfText(journey)}</span>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md bg-surface-2 px-4 py-3 text-sm">
        {next ? (
          <span>
            <b className="mr-1.5">下一場</b>
            {next.kind === "E" ? ann.series.E.name : ann.series.C.name} {slotGameLabel(next)}・{slotWhen(next)}・
            {next.awayLabel}（客）對 {next.homeLabel}（主）・{next.venue ?? next.venueNote}
            <span className="ml-2 align-middle"><StatusBadge tone={SLOT_TONE[next.status]}>{POSTSEASON_COPY.status[next.status]}</StatusBadge></span>
          </span>
        ) : (
          <span>本站紀錄中已無未完成的季後場次。</span>
        )}
        {next?.href && (
          <Link href={next.href} className="inline-flex min-h-11 items-center text-accent hover:underline">單場頁 →</Link>
        )}
        {nextMonth && (
          <Link href={`/games?month=${nextMonth}`} className="inline-flex min-h-11 items-center text-accent hover:underline">
            {Number(nextMonth.slice(5))} 月賽程日曆 →
          </Link>
        )}
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)]">
        <div className="space-y-3">
          <SeriesCard
            title={ann.series.E.name}
            format={`${series.E.bestOf} 戰 ${series.E.winsNeeded} 勝`}
            sideA={{ code: eTop, seed: seedOf(eTop), handicap: eTop === handicap }}
            sideB={{ code: eBottom, seed: seedOf(eBottom), handicap: eBottom === handicap }}
            games={series.E.games}
            needed={series.E.winsNeeded}
            nameOf={nameOf}
            kind="E"
            linkYear={journey.year}
            totalsBeforeGames
          >
            <SeriesNote s={series.E} rule={ruleE} />
          </SeriesCard>
          <ol aria-label={`${ann.series.E.name}賽程`} className="space-y-1.5">
            {eSlots.map((s) => <SlotLine key={s.key} s={s} asOf={journey.dataAsOf} />)}
          </ol>
        </div>
        <div className="hidden items-center justify-center pt-10 text-2xl text-faint lg:flex" aria-hidden>→</div>
        <div className="space-y-3">
          <SeriesCard
            title={ann.series.C.name}
            format={`${series.C.bestOf} 戰 ${series.C.winsNeeded} 勝`}
            sideA={{ code: cSeed, seed: seedOf(cSeed) ? `${seedOf(cSeed)}・保送` : "保送", handicap: false }}
            sideB={{ code: eWinner, seed: eWinner ? `${ann.series.E.name}勝隊` : "挑戰賽分出勝負後確定", handicap: false }}
            games={series.C.games}
            needed={series.C.winsNeeded}
            crownWinner
            nameOf={nameOf}
            kind="C"
            linkYear={journey.year}
            totalsBeforeGames
          >
            <SeriesNote s={series.C} rule="台灣大賽沒有規則讓勝。" />
          </SeriesCard>
          <ol aria-label={`${ann.series.C.name}賽程`} className="space-y-1.5">
            {cSlots.map((s) => <SlotLine key={s.key} s={s} asOf={journey.dataAsOf} />)}
          </ol>
        </div>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-muted">
        實線框＝本站已有正式場次（可點進單場）；虛線框＝公告安排（尚無官方場次編號，不提供單場連結）。
        表內數字為各場得分、勝方加粗。
      </p>
      <div className="mt-4">
        <PostseasonExplainer journey={journey} />
      </div>
    </section>
  );
}
