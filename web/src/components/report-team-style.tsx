"use client";

import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";
import { useChartTheme } from "@/lib/chart-theme";
import { clampZ, TEAM_STYLE_SECTION } from "@/lib/team-style";
import { teamColor } from "@/lib/teams";
import type { Report } from "@/lib/report-types";

/** 沿球隊頁既有七軸與 [-2,2] 顯示尺度；不計算能力或新的球風評分。 */
export function ReportTeamStyle({ style }: { style: NonNullable<Report["teams"]>[number] }) {
  const ct = useChartTheme();
  const season = style.seasons[0];
  const complete = style.axes.length === 7 && new Set(style.axes.map(a => a.key)).size === 7 && style.axes.every(a => Number.isFinite(season?.axes[a.key]?.z));
  if (!complete) return <p className="mt-3 text-sm text-muted">本站未取得完整本季球風</p>;
  const data = style.axes.map(a => ({ label:a.label, z:clampZ(season.axes[a.key].z) }));
  const color = teamColor(style.team);
  return <figure className="min-w-0" aria-label="本季七軸球風">
    <div className="mt-4 h-60 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="74%">
          <PolarGrid stroke={ct.line} />
          <PolarAngleAxis dataKey="label" tick={{ fill:ct.muted, fontSize:11 }} />
          <PolarRadiusAxis domain={[-2,2]} tick={false} axisLine={false} />
          <Radar dataKey="z" stroke={color} fill={color} fillOpacity={0.3} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
    <figcaption className="text-xs text-muted">{TEAM_STYLE_SECTION.radarCaption}</figcaption>
    <dl className="mt-3 grid grid-cols-2 gap-3">{style.axes.map(a => <div key={a.key}><dt className="text-xs text-muted">{a.label}</dt><dd className="mt-1 font-mono text-sm">第 {season.axes[a.key].rank} / {season.n_teams} 隊</dd></div>)}</dl>
  </figure>;
}
