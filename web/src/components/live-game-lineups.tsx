import { PlayerLink, TeamLogo } from "@/components/ui";
import { DEFEND_ZH } from "@/components/game-board";
import { lineupMessage, type LiveSnapshot } from "@/lib/live-game";

export function LiveGameLineups({ snapshot }: { snapshot: LiveSnapshot }) {
  const side = (which: "away" | "home") => {
    const data = snapshot[which];
    const message = lineupMessage(data.lineup.availability, snapshot.freshness, snapshot.source_status);
    return (
      <section className="rounded-xl border border-line bg-surface p-4" aria-label={`${data.team.name}先發名單`}>
        <div className="mb-3 flex min-h-11 items-center gap-2 border-b border-line pb-2">
          <TeamLogo code={data.team.code} name={data.team.name} size={28} />
          <h3 className="font-semibold text-ink">{data.team.name}</h3>
          <span className="ml-auto text-xs text-muted">{message}</span>
        </div>
        {data.lineup.items.length ? (
          <ol className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
            {data.lineup.items
              .slice()
              .sort((a, b) => a.batting_order - b.batting_order)
              .map((player) => (
                <li key={`${player.batting_order}-${player.player_id}`} className="flex min-w-0 items-center gap-2 text-sm">
                  <span className="w-5 shrink-0 text-right font-mono text-xs tabular-nums text-faint">{player.batting_order}</span>
                  <PlayerLink pid={player.player_id} name={player.name} className="min-w-0 truncate" />
                  <span className="ml-auto shrink-0 text-xs text-muted">{DEFEND_ZH[player.position] ?? player.position}</span>
                </li>
              ))}
          </ol>
        ) : (
          <p className="text-sm text-muted">
            {snapshot.source_status === "error" ? "目前無可保留的名單資料。" : "官方尚未提供先發棒次與守位。"}
          </p>
        )}
      </section>
    );
  };

  return (
    <section aria-labelledby="live-lineups-title">
      <h2 id="live-lineups-title" className="mb-3 text-sm font-semibold tracking-wide text-muted">先發名單</h2>
      <div className="grid gap-4 lg:grid-cols-2">{side("away")}{side("home")}</div>
    </section>
  );
}
