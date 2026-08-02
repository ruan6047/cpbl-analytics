import { RosterBoard } from "@/components/roster-board";
import { TeamLogo } from "@/components/ui";
import { lineupMessage, type LiveSnapshot } from "@/lib/live-game";
import { liveLineupBoard } from "@/lib/live-lineup-board";

export function LiveGameLineups({ snapshot }: { snapshot: LiveSnapshot }) {
  const side = (which: "away" | "home") => {
    const data = snapshot[which];
    const message = lineupMessage(data.lineup.availability, snapshot.freshness, snapshot.source_status);
    const board = liveLineupBoard(data);
    return (
      <section aria-label={`${data.team.name}先發名單`}>
        <div className="mb-3 flex min-h-11 items-center gap-2">
          <TeamLogo code={data.team.code} name={data.team.name} size={28} />
          <h3 className="font-semibold text-ink">{data.team.name}</h3>
          <span className="ml-auto text-xs text-muted">{message}</span>
        </div>
        {data.lineup.items.length ? (
          <RosterBoard fieldCells={board.fieldCells} designatedHitter={board.designatedHitter}
            caption={`${data.team.name}先發守備位置`} groups={board.groups}
            emptyField="官方尚未提供可繪製的先發守備資料。" />
        ) : (
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-sm text-muted">
              {snapshot.source_status === "error" ? "目前無可保留的名單資料。" : "官方尚未提供先發棒次與守位。"}
            </p>
          </div>
        )}
      </section>
    );
  };

  return (
    <section aria-labelledby="live-lineups-title">
      <h2 id="live-lineups-title" className="mb-3 text-sm font-semibold tracking-wide text-muted">先發名單</h2>
      <div className="grid gap-5 xl:grid-cols-2">{side("away")}{side("home")}</div>
    </section>
  );
}
