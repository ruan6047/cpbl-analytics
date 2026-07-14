"use client";

import Link from "next/link";
import { TeamLogo, Card } from "@/components/ui";
import { teamPageCode } from "@/lib/teams";
import type { OfficialStanding } from "@/lib/api";

const pct = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0/, ""));

export default function MiniStandings({
  standings,
}: {
  standings: OfficialStanding[];
}) {
  return (
    <Card className="flex flex-col" padding="p-0">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-bold text-ink">全聯盟戰績</h2>
      </div>

      <div className="w-full overflow-x-auto">
        <table className="w-full text-left text-xs table-auto">
          <thead>
            <tr className="border-b border-line bg-surface-2 text-muted font-semibold">
              <th className="py-2 px-3 text-center w-8">#</th>
              <th className="py-2 px-2 min-w-[70px]">球隊</th>
              <th className="py-2 px-1.5 text-center">已賽</th>
              <th className="py-2 px-1.5 text-center whitespace-nowrap">勝-和-敗</th>
              <th className="py-2 px-1.5 text-right">勝率</th>
              <th className="py-2 px-1.5 text-right">勝差</th>
              <th className="py-2 pl-2 pr-3 text-center">近況</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/40">
            {standings.map((team, idx) => {
              const rank = team.rank || idx + 1;

              return (
                <tr
                  key={team.team_code}
                  className="hover:bg-surface-2/50 transition-colors"
                >
                  <td className="py-2.5 px-3 text-center font-mono font-bold text-faint">
                    {rank}
                  </td>
                  <td className="py-2.5 px-2 font-medium text-ink min-w-0">
                    <Link
                      href={`/teams/${teamPageCode(team.team_code)}`}
                      className="inline-flex items-center gap-1.5 group hover:text-accent transition w-full"
                    >
                      <TeamLogo code={team.team_code} name={team.team_name} size={16} decorative />
                      <span className="truncate max-w-[65px] xs:max-w-[80px] sm:max-w-none">
                        {team.team_name}
                      </span>
                    </Link>
                  </td>
                  <td className="py-2.5 px-1.5 text-center font-mono text-muted">
                    {team.g}
                  </td>
                  <td className="py-2.5 px-1.5 text-center font-mono text-muted tabular-nums whitespace-nowrap">
                    {team.w}-{team.t}-{team.l}
                  </td>
                  <td className="py-2.5 px-1.5 text-right font-mono text-ink font-semibold tabular-nums">
                    {pct(team.win_pct)}
                  </td>
                  <td className="py-2.5 px-1.5 text-right font-mono text-muted tabular-nums">
                    {team.gb === 0 || team.gb == null ? "—" : team.gb.toFixed(1)}
                  </td>
                  <td className="py-2.5 pl-2 pr-3 text-center">
                    {team.streak ? (
                      <span
                        className={`inline-block rounded px-1.5 py-0.5 text-[9px] font-bold whitespace-nowrap ${
                          team.streak.startsWith("W")
                            ? "bg-up/10 text-up"
                            : "bg-accent/10 text-accent"
                        }`}
                      >
                        {team.streak}
                      </span>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
