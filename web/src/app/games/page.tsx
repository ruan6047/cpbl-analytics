import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function GamesPage() {
  const { season, items } = await api.gamesRecent();

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
        <h1 className="text-2xl font-bold">{season} 球季 · 賽況</h1>
        <p className="mt-2 text-sm text-white/50">點任一場看逐局比分與逐打席賽況（play-by-play）。</p>
      </header>

      <div className="space-y-6">
        {[...byDate.entries()].map(([d, games]) => (
          <section key={d}>
            <h2 className="mb-2 text-sm font-medium text-white/50">{d}</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {games.map((g) => {
                const awayWin = g.away_score > g.home_score;
                return (
                  <Link
                    key={g.game_sno}
                    href={`/games/${g.game_sno}?kind=${g.kind_code}`}
                    className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 hover:bg-white/5"
                  >
                    <div className="space-y-1">
                      <div className={awayWin ? "font-semibold" : "text-white/70"}>
                        {g.away_team_name}
                      </div>
                      <div className={!awayWin ? "font-semibold" : "text-white/70"}>
                        {g.home_team_name}
                      </div>
                    </div>
                    <div className="space-y-1 text-right font-mono tabular-nums">
                      <div className={awayWin ? "font-semibold text-emerald-400" : "text-white/70"}>
                        {g.away_score}
                      </div>
                      <div className={!awayWin ? "font-semibold text-emerald-400" : "text-white/70"}>
                        {g.home_score}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
