import Link from "next/link";
import { Card, StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";
import { displayTeamName, slotDay, slotGameLabel } from "@/components/postseason-series";
import type { RosterLead } from "@/lib/postseason-announcement";
import type { JourneySeries, JourneySlot, PostseasonJourney, SideTally, SlotStatus } from "@/lib/postseason-journey";
import {
  POSTSEASON_COPY,
  announcementSourceText,
  journeyAsOfText,
  shortDay,
  slotWhen,
  tallyBreakdownText,
  teamShortName,
} from "@/lib/postseason-journey";

// 當季季後總覽（#237）。需求方：「資料太多重複」「可以將挑戰賽跟台灣大賽分開來」。
// 兩個系列各自一個分頁（?ps=E|C，純連結、無用戶端狀態），每頁只有一套：進度 → 晉級關係 → 該系列賽程。
// 資訊責任位置（同一頁只出現一次）：
// - 資訊截至、「官方公告賽程」：標題列。
// - 誰領先、還差幾勝：進度列（大字勝場＋勝場格）。
// - 下一場：賽程清單裡標「下一場」的那一列，不另開一塊。
// - 「如有必要」的意思：清單下方一行；每場只掛標籤。
// - 台灣大賽 G3／G4 球場分支：台灣大賽分頁清單下方一行；場次列只寫「球場依挑戰賽勝隊而定」。
// - 登錄名單來源線索：賽程卡下方一行，各系列各自一版（#237 自 #238 轉入）。
// - 公告來源、無單場連結的原因：頁尾 <details>。

const TONE: Record<SlotStatus, StatusTone> = {
  final: "done", scheduled: "scheduled", announced: "scheduled", result_pending: "warn", not_needed: "done",
};
const isOpen = (s: JourneySlot) => s.status !== "final" && s.status !== "not_needed";
type Key = "E" | "C";
const tabHref = (k: Key) => `/standings?seg=3&ps=${k}`;

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

function ProgressRow({ s, side, seed, nameOf }: { s: JourneySeries; side: SideTally; seed: string; nameOf: (c: string | null) => string }) {
  const won = s.tally.winner != null && side.code === s.tally.winner;
  const note = won ? (s.kind === "E" ? "晉級" : "總冠軍")
    : s.status === "decided" ? ""
    : side.code ? `還差 ${side.remaining} 勝` : "待定";
  const breakdown = tallyBreakdownText(side);
  return (
    <li className="flex items-center gap-3">
      {side.code ? (
        <TeamLogo code={side.code} name={nameOf(side.code)} size={24} decorative />
      ) : (
        <span className="h-6 w-6 shrink-0 rounded-full border border-dashed border-line-strong" aria-hidden />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold text-ink">{side.code ? displayTeamName(nameOf(side.code)) : POSTSEASON_COPY.eWinner}</span>
        <span className="block text-[11px] text-muted">{seed}</span>
        {/* 驗收 2：規則勝與實際場勝分列，讀者不必用大字合計自己減。 */}
        {breakdown && <span className="block text-[11px] font-medium tabular-nums text-ink">{breakdown}<span className="sr-only">，合計</span></span>}
      </span>
      <WinPips t={side} needed={s.winsNeeded} />
      <span className={`w-8 text-right font-[family-name:var(--font-wide)] text-3xl leading-none tabular-nums [font-stretch:80%] ${
        won || side.total > 0 ? "font-black text-ink" : "text-faint"}`}>{side.total}</span>
      <span className={`w-14 text-right text-xs ${won ? "font-bold text-ink" : "text-muted"}`}>{note}</span>
    </li>
  );
}

/** 賽程一列：日期時刻與狀態在上、主客與球場在下。下一場以底色與「下一場」標記；正式場次才可點進單場。 */
function GameRow({ s, isNext, asOf }: { s: JourneySlot; isNext: boolean; asOf: string | null }) {
  const venue = s.venue ?? (s.venueNote?.startsWith("依挑戰賽勝隊") ? "球場依挑戰賽勝隊而定" : s.venueNote);
  const body = (
    <span className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2 gap-y-0.5">
      <span className="font-mono text-sm font-bold leading-6 text-ink">{slotGameLabel(s)}</span>
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-medium tabular-nums text-ink">{slotWhen(s)}</span>
        {isNext && <span className="pm-tag font-bold !text-ink">下一場</span>}
        {s.status !== "announced" && <StatusBadge tone={TONE[s.status]}>{POSTSEASON_COPY.status[s.status]}</StatusBadge>}
        {s.conditional && isOpen(s) && <span className="pm-tag">{POSTSEASON_COPY.conditional}</span>}
      </span>
      <span className="col-start-2 text-[13px] text-ink">
        {s.awayLabel}（客）
        {s.score ? <b className="mx-1 font-mono tabular-nums">{s.score.away}：{s.score.home}</b> : <span className="mx-1 text-faint">對</span>}
        {s.homeLabel}（主）<span className="text-muted">・{venue}</span>
      </span>
      {s.status === "result_pending" && (
        <span className="col-start-2 text-xs text-down">已過預定開賽時間・本站尚無賽果紀錄{asOf ? `（本站賽果紀錄至 ${shortDay(asOf)}）` : ""}</span>
      )}
      {s.changeNote && <span className="col-start-2 text-xs text-down">{s.changeNote}</span>}
    </span>
  );
  // 列在同一張 .card 內以分隔線排列（不畫框、不卡中卡）；下一場沿用日曆「今天」格的 bg-stub 底色標示。
  const tone = isNext ? "bg-stub" : "";
  return s.href ? (
    <li>
      <Link href={s.href} className={`block px-4 py-2.5 text-inherit no-underline transition-colors hover:bg-band ${tone}`}>{body}</Link>
    </li>
  ) : (
    <li data-announced={s.row ? undefined : "true"} className={`px-4 py-2.5 ${tone}`}>{body}</li>
  );
}

function ReserveRow({ date }: { date: string }) {
  return (
    <li className="px-4 py-2 text-xs text-muted">
      <span className="tabular-nums">{slotDay({ date })}</span>　{POSTSEASON_COPY.reserveDay}
    </li>
  );
}

/**
 * 該系列登錄名單的來源線索，賽程卡下方一行。每個系列各自一版（不沿用另一系列的連結）；
 * 只連到外部報導，不呈現球員或人數。沒有線索時寫「本站尚未取得」，不寫成官方未公布。
 */
function RosterLine({ name, leads }: { name: string; leads: RosterLead[] }) {
  return (
    <p data-roster-lead className="text-xs leading-relaxed text-muted">
      <b className="font-bold text-ink">登錄名單</b>：
      {leads.length === 0 ? <>本站尚未取得{name}登錄名單。</> : (
        <>
          {leads.map((l, i) => (
            <span key={l.url}>
              {i > 0 && "、"}
              <a href={l.url} target="_blank" rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center text-accent hover:underline">
                {l.kind}・{l.label} {shortDay(l.publishedOn)}<span className="sr-only">（另開新分頁）</span>
              </a>
            </span>
          ))}
          。
          {/* 連結點擊區 44px 會撐高所在行；說明另起一行，窄螢幕換行時才不會被拉開。 */}
          <span className="block">登錄名單不是先發打線，也不代表球員可出賽。</span>
        </>
      )}
    </p>
  );
}

/** 一個系列的分頁內容：進度 → 晉級關係 → 賽程 → 該系列才有的條件說明。 */
function SeriesView({ journey, k, nameOf, seedOf }: {
  journey: PostseasonJourney; k: Key;
  nameOf: (c: string | null) => string; seedOf: (code: string | null) => string;
}) {
  const { announcement: ann, series } = journey;
  const s = series[k];
  const slots = journey.slots.filter((x) => x.kind === k);
  const eWinner = series.E.status === "decided" ? series.E.tally.winner : null;
  const cSeed = ann.series.C.seededTeam;
  const rows = k === "E"
    ? (s.tally.a.code === ann.series.E.handicapTeam ? [s.tally.a, s.tally.b] : [s.tally.b, s.tally.a])
        .map((side) => ({ side, seed: seedOf(side.code) }))
    : [
        { side: s.tally.a, seed: seedOf(s.tally.a.code) ? `${seedOf(s.tally.a.code)}・保送` : "保送" },
        { side: s.tally.b, seed: s.tally.b.code ? `${ann.series.E.name}勝隊` : "挑戰賽分出勝負後確定" },
      ];
  const reserves = k === "C" ? journey.reserveDays.map((d) => d.date) : [];
  const items: ({ slot: JourneySlot } | { reserve: string })[] = [
    ...slots.map((slot) => ({ slot })),
    ...reserves.map((reserve) => ({ reserve })),
  ].sort((a, b) => ("slot" in a ? a.slot.date : a.reserve).localeCompare("slot" in b ? b.slot.date : b.reserve));
  const branch = slots.find((x) => !x.venue && x.venueNote?.startsWith("依挑戰賽勝隊"));
  const branchSeqs = slots.filter((x) => x.venueNote === branch?.venueNote).map((x) => `G${x.seq}`).join("、");
  const cFirst = journey.slots.find((x) => x.kind === "C");
  const anyAnnounced = slots.some((x) => !x.row);

  return (
    <div className="space-y-3">
      <Card>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 className="text-base font-bold text-ink">{s.name}</h3>
          <span className="text-xs text-muted">{s.bestOf} 戰 {s.winsNeeded} 勝</span>
        </div>
        <ul className="space-y-3">
          {rows.map(({ side, seed }, i) => <ProgressRow key={side.code ?? `tbd-${i}`} s={s} side={side} seed={seed} nameOf={nameOf} />)}
        </ul>
        {k === "E" && (
          <p className="mt-3 text-xs text-muted">
            ● 實際勝場　■ 規則勝：{teamShortName(ann.series.E.handicapTeam)}依規則先得 1 勝，不是實際比賽。
          </p>
        )}
        {s.tally.ties > 0 && (
          <p className="mt-1 text-xs text-down">本站紀錄有 {s.tally.ties} 場比分相同，不計入任何一方勝場（季後賽不應有和局，資料待查）。</p>
        )}
        <p className="mt-3 border-t border-line pt-2 text-sm text-ink">
          {k === "E"
            ? <>{eWinner ? `${teamShortName(eWinner)}晉級台灣大賽` : `先拿 ${s.winsNeeded} 勝晉級台灣大賽`}{cFirst ? `，${slotDay(cFirst)} 起對${teamShortName(cSeed)}` : ""}。</>
            : <>{teamShortName(cSeed)}直接晉級，對手{eWinner ? `為${teamShortName(eWinner)}` : "由季後挑戰賽決定"}；先拿 {s.winsNeeded} 勝奪得總冠軍。</>}
          <Link href={tabHref(k === "E" ? "C" : "E")} scroll={false} className="ml-1 inline-flex min-h-11 items-center text-accent hover:underline">
            {k === "E" ? "看台灣大賽 →" : "看季後挑戰賽 →"}
          </Link>
        </p>
      </Card>

      <Card padding="" className="overflow-hidden">
        <ol aria-label={`${s.name}賽程`} className="divide-y divide-line">
          {items.map((it) => "slot" in it
            ? <GameRow key={it.slot.key} s={it.slot} isNext={journey.next?.key === it.slot.key} asOf={journey.dataAsOf} />
            : <ReserveRow key={it.reserve} date={it.reserve} />)}
        </ol>
      </Card>
      <RosterLine name={s.name} leads={ann.series[k].rosterLeads} />
      <p className="text-xs leading-relaxed text-muted">
        {branch && <><b className="font-bold text-ink">{branchSeqs} 球場</b>：{branch.venueNote}。<br /></>}
        「{POSTSEASON_COPY.conditional}」＝{POSTSEASON_COPY.conditionalNote}。{anyAnnounced && "尚無比分的場次為官方公告安排，本站尚無正式場次紀錄。"}
      </p>
    </div>
  );
}

/** 當季季後總覽：兩系列分頁，一次只讀一套進度與賽程。 */
export function PostseasonOverview({ journey, nameOf, seedOf, active }: {
  journey: PostseasonJourney;
  nameOf: (c: string | null) => string;
  seedOf: (code: string | null) => string;
  /** 網址 `ps`；無效或缺時預設為下一場所在系列。 */
  active?: string | null;
}) {
  const { series, announcement: ann } = journey;
  const fallback: Key = journey.next?.kind ?? (series.E.status === "decided" ? "C" : "E");
  const cur: Key = active === "E" || active === "C" ? active : fallback;
  const hasCRow = journey.slots.some((s) => s.kind === "C" && s.row);
  const range = (k: Key) => {
    const xs = journey.slots.filter((s) => s.kind === k);
    return xs.length ? `${shortDay(xs[0].date)}–${shortDay(xs[xs.length - 1].date)}` : "";
  };
  const month = (journey.next?.date ?? journey.slots[0]?.date ?? "").slice(0, 7);

  return (
    <section aria-labelledby="ps-h">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="ps-h" className="text-xl font-bold tracking-[0.04em] text-ink">季後賽</h2>
          <span className="text-[12.5px] text-muted">官方公告賽程・{journeyAsOfText(journey)}</span>
        </div>
        {month && (
          <Link href={`/games?month=${month}`} className="inline-flex min-h-11 items-center text-sm text-accent hover:underline">
            {Number(month.slice(5))} 月賽程日曆 →
          </Link>
        )}
      </div>

      <nav aria-label="季後系列" className="mb-3 grid grid-cols-2 gap-1.5">
        {(["E", "C"] as const).map((k) => {
          const on = k === cur;
          return (
            <Link key={k} href={tabHref(k)} scroll={false} aria-current={on ? "page" : undefined}
              className={`flex min-h-11 flex-col justify-center rounded-md px-3 py-2 transition-colors ${
                on ? "bg-ink text-paper" : "bg-surface-2 text-ink hover:bg-band"}`}>
              <span className="text-sm font-bold">{series[k].name}</span>
              <span className={`text-[11px] tabular-nums ${on ? "text-paper/80" : "text-muted"}`}>{range(k)}</span>
            </Link>
          );
        })}
      </nav>

      <SeriesView journey={journey} k={cur} nameOf={nameOf} seedOf={seedOf} />

      <details className="mt-3 text-xs text-muted">
        <summary className="inline-flex min-h-11 cursor-pointer items-center text-accent">資料來源與單場連結</summary>
        <p className="pb-1">
          {!hasCRow && <>{POSTSEASON_COPY.noLink}。</>}
          公告來源：{announcementSourceText(ann)}（
          <a href={ann.source.url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">官方公告</a>
          ）。有比分的場次可點進單場紀錄。
        </p>
      </details>
    </section>
  );
}
