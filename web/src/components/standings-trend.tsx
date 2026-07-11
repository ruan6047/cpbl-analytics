// 戰績走勢折線圖：x=日期、y=累積勝-敗差（高於 .500 的場數），每隊一條線、隊色。
"use client";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { contrastText, nameMeta, teamColor, teamLetter, teamShort } from "@/lib/teams";
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
function letterOf(code: string, names?: Record<string, string>) {
  const nm = names?.[code];
  const m = nm ? nameMeta(nm) : null;
  return m && m.letter !== "?" ? m.letter : teamLetter(code);
}

// 折線尾端隊徽（direct labeling 取代 legend）：僅在最後一點畫隊色方塊+字母。
// dy 供垂直錯位（避免多隊末值相近時徽章重疊）。
function makeEndBadge(color: string, letter: string, lastIndex: number, dy: number) {
  const txt = contrastText(color);
  function EndBadge(props: { x?: number; y?: number; index?: number }) {
    const { x, y, index } = props;
    if (index !== lastIndex || x == null || y == null) return <g />;
    return (
      <g transform={`translate(${x + 5}, ${y + dy})`}>
        <rect x={0} y={-8} width={16} height={16} rx={3} fill={color} />
        <text x={8} y={1} textAnchor="middle" dominantBaseline="middle" fontSize={10} fontWeight={700} fill={txt}>{letter}</text>
      </g>
    );
  }
  return EndBadge;
}

export function StandingsTrend({ teams, points, names }: { teams: string[]; points: StandingsTrendPoint[]; names?: Record<string, string> }) {
  const ct = useChartTheme();
  const axis = chartAxis(ct);

  // 末值 → 估算像素 y → 貪婪垂直錯位（min gap 17px），避免多隊末值相近時尾端隊徽重疊。
  const lastIdx = points.length - 1;
  const allVals = points.flatMap((p) => teams.map((t) => (p as Record<string, number>)[t]).filter((v) => typeof v === "number"));
  const yMax = allVals.length ? Math.max(...allVals) : 1;
  const yMin = allVals.length ? Math.min(...allVals) : 0;
  const plotH = 340 - 8 - 4 - 22; // 估算繪圖區高（扣上下 margin 與 x 軸）
  const scale = yMax > yMin ? plotH / (yMax - yMin) : 1;
  const pxOf = (v: number) => 8 + (yMax - v) * scale;
  const ends = teams
    .map((t) => ({ t, v: (points[lastIdx] as Record<string, number> | undefined)?.[t] }))
    .filter((e): e is { t: string; v: number } => typeof e.v === "number")
    .sort((a, b) => b.v - a.v);
  const dyMap = new Map<string, number>();
  let prevPx = -Infinity;
  for (const e of ends) {
    const px = Math.max(pxOf(e.v), prevPx + 17);
    dyMap.set(e.t, px - pxOf(e.v));
    prevPx = px;
  }

  return (
    <div role="img" aria-label="各隊累積勝敗差戰績走勢折線圖，隨賽季日期變化，線尾標隊徽">
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={points} margin={{ top: 8, right: 30, bottom: 4, left: -16 }}>
        <CartesianGrid stroke={ct.surface2} vertical={false} />
        <XAxis dataKey="date" {...axis} minTickGap={36} />
        <YAxis {...axis} width={40} allowDecimals={false} tickFormatter={fmt} />
        <ReferenceLine y={0} stroke={ct.faint} strokeDasharray="4 4" label={{ value: ".500", position: "insideLeft", fill: ct.faint, fontSize: 10 }} />
        <Tooltip
          contentStyle={chartTooltip(ct)}
          labelStyle={{ color: ct.muted }}
          itemSorter={(i) => -(i.value as number)}
          formatter={(v: number, name: string) => [fmt(v), name]}
        />
        {teams.map((t) => (
          <Line
            key={t}
            type="monotone"
            dataKey={t}
            name={labelOf(t, names)}
            stroke={colorOf(t, names)}
            strokeWidth={2}
            dot={false}
            label={makeEndBadge(colorOf(t, names), letterOf(t, names), lastIdx, dyMap.get(t) ?? 0)}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
    </div>
  );
}
