import Link from "next/link";
import { TeamLogo, StatusBadge, EmptyState, type StatusTone } from "@/components/ui";
import { LevelYearNav } from "@/components/level-year-nav";
import { NavBarRow, StickyNavBar } from "@/components/sticky-nav-bar";
import { api, type CalendarGame } from "@/lib/api";
import { contrastText, teamColor, teamFullName } from "@/lib/teams";

export const dynamic = "force-dynamic";

const WD = ["日", "一", "二", "三", "四", "五", "六"];
// 場次狀態 → 標籤＋語意 tone（完賽=中性／延賽·保留=warn／未開打=scheduled）
const statusOf = (done: boolean, delay: string | null | undefined): { label: string; tone: StatusTone } =>
  done ? { label: "完賽", tone: "done" }
    : delay ? { label: delay, tone: "warn" }
      : { label: "未開打", tone: "scheduled" };
// 季後賽層級標記（C=台灣大賽/E=季後挑戰賽/F=二軍季後；例行賽 A/D 無標記）
const POST_LABEL: Record<string, string> = { C: "台灣大賽", E: "季後挑戰賽", F: "二軍季後" };
const pad = (n: number) => String(n).padStart(2, "0");
const ymOf = (d: string) => d.slice(0, 7);
const addMonth = (ym: string, delta: number) => {
  const [y, m] = ym.split("-").map(Number);
  const t = new Date(y, m - 1 + delta, 1);
  return `${t.getFullYear()}-${pad(t.getMonth() + 1)}`;
};

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
  const { season, items } = await api.gamesCalendar(isCurrent ? undefined : selectedYear, kind);
  const hasDetail = selectedYear >= 2018;

  // 依日期分組
  const byDate = new Map<string, CalendarGame[]>();
  for (const g of items) (byDate.get(g.game_date) ?? byDate.set(g.game_date, []).get(g.game_date)!).push(g);

  // 可選月份 + 預設月（優先今天所在月，否則最近有比賽的月）
  const monthsAvail = [...new Set(items.map((g) => ymOf(g.game_date)))].sort();
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
    return { key, day: dt.getDate(), inMonth, games: inMonth ? (byDate.get(key) ?? []).filter(teamOk) : [] };
  });

  const prevM = addMonth(month, -1);
  const nextM = addMonth(month, 1);
  const canPrev = prevM >= monthsAvail[0];
  const canNext = nextM <= monthsAvail[monthsAvail.length - 1];

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">{season} 球季 · {kind === "D" ? "二軍賽況" : "賽況"}</h1>
        <p className="mt-1.5 text-sm text-muted">
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
              {/* 圓角走 control canonical rounded-lg（§2.5；rounded-full 不像可按，UI 審 r2） */}
              <Link href={qs({ team: "" })} aria-current={!team ? "true" : undefined}
                className={`inline-flex min-h-11 shrink-0 touch-manipulation items-center rounded-lg px-2.5 text-xs font-medium transition ${
                  !team ? "bg-ink text-paper" : "bg-surface-2 text-muted hover:text-ink"}`}>全部</Link>
              {teamCodes.map((code) => {
                const on = team === code;
                return (
                  <Link key={code} href={qs({ team: on ? "" : code })} aria-current={on ? "true" : undefined}
                    className={`inline-flex min-h-11 shrink-0 touch-manipulation items-center gap-1 rounded-lg px-2 text-xs font-medium transition ${on ? "" : "bg-surface-2"}`}
                    style={on ? { background: teamColor(code), color: contrastText(teamColor(code)) } : undefined}>
                    <TeamLogo code={code} name={names.get(code)} size={15} />
                    <span className={on ? "" : "text-muted"}>{teamFullName(names.get(code) ?? "")}</span>
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
          <Link href={qs({ month: prevM })} className="rounded-lg border border-line px-2.5 py-1 text-sm text-muted hover:bg-surface-2">←</Link>
        ) : <span className="px-2.5 py-1 text-sm text-faint">←</span>}
        <div className="min-w-[8rem] text-center text-lg font-semibold">{my} 年 {mm} 月</div>
        {canNext ? (
          <Link href={qs({ month: nextM })} className="rounded-lg border border-line px-2.5 py-1 text-sm text-muted hover:bg-surface-2">→</Link>
        ) : <span className="px-2.5 py-1 text-sm text-faint">→</span>}
      </div>

      {/* 月曆 (桌機版) */}
      <div className="hidden md:block overflow-x-auto">
        <div className="min-w-[720px]">
          <div className="grid grid-cols-7 gap-px">
            {WD.map((w, i) => (
              <div key={w} className={`pb-1 text-center text-xs font-medium ${i === 0 || i === 6 ? "text-accent/70" : "text-faint"}`}>{w}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((c) => (
              <div key={c.key}
                className={`min-h-[92px] rounded-lg border p-1 ${
                  c.inMonth ? "border-line bg-surface" : "border-transparent bg-transparent"}`}>
                {c.inMonth && (
                  <div className={`mb-0.5 px-0.5 text-[11px] ${c.key === todayStr
                    ? "inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 font-semibold text-white"
                    : "text-faint"}`}>{c.day}</div>
                )}
                <div className="space-y-1">
                  {c.games.map((g) => {
                    const done = g.away_score + g.home_score > 0;
                    const awayWin = done && g.away_score > g.home_score;
                    const homeWin = done && g.home_score > g.away_score;
                    // 打完就是「完賽」（延賽/保留性質改以 ☔ 小標記保留）；未打才顯示延賽/保留/未開打
                    const st = statusOf(done, g.delay_kind);
                    const info = done
                      ? (g.mvp ? `⭐ ${g.mvp}` : g.win_pitcher ? `勝 ${g.win_pitcher}` : "")
                      : (g.away_starter || g.home_starter ? `${g.away_starter ?? "未定"} · ${g.home_starter ?? "未定"}` : (g.venue ?? ""));
                    const body = (
                      <>
                        {POST_LABEL[g.kind_code] && <div className="mb-0.5 text-center text-[8px] font-bold leading-none text-accent">{POST_LABEL[g.kind_code]}</div>}
                        <div className="flex items-center justify-between gap-1 leading-none">
                          <span className="flex items-center gap-1">
                            <TeamLogo code={g.away_team_code} name={g.away_team_name} size={20} />
                            {done && <span className={`text-base tabular-nums ${awayWin ? "font-bold text-accent" : "text-muted"}`}>{g.away_score}</span>}
                          </span>
                          <span className="text-[9px] leading-tight">
                            <StatusBadge tone={st.tone} variant="bare">{st.label}</StatusBadge>
                            {done && g.delay_kind && <span title={`因雨${g.delay_kind}`} className="text-faint"> ☔</span>}
                          </span>
                          <span className="flex items-center gap-1">
                            {done && <span className={`text-base tabular-nums ${homeWin ? "font-bold text-accent" : "text-muted"}`}>{g.home_score}</span>}
                            <TeamLogo code={g.home_team_code} name={g.home_team_name} size={20} />
                          </span>
                        </div>
                        {info && <div className="mt-1 truncate text-center text-[9px] leading-none text-faint">{info}</div>}
                      </>
                    );
                    const cls = "block rounded-md bg-surface-2/50 px-1.5 py-1";
                    return hasDetail ? (
                      <Link key={`${g.kind_code}-${g.game_sno}`} href={`/games/${g.game_sno}?kind=${g.kind_code}&year=${g.year}`}
                        className={`${cls} transition hover:bg-surface-2`}>{body}</Link>
                    ) : (
                      <div key={`${g.kind_code}-${g.game_sno}`} className={cls}>{body}</div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 行動端：直列式列表 */}
      <div className="block md:hidden space-y-4">
        {cells.filter(c => c.inMonth && c.games.length > 0).map(c => (
          <div key={c.key} className="card p-4">
            <div className={`text-xs font-semibold mb-2.5 pb-1 border-b border-line flex items-center justify-between ${c.key === todayStr ? "text-accent" : "text-muted"}`}>
              <span>{c.key}</span>
              {c.key === todayStr && <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold text-accent">今天</span>}
            </div>
            <div className="space-y-3">
              {c.games.map((g) => {
                const done = g.away_score + g.home_score > 0;
                const awayWin = done && g.away_score > g.home_score;
                const homeWin = done && g.home_score > g.away_score;
                const st = statusOf(done, g.delay_kind);
                const info = done
                  ? (g.mvp ? `⭐ MVP: ${g.mvp}` : g.win_pitcher ? `勝投: ${g.win_pitcher}` : "")
                  : (g.away_starter || g.home_starter ? `先發: ${g.away_starter ?? "未定"} vs ${g.home_starter ?? "未定"}` : (g.venue ?? ""));
                const body = (
                  <div className="flex flex-col gap-2 p-3 bg-surface-2/30 rounded-lg">
                    <div className="flex items-center justify-between">
                      <span className="flex max-w-fit items-center gap-1.5 leading-none">
                        <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                        {POST_LABEL[g.kind_code] && <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-bold text-accent">{POST_LABEL[g.kind_code]}</span>}
                        {done && g.delay_kind && <span title={`因雨${g.delay_kind}`} className="text-[10px] text-faint"> ☔</span>}
                      </span>
                      {g.venue && <span className="text-[10px] text-faint">{g.venue}</span>}
                    </div>
                    <div className="flex items-center justify-between px-1">
                      <span className="flex items-center gap-2 flex-1">
                        <TeamLogo code={g.away_team_code} name={g.away_team_name} size={22} />
                        <span className={`text-sm ${done && awayWin ? "font-bold text-ink" : "text-muted"}`}>{g.away_team_name}</span>
                      </span>
                      {done && <span className={`text-lg font-mono tabular-nums min-w-[2rem] text-right ${awayWin ? "font-bold text-accent" : "text-muted"}`}>{g.away_score}</span>}
                    </div>
                    <div className="flex items-center justify-between px-1">
                      <span className="flex items-center gap-2 flex-1">
                        <TeamLogo code={g.home_team_code} name={g.home_team_name} size={22} />
                        <span className={`text-sm ${done && homeWin ? "font-bold text-ink" : "text-muted"}`}>{g.home_team_name}</span>
                      </span>
                      {done && <span className={`text-lg font-mono tabular-nums min-w-[2rem] text-right ${homeWin ? "font-bold text-accent" : "text-muted"}`}>{g.home_score}</span>}
                    </div>
                    {info && <div className="text-[10px] text-faint border-t border-line/40 pt-1.5 mt-0.5">{info}</div>}
                  </div>
                );
                return hasDetail ? (
                  <Link key={`${g.kind_code}-${g.game_sno}`} href={`/games/${g.game_sno}?kind=${g.kind_code}&year=${g.year}`} className="block transition hover:opacity-80">
                    {body}
                  </Link>
                ) : (
                  <div key={`${g.kind_code}-${g.game_sno}`}>{body}</div>
                );
              })}
            </div>
          </div>
        ))}
        {cells.filter(c => c.inMonth && c.games.length > 0).length === 0 && (
          <EmptyState>本月無賽程安排。</EmptyState>
        )}
      </div>

      <p className="mt-4 text-center text-xs text-faint">
        中央為狀態（完賽／延賽／保留／未開打）· 粗體＝勝方 · 完賽附 ⭐MVP／勝投，未開打附先發對決
      </p>
    </div>
  );
}
