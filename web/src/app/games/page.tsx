import Link from "next/link";
import { TeamLogo, StatusBadge, EmptyState, type StatusTone } from "@/components/ui";
import { SectionTitle } from "@/components/postmark";
import { LevelYearNav } from "@/components/level-year-nav";
import { NavBarRow, StickyNavBar } from "@/components/sticky-nav-bar";
import { api, type CalendarGame } from "@/lib/api";
import { hasFinalResult } from "@/lib/live-game";
import { teamFullName } from "@/lib/teams";
import { LiveCalendarGame } from "@/components/live-calendar-game";
import { PostseasonExplainer, slotGameLabel } from "@/components/postseason-series";
import { AnnouncedCompact, AnnouncedMobile } from "@/components/postseason-calendar";
import { announcementFor } from "@/lib/postseason-announcement";
import {
  POSTSEASON_COPY, journeyAsOfText, liveEntryProbes, liveEntryResults, postseasonJourneyFor, slotMayInvolve, withLiveEntries,
  type JourneySlot,
} from "@/lib/postseason-journey";

export const dynamic = "force-dynamic";
export const metadata = { title: "賽程與賽況" };

const WD = ["日", "一", "二", "三", "四", "五", "六"];
// 場次狀態 → 標籤＋語意 tone（完賽=中性／延賽·保留=warn／未開打=scheduled）
// #220：`delay_kind` 是排程歷程的歷史標記，會跟著改期後的場次走。今天（含）以後、`orig_date`
// 早於 `game_date` 的未完賽場＝已排定的補賽，不是延賽（與首頁 `todayCardKind` 同一判準）。
const statusOf = (done: boolean, delay: string | null | undefined,
  g?: { orig_date: string | null; game_date: string }, today?: string): { label: string; tone: StatusTone } =>
  done ? { label: "完賽", tone: "done" }
    : delay && !(g && today && g.orig_date && g.orig_date !== g.game_date && g.game_date >= today)
      ? { label: delay, tone: "warn" }
      : { label: "未開打", tone: "scheduled" };
const makeupNote = (g: { orig_date: string | null; game_date: string; delay_kind: string | null }, done: boolean) =>
  !done && g.delay_kind && g.orig_date && g.orig_date !== g.game_date ? `原定 ${g.orig_date.slice(5).replace("-", "/")}` : null;
// 季後賽層級標記（C=台灣大賽/E=季後挑戰賽/F=二軍季後；例行賽 A/D 無標記）
const POST_LABEL: Record<string, string> = { C: "台灣大賽", E: "季後挑戰賽", F: "二軍季後" };
// 完賽但帶 delay_kind＝在改期後的日子打完（延賽→補賽、保留→續賽）。原本用 ☔ 小標記，
// #218 emoji 處置改文字；不寫成因（全庫沒有延賽理由欄位）。
const MADEUP_LABEL: Record<string, string> = { 延賽: "補賽", 保留: "續賽" };
const pad = (n: number) => String(n).padStart(2, "0");
const ymOf = (d: string) => d.slice(0, 7);
const addMonth = (ym: string, delta: number) => {
  const [y, m] = ym.split("-").map(Number);
  const t = new Date(y, m - 1 + delta, 1);
  return `${t.getFullYear()}-${pad(t.getMonth() + 1)}`;
};

// —— 季後（#237）：公告格元件在 postseason-calendar；這裡只處理正式場次上的公告補充。 ——
const slotOpen = (s: JourneySlot) => s.status !== "final" && s.status !== "not_needed";

/** 正式場次（資料庫列）上的公告補充：開賽時刻與如有必要（資料庫沒有開賽時刻欄位）。 */
const slotExtra = (s: JourneySlot | undefined, done: boolean) =>
  s && !done ? [s.start && `${s.start} 開打`, s.conditional && slotOpen(s) ? POSTSEASON_COPY.conditional : null].filter(Boolean).join("・") : "";

export default async function GamesPage({
  searchParams,
}: {
  searchParams: Promise<{ year?: string; kind?: string; team?: string; month?: string }>;
}) {
  const { year: yearParam, kind: kindParam, team, month: monthParam } = await searchParams;
  const kind = kindParam === "D" ? "D" : "A";
  const { years } = await api.seasons(kind);
  const currentYear = years[0] ?? new Date().getFullYear();
  const selectedYear = yearParam ? Number(yearParam) : currentYear;
  const isCurrent = selectedYear === currentYear && kind === "A";
  // 季後公告（#237）：只在當季一軍且有官方公告時啟用；歷史年份與二軍走原路徑。
  // 啟用時 calendar 與季後摘要都不走跨請求快取，避免同一頁組到不同時間的快照（api.ts journeyGet）。
  const announced = isCurrent && announcementFor(selectedYear) !== null;
  const live = { live: announced };
  const { season, items } = await api.gamesCalendar(isCurrent ? undefined : selectedYear, kind, live);
  const hasDetail = selectedYear >= 2018;

  // 季後摘要取不到時旅程模型只用 calendar 列，不擋日曆本身。
  const postSummary = announced
    ? await api.postseasonSummary(selectedYear, "A", live).catch(() => null)
    : null;
  const baseJourney = isCurrent ? postseasonJourneyFor(selectedYear, postSummary?.series ?? null, items, Date.now()) : null;
  // 單場賽況入口（#237）：資料庫還沒有 E 列的公告格，依官方場號查既有單場狀態（最多 4 支、no-store、
  // 有逾時），身分全部相符才整格連到單場頁；任何失敗都等於沒有入口。有資料庫列的場次不查也不覆蓋。
  const probes = baseJourney && announced ? liveEntryProbes(baseJourney) : [];
  const probeR = await Promise.allSettled(probes.map((p) => api.liveEntryStatus(p.sno, p.kind, baseJourney!.year)));
  const journey = baseJourney && withLiveEntries(baseJourney, liveEntryResults(probes, probeR));
  const slotByRow = new Map<string, JourneySlot>();
  const announcedByDate = new Map<string, JourneySlot[]>();
  for (const s of journey?.slots ?? []) {
    if (s.row) slotByRow.set(`${s.row.kind_code}-${s.row.game_sno}`, s);
    else (announcedByDate.get(s.date) ?? announcedByDate.set(s.date, []).get(s.date)!).push(s);
  }
  const reserveDates = new Set((journey?.reserveDays ?? []).map((d) => d.date));

  // 依日期分組
  const byDate = new Map<string, CalendarGame[]>();
  for (const g of items) (byDate.get(g.game_date) ?? byDate.set(g.game_date, []).get(g.game_date)!).push(g);

  // 可選月份 + 預設月（優先今天所在月，否則最近有比賽的月）；公告月份即使尚無正式場次也可選。
  const monthsAvail = [...new Set([
    ...items.map((g) => ymOf(g.game_date)),
    ...[...announcedByDate.keys(), ...reserveDates].map(ymOf),
  ])].sort();
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const todayYM = todayStr.slice(0, 7);
  const defaultMonth =
    monthsAvail.includes(todayYM) ? todayYM
    : [...monthsAvail].reverse().find((m) => m <= todayYM) ?? monthsAvail[monthsAvail.length - 1] ?? todayYM;
  const month = monthParam && /^\d{4}-\d{2}$/.test(monthParam) ? monthParam : defaultMonth;
  const [my, mm] = month.split("-").map(Number);

  // 球隊篩選 chips
  const names = new Map<string, string>();
  for (const g of items) {
    names.set(g.home_team_code, g.home_team_name);
    names.set(g.away_team_code, g.away_team_name);
  }
  const teamCodes = [...names.keys()].sort();
  const teamOk = (g: CalendarGame) => !team || g.home_team_code === team || g.away_team_code === team;
  const qs = (extra: Record<string, string>) => {
    const p = new URLSearchParams();
    if (kind === "D") p.set("kind", "D");
    if (selectedYear !== currentYear) p.set("year", String(selectedYear));
    if (team) p.set("team", team);
    if (month !== defaultMonth) p.set("month", month);
    for (const [k, v] of Object.entries(extra)) { if (v) p.set(k, v); else p.delete(k); }
    const s = p.toString();
    return s ? `/games?${s}` : "/games";
  };

  // 月曆格：從該月 1 日所在週日 → 到最後一日所在週六
  const first = new Date(my, mm - 1, 1);
  const gridStart = new Date(my, mm - 1, 1 - first.getDay());
  const last = new Date(my, mm, 0);
  const totalCells = Math.ceil((first.getDay() + last.getDate()) / 7) * 7;
  const cells = Array.from({ length: totalCells }, (_, i) => {
    const dt = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
    const key = `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
    const inMonth = dt.getMonth() === mm - 1;
    const ann = inMonth && journey
      ? (announcedByDate.get(key) ?? []).filter((s) => !team || slotMayInvolve(journey, s, team))
      : [];
    return {
      key, day: dt.getDate(), inMonth, games: inMonth ? (byDate.get(key) ?? []).filter(teamOk) : [],
      ann, reserve: inMonth && reserveDates.has(key),
    };
  });
  const monthHasPostseason = !!journey && (journey.slots.some((s) => ymOf(s.date) === month) || [...reserveDates].some((d) => ymOf(d) === month));

  const prevM = addMonth(month, -1);
  const nextM = addMonth(month, 1);
  const canPrev = prevM >= monthsAvail[0];
  const canNext = nextM <= monthsAvail[monthsAvail.length - 1];

  return (
    <div>
      <header className="mb-5">
        <SectionTitle as="h1" date={season} cue={kind === "D" ? "二軍" : "一軍・季後賽"}>賽程與賽況</SectionTitle>
        <p className="-mt-1 text-sm text-muted">
          {hasDetail ? "月曆檢視；點任一場看逐局比分與逐打席賽況（play-by-play）。" : "2018 年前僅逐場結果（無逐局/逐打席）。"}
        </p>
      </header>

      {/* 一體式多軸導覽欄（§4.3 第三例）：隊伍篩選（隊徽 chip 群，§9.3）＋kind/year controls
          收成一列；月份 stepper 屬月曆專屬、保留於下方。窄螢幕 chip 群改橫向捲動。 */}
      <StickyNavBar label="賽況導覽">
        <NavBarRow
          main={
            <div role="group" aria-label="球隊篩選"
              className="flex min-w-0 items-center gap-1.5 overflow-x-auto overscroll-x-contain">
              {/* 選中＝墨色實底紙色字（#218 二級切換）；隊色只在印記，不鋪 chip 底。 */}
              <Link href={qs({ team: "" })} aria-current={!team ? "true" : undefined}
                className={`inline-flex min-h-11 shrink-0 touch-manipulation items-center rounded-md px-2.5 text-xs font-medium transition-colors ${
                  !team ? "bg-ink font-bold text-paper" : "bg-surface-2 text-muted hover:text-ink"}`}>全部</Link>
              {teamCodes.map((code) => {
                const on = team === code;
                return (
                  <Link key={code} href={qs({ team: on ? "" : code })} aria-current={on ? "true" : undefined}
                    className={`inline-flex min-h-11 shrink-0 touch-manipulation items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors ${
                      on ? "bg-ink font-bold text-paper" : "bg-surface-2 text-muted hover:text-ink"}`}>
                    <span className={on ? "rounded-sm bg-surface p-px" : ""}><TeamLogo code={code} name={names.get(code)} size={15} decorative /></span>
                    <span>{teamFullName(names.get(code) ?? "")}</span>
                  </Link>
                );
              })}
            </div>
          }
          controls={<LevelYearNav kind={kind} years={years} selectedYear={selectedYear} base="/games" />}
        />
      </StickyNavBar>

      {/* 月份導覽 */}
      <div className="mb-3 flex items-center justify-center gap-4">
        {canPrev ? (
          <Link href={qs({ month: prevM })} aria-label="上個月" className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-line-strong text-sm text-ink hover:bg-surface-2">←</Link>
        ) : <span aria-hidden="true" className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-faint opacity-50">←</span>}
        <div className="min-w-[8rem] text-center font-[family-name:var(--font-wide)] text-xl font-extrabold [font-stretch:85%]">{my} 年 {mm} 月</div>
        {canNext ? (
          <Link href={qs({ month: nextM })} aria-label="下個月" className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-line-strong text-sm text-ink hover:bg-surface-2">→</Link>
        ) : <span aria-hidden="true" className="inline-flex min-h-11 min-w-11 items-center justify-center text-sm text-faint opacity-50">→</span>}
      </div>

      {/* 季後（#237 驗收 3、5）：「公告安排」與資訊截至在月曆上方說一次，格內不再逐格重複。 */}
      {journey && monthHasPostseason && (
        <p className="mb-3 text-xs leading-relaxed text-muted">
          <b className="font-bold text-ink">季後賽</b>：虛線框為官方公告安排（本站尚無正式場次，
          {journey.slots.some((s) => s.liveEntry) ? "標「單場賽況」者可點入查看單場賽況，整體賽果待更新" : "不提供單場連結"}）・
          點線框為{POSTSEASON_COPY.reserveDay}・「{POSTSEASON_COPY.conditional}」＝{POSTSEASON_COPY.conditionalNote}・{journeyAsOfText(journey)}。
          <Link href="/standings?seg=3" className="ml-1 inline-flex min-h-11 items-center text-accent hover:underline">系列進度與晉級條件 →</Link>
        </p>
      )}

      {/* 月曆 (桌機版) */}
      <div className="hidden md:block overflow-x-auto">
        <div className="min-w-[720px]">
          <div className="grid grid-cols-7 gap-px">
            {WD.map((w, i) => (
              <div key={w} className={`pb-1 text-center text-xs font-bold ${i === 0 || i === 6 ? "text-ink" : "text-muted"}`}>{w}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((c) => (
              <div key={c.key}
                className={`min-h-[92px] rounded-md p-1 ${
                  !c.inMonth ? "bg-transparent" : c.key === todayStr ? "bg-stub" : "bg-surface"}`}>
                {c.inMonth && (
                  <div className="mb-0.5 flex items-baseline justify-between px-0.5">
                    <span className="font-[family-name:var(--font-wide)] text-[15px] font-extrabold leading-none [font-stretch:80%]">{c.day}</span>
                    {c.key === todayStr && <span className="text-[11px] font-bold text-ink">今天</span>}
                  </div>
                )}
                <div className="space-y-1">
                  {c.games.map((g) => {
                    const done = hasFinalResult(g);
                    const awayWin = done && g.away_score > g.home_score;
                    const homeWin = done && g.home_score > g.away_score;
                    // 打完就是「完賽」（延賽/保留性質改以「補賽／續賽」文字保留）；未打才顯示延賽/保留/未開打
                    // 季後正式場次（#237）：已過公告開賽時間仍無賽果 → 賽果待更新。
                    const js = slotByRow.get(`${g.kind_code}-${g.game_sno}`);
                    const st = !done && js?.status === "result_pending"
                      ? { label: POSTSEASON_COPY.status.result_pending, tone: "warn" as StatusTone }
                      : statusOf(done, g.delay_kind, g, todayStr);
                    const info = done
                      ? (g.mvp ? `MVP ${g.mvp}` : g.win_pitcher ? `勝 ${g.win_pitcher}` : "")
                      : (g.away_starter || g.home_starter ? `${g.away_starter ?? "未定"} · ${g.home_starter ?? "未定"}` : (g.venue ?? ""));
                    const extra = slotExtra(js, done);
                    const body = (
                      <>
                        {POST_LABEL[g.kind_code] && <div className="mb-0.5 text-center text-[10px] font-bold leading-none text-ink">{POST_LABEL[g.kind_code]}{js ? ` ${slotGameLabel(js)}` : ""}</div>}
                        {isCurrent && c.key === todayStr ? (
                          <LiveCalendarGame game={g} variant="compact" startsAt={js?.start ? `${js.date}T${js.start}:00+08:00` : null} />
                        ) : <div className="flex items-center justify-between gap-1 leading-none">
                          <span className="flex items-center gap-1">
                            <TeamLogo code={g.away_team_code} name={g.away_team_name} size={20} />
                            {done && <span className={`font-[family-name:var(--font-wide)] text-[17px] tabular-nums [font-stretch:80%] ${awayWin ? "font-black text-ink" : "text-faint"}`}>{g.away_score}</span>}
                          </span>
                          <span className="text-center text-[10px] leading-tight">
                            <StatusBadge tone={st.tone} variant="bare">{st.label}</StatusBadge>
                            {done && g.delay_kind && MADEUP_LABEL[g.delay_kind] && <span className="block text-muted">{MADEUP_LABEL[g.delay_kind]}</span>}
                            {makeupNote(g, done) && <span className="block text-muted">{makeupNote(g, done)}</span>}
                          </span>
                          <span className="flex items-center gap-1">
                            {done && <span className={`font-[family-name:var(--font-wide)] text-[17px] tabular-nums [font-stretch:80%] ${homeWin ? "font-black text-ink" : "text-faint"}`}>{g.home_score}</span>}
                            <TeamLogo code={g.home_team_code} name={g.home_team_name} size={20} />
                          </span>
                        </div>}
                        {extra && <div className="mt-1 truncate text-center text-[10px] font-bold leading-none text-ink">{extra}</div>}
                        {info && <div className="mt-1 truncate text-center text-[10px] leading-none text-muted">{info}</div>}
                      </>
                    );
                    const cls = "block rounded-sm bg-surface-2 px-1.5 py-1";
                    return hasDetail ? (
                      <Link key={`${g.kind_code}-${g.game_sno}`} href={`/games/${g.game_sno}?kind=${g.kind_code}&year=${g.year}`}
                        className={`${cls} transition-colors hover:bg-band`}>{body}</Link>
                    ) : (
                      <div key={`${g.kind_code}-${g.game_sno}`} className={cls}>{body}</div>
                    );
                  })}
                  {c.ann.map((s) => <AnnouncedCompact key={s.key} s={s} />)}
                  {c.reserve && (
                    <div title={POSTSEASON_COPY.reserveDay}
                      className="rounded-sm border border-dotted border-line-strong px-1.5 py-1 text-center text-[10px] leading-tight text-muted">
                      移動補賽日<span className="block">遇延賽才使用</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 行動端：直列式列表 */}
      <div className="block md:hidden space-y-4">
        {cells.filter(c => c.inMonth && (c.games.length > 0 || c.ann.length > 0 || c.reserve)).map(c => (
          <div key={c.key} className={`rounded-md p-3.5 ${c.key === todayStr ? "bg-stub" : "bg-surface"}`}>
            <div className="mb-2.5 flex items-baseline justify-between">
              <span className="font-[family-name:var(--font-wide)] text-lg font-extrabold leading-none [font-stretch:80%]">{c.key.slice(5).replace("-", "/")}<small className="ml-1 font-sans text-xs font-bold text-muted">（{WD[new Date(`${c.key}T00:00:00Z`).getUTCDay()]}）</small></span>
              {c.key === todayStr && <span className="text-xs font-bold text-ink">今天</span>}
            </div>
            <div className="space-y-3">
              {c.games.map((g) => {
                const done = hasFinalResult(g);
                const awayWin = done && g.away_score > g.home_score;
                const homeWin = done && g.home_score > g.away_score;
                const js = slotByRow.get(`${g.kind_code}-${g.game_sno}`);
                const st = !done && js?.status === "result_pending"
                  ? { label: POSTSEASON_COPY.status.result_pending, tone: "warn" as StatusTone }
                  : statusOf(done, g.delay_kind, g, todayStr);
                const info = done
                  ? (g.mvp ? `MVP ${g.mvp}` : g.win_pitcher ? `勝投 ${g.win_pitcher}` : "")
                  : (g.away_starter || g.home_starter ? `先發: ${g.away_starter ?? "未定"} vs ${g.home_starter ?? "未定"}` : (g.venue ?? ""));
                const extra = slotExtra(js, done);
                // 今天格整塊換成即時卡：季後標籤（G 序）與開賽時刻另起一行，與桌面同一格一致。
                // 用 <p> 不用 <div>，避免吃到外層 Link 的 [&>div]:hover。
                const body = isCurrent && c.key === todayStr ? (
                  <>
                    {POST_LABEL[g.kind_code] && (
                      <p className="mb-1.5 flex flex-wrap gap-1.5 leading-none">
                        <span className="pm-tag !text-ink">{POST_LABEL[g.kind_code]}{js ? ` ${slotGameLabel(js)}` : ""}</span>
                        {extra && <span className="pm-tag !text-ink">{extra}</span>}
                      </p>
                    )}
                    <LiveCalendarGame game={g} variant="mobile" startsAt={js?.start ? `${js.date}T${js.start}:00+08:00` : null} />
                  </>
                ) : (
                  <div className="flex flex-col gap-2 rounded-sm bg-surface-2 p-3">
                    <div className="flex items-center justify-between">
                      <span className="flex max-w-fit flex-wrap items-center gap-1.5 leading-none">
                        <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                        {POST_LABEL[g.kind_code] && <span className="pm-tag !text-ink">{POST_LABEL[g.kind_code]}{js ? ` ${slotGameLabel(js)}` : ""}</span>}
                        {extra && <span className="pm-tag !text-ink">{extra}</span>}
                        {done && g.delay_kind && MADEUP_LABEL[g.delay_kind] && <span className="pm-tag">{MADEUP_LABEL[g.delay_kind]}</span>}
                        {makeupNote(g, done) && <span className="pm-tag">{makeupNote(g, done)}</span>}
                      </span>
                      {g.venue && <span className="text-xs text-muted">{g.venue}</span>}
                    </div>
                    <div className="flex items-center justify-between px-1">
                      <span className="flex items-center gap-2 flex-1">
                        <TeamLogo code={g.away_team_code} name={g.away_team_name} size={22} />
                        <span className={`text-sm ${done && awayWin ? "font-bold text-ink" : "text-muted"}`}>{g.away_team_name}</span>
                      </span>
                      {done && <span className={`min-w-[2rem] text-right font-[family-name:var(--font-wide)] text-xl tabular-nums [font-stretch:75%] ${awayWin ? "font-black text-ink" : "text-faint"}`}>{g.away_score}</span>}
                    </div>
                    <div className="flex items-center justify-between px-1">
                      <span className="flex items-center gap-2 flex-1">
                        <TeamLogo code={g.home_team_code} name={g.home_team_name} size={22} />
                        <span className={`text-sm ${done && homeWin ? "font-bold text-ink" : "text-muted"}`}>{g.home_team_name}</span>
                      </span>
                      {done && <span className={`min-w-[2rem] text-right font-[family-name:var(--font-wide)] text-xl tabular-nums [font-stretch:75%] ${homeWin ? "font-black text-ink" : "text-faint"}`}>{g.home_score}</span>}
                    </div>
                    {info && <div className="mt-0.5 text-xs text-muted">{info}</div>}
                  </div>
                );
                return hasDetail ? (
                  <Link key={`${g.kind_code}-${g.game_sno}`} href={`/games/${g.game_sno}?kind=${g.kind_code}&year=${g.year}`} className="block transition-colors [&>div]:hover:bg-band">
                    {body}
                  </Link>
                ) : (
                  <div key={`${g.kind_code}-${g.game_sno}`}>{body}</div>
                );
              })}
              {c.ann.map((s) => <AnnouncedMobile key={s.key} s={s} asOf={journey?.dataAsOf ?? null} />)}
              {c.reserve && <p className="rounded-sm border border-dotted border-line-strong p-3 text-xs text-muted">{POSTSEASON_COPY.reserveDay}</p>}
            </div>
          </div>
        ))}
        {cells.filter(c => c.inMonth && (c.games.length > 0 || c.ann.length > 0 || c.reserve)).length === 0 && (
          <EmptyState>本月無賽程安排。</EmptyState>
        )}
      </div>

      {/* 季後未定場次說明（#237 驗收 6）：G3／G4 與未定場次為何未定、何時確定。 */}
      {journey && monthHasPostseason && (
        <div className="mt-6">
          <PostseasonExplainer journey={journey} showAsOf={false} />
        </div>
      )}

      <p className="mt-4 text-center text-xs text-muted">
        中央為狀態（完賽／延賽／保留／未開打）・粗體＝勝方・完賽附 MVP／勝投，未開打附先發對決；「補賽／續賽」＝改期後打完
      </p>
    </div>
  );
}
