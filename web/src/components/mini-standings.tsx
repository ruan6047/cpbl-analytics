"use client";

import Link from "next/link";
import { ENTITY_LINK_TEXT, TeamLogo } from "@/components/ui";
import { SectionTitle } from "@/components/postmark";
import { teamPageCode } from "@/lib/teams";
import type { OfficialStanding } from "@/lib/api";

const pct = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0/, ""));

// 首頁戰績摘要（#218 home.html「戰績」）：共用資料表語言——表頭色塊帶、列間不畫線、
// 勝率為主指標加粗；近況（連勝敗）保留，連敗走 down 紅（#220 起 accent 是石油藍，不再兼任負向）。
export default function MiniStandings({
  standings,
}: {
  standings: OfficialStanding[];
}) {
  return (
    <section aria-labelledby="home-standings-h">
      <SectionTitle as="h2" size="sm" id="home-standings-h" cue="全年・一軍">戰績</SectionTitle>
      <div className="w-full overflow-x-auto rounded-md">
        <table className="pm-data">
          <thead>
            <tr>
              <th className="w-8 text-left">#</th>
              <th className="min-w-[70px] text-left">球隊</th>
              <th className="text-right">已賽</th>
              <th className="whitespace-nowrap text-right">勝-和-敗</th>
              <th className="text-right">勝率</th>
              <th className="text-right">勝差</th>
              <th className="text-right">近況</th>
            </tr>
          </thead>
          <tbody>
            {standings.map((team, idx) => {
              const rank = team.rank || idx + 1;
              return (
                <tr key={team.team_code}>
                  <td className="text-left font-mono text-muted">{rank}</td>
                  <td className="text-left">
                    {/* 整塊（含印記）維持可點，底線只跟隊名文字。 */}
                    <Link href={`/teams/${teamPageCode(team.team_code)}`} className="group inline-flex items-center gap-2">
                      <TeamLogo code={team.team_code} name={team.team_name} size={20} decorative />
                      <span className={`whitespace-nowrap ${ENTITY_LINK_TEXT}`}>{team.team_name}</span>
                    </Link>
                  </td>
                  <td className="text-right font-mono tabular-nums">{team.g}</td>
                  <td className="whitespace-nowrap text-right font-mono tabular-nums">{team.w}-{team.t}-{team.l}</td>
                  <td className="text-right font-mono font-extrabold tabular-nums text-ink">{pct(team.win_pct)}</td>
                  <td className="text-right font-mono tabular-nums">
                    {team.gb === 0 || team.gb == null ? "—" : team.gb.toFixed(1)}
                  </td>
                  <td className="text-right">
                    {team.streak ? (
                      <span className={`whitespace-nowrap text-xs font-bold ${team.streak.startsWith("W") ? "text-up" : "text-down"}`}>
                        {team.streak}
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
