"use client";

// 冠軍王朝榜：甜甜圈圖（各球團佔 36 座冠軍的比例，隊色 slice）＋右側資訊面板。
// 指到 slice 顯示該隊奪冠年份；右側密集呈現座數／佔比／連霸／最近奪冠（標籤）。
import Link from "next/link";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Pill, TeamBadge } from "@/components/ui";
import { chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { teamColor } from "@/lib/teams";

export type DynastyRow = { team_code: string; team: string | null; titles: number; years: number[]; rk: number };

function longestStreak(years: number[]): number {
  const ys = [...new Set(years)].sort((a, b) => a - b);
  let best = 1, run = 1;
  for (let i = 1; i < ys.length; i++) {
    run = ys[i] === ys[i - 1] + 1 ? run + 1 : 1;
    if (run > best) best = run;
  }
  return best;
}

function YearTooltip({ active, payload }: { active?: boolean; payload?: { payload: DynastyRow }[] }) {
  const ct = useChartTheme();
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{ ...chartTooltip(ct), padding: "6px 10px", maxWidth: 220 }}>
      <div style={{ fontWeight: 700 }}>{d.team}・{d.titles} 座冠軍</div>
      <div style={{ color: ct.muted, marginTop: 2 }}>{d.years.join("、")}</div>
    </div>
  );
}

export function DynastyChart({ rows }: { rows: DynastyRow[] }) {
  const total = rows.reduce((s, r) => s + r.titles, 0);
  return (
    <div className="card grid items-center gap-5 p-4 sm:grid-cols-[220px_1fr]">
      <div className="relative mx-auto h-52 w-52">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="titles" nameKey="team" innerRadius="60%" outerRadius="95%" paddingAngle={2} stroke="none">
              {rows.map((r) => <Cell key={r.team_code} fill={teamColor(r.team_code)} />)}
            </Pie>
            <Tooltip content={<YearTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-3xl font-extrabold tabular-nums text-ink">{total}</span>
          <span className="text-[11px] text-muted">座冠軍・{rows.length} 隊</span>
        </div>
      </div>

      <ul className="space-y-1.5">
        {rows.map((r) => {
          const streak = longestStreak(r.years);
          const pct = Math.round((r.titles / total) * 100);
          return (
            <li key={r.team_code} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: teamColor(r.team_code) }} />
              <Link href={`/teams/${r.team_code}`} className="font-sans font-medium hover:underline">
                <TeamBadge code={r.team_code} name={r.team} size={16} />
              </Link>
              {r.rk === 1 && <Pill tone="up">榜首</Pill>}
              {streak >= 2 && <Pill tone="muted" className="!bg-accent/15 !text-accent">{streak} 連霸</Pill>}
              <span className="ml-auto flex items-baseline gap-2 tabular-nums">
                <span className="text-[11px] text-faint">最近 {Math.max(...r.years)}</span>
                <span className="w-8 text-right text-[11px] text-muted">{pct}%</span>
                <span className="w-7 text-right font-bold text-accent">{r.titles}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
