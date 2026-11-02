"use client";

// #415：能力值雷達（recharts）自 `ability-card.tsx` 獨立成模組，由該檔以 `next/dynamic(ssr:false)` 按需載入；
// 卡標題、等級、`?` 方法說明與 `role="img"` 等高容器留在 `ability-card.tsx` 即時渲染。
// 雷達本體與 `AbilityRadarVS`（對戰卡兩人疊圖；目前無消費者）原樣搬移，recharts 用法不變（#419 升級時連同本檔處理）。
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { useChartTheme } from "@/lib/chart-theme";
import type { Card } from "./ability-card";

export type RadarTickProps = { x: number; y: number; textAnchor: string; payload: { value: string } };

export default function AbilityRadar({ data, compact, radarColor, tick }: {
  data: { axis: string; pr: number }[];
  compact: boolean;
  radarColor: string;
  /** compact＝樣式物件；否則為自訂軸名刻度（含組成提示）。 */
  tick: { fontSize: number; fill: string } | ((props: RadarTickProps) => React.ReactElement<SVGElement>);
}) {
  const ct = useChartTheme();
  return (
    <ResponsiveContainer width="100%" height="100%">
      <RadarChart data={data} outerRadius={compact ? "70%" : "78%"}>
        <PolarGrid stroke={ct.line} />
        <PolarAngleAxis dataKey="axis" tick={tick} />
        {/* 半徑軸釘死 0–100：不設的話 recharts 自動縮放到本人最大值，
            圖形變「相對自己」而等級是絕對 PR（羅戈 續航78/B 被畫到滿格）*/}
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        <Radar dataKey="pr" stroke={radarColor} strokeWidth={2} fill={radarColor} fillOpacity={0.14} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

// 兩人雷達疊圖（對戰卡：主投 vs 客投）。
export function AbilityRadarVS({
  home,
  away,
  homeColor,
  awayColor,
}: {
  home: Card;
  away: Card;
  homeColor?: string;
  awayColor?: string;
}) {
  const ct = useChartTheme();
  if (!home?.available || !away?.available || !home.axes) return null;
  const data = home.axes.map((a, i) => ({
    axis: a.label,
    home: a.pr ?? 0,
    away: away.axes?.[i]?.pr ?? 0,
  }));
  return (
    <div className="h-44" role="img" aria-label="兩位先發投手能力值雷達疊圖，各項為全聯盟百分位">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke={ct.line} />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 10, fill: ct.muted }} />
          {/* 同上：兩人疊圖更不能各自縮放，0–100 絕對刻度才可比 */}
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar dataKey="away" stroke={awayColor ?? ct.accent} fill={awayColor ?? ct.accent} fillOpacity={0.25} />
          <Radar dataKey="home" stroke={homeColor ?? ct.down} fill={homeColor ?? ct.down} fillOpacity={0.25} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
