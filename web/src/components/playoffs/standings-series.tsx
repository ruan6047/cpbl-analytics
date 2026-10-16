import Link from "next/link";
import { TeamBadge } from "@/components/ui";
import { teamShort } from "@/lib/teams";
import { seriesHref } from "@/lib/playoffs-types";
import type { PostseasonSeriesContextV2 } from "@/lib/postseason-series-contract";

/** 比分直接使用正式系列 total_wins（包含有根據的讓勝），不從逐場勝數反推。 */
export function StandingsSeries({ year, context }: { year: number; context: PostseasonSeriesContextV2 | null | undefined }) {
  return <div className="grid gap-4 md:grid-cols-2">{(["E", "C"] as const).map((code) => {
    const series = context?.year === year ? context.series[code] : null;
    return <section key={code} className="rounded bg-surface p-4">
      <h2 className="text-lg font-bold">{code === "E" ? "季後挑戰賽" : "台灣大賽"}</h2>
      {series?.sides.length === 2 ? <div className="my-3 space-y-2">{series.sides.map((side, i) =>
        <div key={i} className="flex items-center justify-between gap-3">
          {side.team_code ? <TeamBadge code={side.team_code} name={teamShort(side.team_code) || side.team_code} /> : <span>隊伍待定</span>}
          <span className="tabular-nums">{side.total_wins ?? "—"}{side.initial_wins ? <small className="ml-2 text-muted">含讓 {side.initial_wins} 勝</small> : null}</span>
        </div>)}</div> : <p className="my-3 text-sm text-muted">系列比分未提供</p>}
      <Link className="inline-flex min-h-11 items-center underline underline-offset-4" href={seriesHref(code, year)}>季後賽專頁 →</Link>
    </section>;
  })}</div>;
}
