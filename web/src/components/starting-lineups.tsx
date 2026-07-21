import { FieldDiagram } from "@/components/field-diagram";
import { PlayerLink } from "@/components/ui";
import { startingLineup } from "@/lib/game-lineup";
import type { StatRow } from "@/lib/client";
import { teamColor } from "@/lib/teams";

export function StartingLineups({ game, log, pitching }: { game: StatRow; log: StatRow[]; pitching: StatRow[] }) {
  const sides = [
    { side: "away" as const, name: String(game.away_team_name ?? "客隊"), code: String(game.away_team_code ?? "") },
    { side: "home" as const, name: String(game.home_team_name ?? "主隊"), code: String(game.home_team_code ?? "") },
  ];
  const lineups = sides.map((team) => ({ ...team, lineup: startingLineup(team.side, log, game, pitching) }));
  if (!lineups.some(({ lineup }) => lineup.available)) return null;

  return (
    <section className="grid gap-4 lg:grid-cols-2" aria-label="先發打序與守備位置">
      {lineups.map(({ side, name, code, lineup }) => (
        <article key={side} className="overflow-hidden rounded-xl border border-line bg-surface">
          <header className="flex items-center gap-2 border-b border-line px-4 py-3">
            <i aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: teamColor(code) }} />
            <h2 className="text-sm font-semibold text-ink">{name}・先發打序</h2>
            <span className="text-[11px] text-faint">依首輪打席重建</span>
          </header>
          {!lineup.available ? (
            <p className="px-4 py-6 text-center text-sm text-muted">先發名單尚未完整，暫不推定。</p>
          ) : (
            <div className="p-3">
              <FieldDiagram cells={lineup.cells} caption={`${name}先發守備位置`}
                className="mx-auto w-full max-w-[360px]" />
              {lineup.designatedHitter && (
                <p className="mx-auto mt-1 flex max-w-[360px] items-center justify-between rounded-md bg-surface-2 px-3 py-2 text-xs">
                  <span className="font-mono font-semibold text-muted">DH・第 {lineup.designatedHitter.order} 棒</span>
                  <PlayerLink pid={lineup.designatedHitter.id} name={lineup.designatedHitter.name}
                    className="font-semibold text-ink hover:text-accent hover:underline" />
                </p>
              )}
              <ol className="mt-3 grid grid-cols-3 gap-x-2 gap-y-1 border-t border-line pt-3 text-xs">
                {lineup.order.map((player) => (
                  <li key={player.id} className="flex min-w-0 items-center gap-1.5">
                    <span className="font-mono text-faint">{player.order}</span>
                    <PlayerLink pid={player.id} name={player.name} className="truncate text-ink hover:text-accent hover:underline" />
                  </li>
                ))}
              </ol>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
