"use client";

// 冠軍王朝榜長條圖（client island）：條長 ∝ titles/榜首；奪冠年份不常駐，指到隊伍才由
// Tooltip 顯示（Tooltip 用 React.Children.only，須在 client 端建立 children）。
import Link from "next/link";
import { Tooltip } from "@/components/tooltip";
import { TeamBadge } from "@/components/ui";
import { teamColor } from "@/lib/teams";

export type DynastyRow = { team_code: string; team: string | null; titles: number; years: number[]; rk: number };

export function DynastyChart({ rows }: { rows: DynastyRow[] }) {
  const max = rows[0]?.titles ?? 1;
  return (
    <div className="card space-y-2.5 p-4">
      {rows.map((r) => (
        <div key={r.team_code} className="grid grid-cols-[6.5rem_1fr_1.75rem] items-center gap-3">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="w-4 shrink-0 text-right font-mono text-xs tabular-nums text-faint">{r.rk}</span>
            <Tooltip content={`${r.titles} 座冠軍：${r.years.join("、")}`} suppressUnderline>
              <Link href={`/teams/${r.team_code}`} className="inline-flex cursor-help items-center gap-1.5 font-sans font-medium hover:underline">
                <TeamBadge code={r.team_code} name={r.team} size={16} />
              </Link>
            </Tooltip>
          </span>
          <span className="h-4 overflow-hidden rounded bg-surface-2">
            <span className="block h-full rounded" style={{ width: `${Math.max(6, (r.titles / max) * 100)}%`, background: teamColor(r.team_code) }} />
          </span>
          <span className="text-right text-sm font-bold tabular-nums text-accent">{r.titles}</span>
        </div>
      ))}
    </div>
  );
}
