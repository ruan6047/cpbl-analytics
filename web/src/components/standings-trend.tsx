// 戰績走勢折線圖：x=日期、y=累積勝-敗差（高於 .500 的場數），每隊一條線、隊色。
"use client";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { nameMeta, teamColor, teamShort } from "@/lib/teams";
import { chartAxis, chartTooltip, useChartTheme } from "@/lib/chart-theme";
import type { StandingsTrendPoint } from "@/lib/api";

const fmt = (v: number) => (v > 0 ? `+${v}` : `${v}`);

// 隊名優先(era 名 + nameMeta 色)，無則退回代碼解析
function labelOf(code: string, names?: Record<string, string>) {
  const nm = names?.[code];
  return nm || teamShort(code) || code;
}
function colorOf(code: string, names?: Record<string, string>) {
  const nm = names?.[code];
  const m = nm ? nameMeta(nm) : null;
  return m && m.letter !== "?" ? m.color : teamColor(code);
}

export function StandingsTrend({ teams, points, names }: { teams: string[]; points: StandingsTrendPoint[]; names?: Record<string, string> }) {
  const ct = useChartTheme();
  const axis = chartAxis(ct);
  return (
    <div role="img" aria-label="各隊累積勝敗差戰績走勢折線圖，隨賽季日期變化">
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: -16 }}>
        <CartesianGrid stroke={ct.surface2} vertical={false} />
        <XAxis dataKey="date" {...axis} minTickGap={36} />
        <YAxis {...axis} width={40} allowDecimals={false} tickFormatter={fmt} />
        <ReferenceLine y={0} stroke={ct.faint} strokeDasharray="4 4" label={{ value: ".500", position: "right", fill: ct.faint, fontSize: 10 }} />
        <Tooltip
          contentStyle={chartTooltip(ct)}
          labelStyle={{ color: ct.muted }}
          itemSorter={(i) => -(i.value as number)}
          formatter={(v: number, name: string) => [fmt(v), name]}
        />
        <Legend formatter={(v) => <span className="text-xs text-ink">{v}</span>} />
        {teams.map((t) => (
          <Line
            key={t}
            type="monotone"
            dataKey={t}
            name={labelOf(t, names)}
            stroke={colorOf(t, names)}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
    </div>
  );
}
