import Link from "next/link";
import { TeamLogo } from "@/components/ui";
import type { SeriesGame, JourneySlot, PostseasonJourney } from "@/lib/postseason-journey";
import {
  POSTSEASON_COPY,
  announcementSourceText,
  gameLink,
  gameWinner,
  journeyAsOfText,
  slotWhen,
  tallySeries,
  teamShortName,
} from "@/lib/postseason-journey";

// 季後系列卡與台灣大賽未定說明（#237）。系列卡由戰績頁拆出，歷史年份與二軍總冠軍共用；
// 當季季後總覽在 postseason-overview。大比分一律走 `tallySeries`（與首頁、日曆的旅程模型同一份算法）。

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

/** 「G3」：系列內場序（公告場序，不是官方場號）。 */
export function slotGameLabel(s: Pick<JourneySlot, "seq">): string {
  return `G${s.seq}`;
}

/** 驗收 6：台灣大賽的未定事項——只寫場次列寫不下的「為何未定、何時確定」，不重抄賽程。
 *  季後總覽的台灣大賽分頁與日曆共用；挑戰賽分出勝負後自動改寫為已確定。
 *  `showAsOf`：所在頁面已在顯眼處標了資訊截至時設 false，避免同頁重複。 */
export function PostseasonExplainer({ journey, showAsOf = true }: { journey: PostseasonJourney; showAsOf?: boolean }) {
  const { series, slots, announcement: ann } = journey;
  const eWinner = series.E.status === "decided" ? series.E.tally.winner : null;
  const opp = eWinner ? teamShortName(eWinner) : null;
  const branch = slots.filter((s) => s.kind === "C" && !s.venue && s.venueNote);
  const decidedBranch = slots.filter((s) => s.kind === "C" && (s.seq === 3 || s.seq === 4));
  const hasCRow = slots.some((s) => s.kind === "C" && s.row);
  const seqs = (xs: JourneySlot[]) => xs.map((s) => `G${s.seq}`).join("、");
  return (
    <section aria-labelledby="ps-explain-h" className="rounded-md bg-surface p-4 text-[13px] leading-relaxed text-ink">
      <h3 id="ps-explain-h" className="mb-2 text-sm font-bold">台灣大賽未定事項</h3>
      <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[6.5rem_minmax(0,1fr)]">
        <dt className="font-bold">對手</dt>
        <dd>{opp ? `已確定：${opp}（挑戰賽勝隊）` : `${POSTSEASON_COPY.eWinner}，挑戰賽分出勝負後確定`}</dd>
        <dt className="font-bold">{seqs(branch.length ? branch : decidedBranch)} 球場</dt>
        <dd>
          {branch.length
            ? branch[0].venueNote
            : `${decidedBranch[0]?.venue ?? "—"}（${opp ?? "挑戰賽勝隊"}主場）`}
        </dd>
      </dl>
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

/** 日期（含星期、不含時刻）：場次格用。 */
export function slotDay(s: Pick<JourneySlot, "date">): string {
  return slotWhen({ date: s.date, start: null });
}
