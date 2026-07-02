import Link from "next/link";
import { TeamLogo } from "@/components/ui";
import { YearSelect } from "@/components/year-select";
import { api } from "@/lib/api";
import { teamFullName } from "@/lib/teams";

export const dynamic = "force-dynamic";

const LEVELS = [
  { v: "A", label: "一軍" },
  { v: "D", label: "二軍" },
];

export default async function GamesPage({ searchParams }: { searchParams: Promise<{ year?: string; kind?: string }> }) {
  const { year: yearParam, kind: kindParam } = await searchParams;
  const kind = kindParam === "D" ? "D" : "A";
  const { years } = await api.seasons(kind);
  const currentYear = years[0] ?? new Date().getFullYear();
  const selectedYear = yearParam ? Number(yearParam) : currentYear;
  const isCurrent = selectedYear === currentYear && kind === "A";
  const { season, items } = await api.gamesRecent(600, isCurrent ? undefined : selectedYear, kind);
  // 2018 前無逐打席/逐局，賽況頁無內容 → 不連結
  const hasDetail = selectedYear >= 2018;

  // 依日期分組
  const byDate = new Map<string, typeof items>();
  for (const g of items) {
    const arr = byDate.get(g.game_date) ?? [];
    arr.push(g);
    byDate.set(g.game_date, arr);
  }

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · {kind === "D" ? "二軍賽況" : "賽況"}</h1>
        <p className="mt-2 text-sm text-muted">
          {hasDetail ? "點任一場看逐局比分與逐打席賽況（play-by-play）。" : "2018 年前僅逐場結果（無逐局/逐打席）。"}
        </p>
      </header>

      <nav className="mb-4 flex flex-wrap items-center gap-2">
        {LEVELS.map((lv) => (
          <Link key={lv.v} href={lv.v === "A" ? "/games" : "/games?kind=D"}
            className={`rounded-full px-3 py-1 text-sm font-medium transition ${
              (lv.v === "D") === (kind === "D") ? "bg-ink text-white" : "bg-surface-2 text-muted hover:bg-surface-2"}`}>
            {lv.label}
          </Link>
        ))}
        <span className="mx-1 h-4 w-px bg-line" />
        <YearSelect years={years} value={selectedYear} kind={kind} basePath="/games" />
      </nav>

      <div className="space-y-6">
        {[...byDate.entries()].map(([d, games]) => (
          <section key={d}>
            <h2 className="mb-2 text-sm font-medium text-muted">{d}</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {games.map((g) => {
                const awayWin = g.away_score > g.home_score;
                const inner = (
                  <>
                    <div className="space-y-1.5">
                      <div className={`flex items-center gap-2 ${awayWin ? "font-semibold" : "text-muted"}`}>
                        <TeamLogo code={g.away_team_code} name={g.away_team_name} size={18} />{teamFullName(g.away_team_name)}
                      </div>
                      <div className={`flex items-center gap-2 ${!awayWin ? "font-semibold" : "text-muted"}`}>
                        <TeamLogo code={g.home_team_code} name={g.home_team_name} size={18} />{teamFullName(g.home_team_name)}
                      </div>
                    </div>
                    <div className="space-y-1 text-right font-mono tabular-nums">
                      <div className={awayWin ? "font-semibold text-accent" : "text-muted"}>{g.away_score}</div>
                      <div className={!awayWin ? "font-semibold text-accent" : "text-muted"}>{g.home_score}</div>
                    </div>
                  </>
                );
                const cls = "flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-3";
                return hasDetail ? (
                  <Link key={g.game_sno} href={`/games/${g.game_sno}?kind=${g.kind_code}&year=${g.year}`}
                    className={`${cls} hover:bg-surface-2`}>{inner}</Link>
                ) : (
                  <div key={g.game_sno} className={cls}>{inner}</div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
