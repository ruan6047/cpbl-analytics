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
    <Card className="flex flex-col overflow-hidden" padding="p-0">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-bold text-ink">全聯盟戰績</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-line bg-surface-2 text-muted font-semibold">
              <th className="py-2.5 pl-4 pr-1 text-center w-8">#</th>
              <th className="py-2.5 px-2">球隊</th>
              <th className="py-2.5 px-2 text-center w-8">已賽</th>
              <th className="py-2.5 px-2 text-center w-14">勝-和-敗</th>
              <th className="py-2.5 px-2 text-right w-12">勝率</th>
              <th className="py-2.5 px-2 text-right w-10">勝差</th>
              <th className="py-2.5 pr-4 pl-2 text-center w-10">近況</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/40">
            {standings.map((team, idx) => {
              const rank = team.rank || idx + 1;
              const isLeader = rank === 1;

              return (
                <tr
                  key={team.team_code}
                  className="hover:bg-surface-2/50 transition-colors"
                >
                  <td className="py-2.5 pl-4 pr-1 text-center font-mono font-bold text-faint">
                    {rank}
                  </td>
                  <td className="py-2.5 px-2 font-medium text-ink">
                    <Link
                      href={`/teams/${teamPageCode(team.team_code)}`}
                      className="inline-flex items-center gap-2 group hover:text-accent transition"
                    >
                      <TeamLogo code={team.team_code} name={team.team_name} size={18} decorative />
                      <span className="truncate max-w-[80px] sm:max-w-none">
                        {team.team_name}
                      </span>
                    </Link>
                  </td>
                  <td className="py-2.5 px-2 text-center font-mono text-muted">
                    {team.g}
                  </td>
                  <td className="py-2.5 px-2 text-center font-mono text-muted tabular-nums">
                    {team.w}-{team.t}-{team.l}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-ink font-semibold tabular-nums">
                    {pct(team.win_pct)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-muted tabular-nums">
                    {team.gb === 0 || team.gb == null ? "—" : team.gb.toFixed(1)}
                  </td>
                  <td className="py-2.5 pr-4 pl-2 text-center">
                    {team.streak ? (
                      <span
                        className={`inline-block rounded px-1 py-0.5 text-[9px] font-bold ${
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
