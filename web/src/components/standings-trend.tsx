// 戰績走勢折線圖：x=日期、y=累積勝-敗差（高於 .500 的場數），每隊一條線、隊色。
"use client";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { teamColor, teamShort } from "@/lib/teams";
import type { StandingsTrendPoint } from "@/lib/api";

const axis = { tick: { fill: "#5b6b7a", fontSize: 11 }, stroke: "#cbd5e1" };
const fmt = (v: number) => (v > 0 ? `+${v}` : `${v}`);

export function StandingsTrend({ teams, points }: { teams: string[]; points: StandingsTrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: -16 }}>
        <CartesianGrid stroke="#eef2f7" vertical={false} />
        <XAxis dataKey="date" {...axis} minTickGap={36} />
        <YAxis {...axis} width={40} allowDecimals={false} tickFormatter={fmt} />
        <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: ".500", position: "right", fill: "#94a3b8", fontSize: 10 }} />
        <Tooltip
          contentStyle={{ background: "#0a2540", border: "none", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#cbd5e1" }}
          itemSorter={(i) => -(i.value as number)}
          formatter={(v: number, name: string) => [fmt(v), name]}
        />
        <Legend formatter={(v) => <span className="text-xs text-ink">{v}</span>} />
        {teams.map((t) => (
          <Line
            key={t}
            type="monotone"
            dataKey={t}
            name={teamShort(t)}
            stroke={teamColor(t)}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
