"use client";

// #415：走勢折線／柱狀圖（recharts）獨立成模組，由 `trend.tsx` 以 `next/dynamic(ssr:false)` 按需載入，
// 讓 `/players/[id]` 首載不帶 recharts 及其相依；卡殼、標題、指標下拉與逐場小表留在 `trend.tsx`。
// 圖表本體與 props 原樣搬移（#419 recharts 3 升級時連同本檔一起處理）。
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartAxis, chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { type Metric } from "./lib";

export default function TrendChart({ data, metric, categorical }: {
  data: { name: string; v: number | null }[]; metric: Metric; categorical: boolean;
}) {
  const ct = useChartTheme();
  const axis = chartAxis(ct);
  // 高度 220 須與 trend.tsx 的 CHART_H 一致（佔位、空態、逐場小表都用它）；⛔ 不從本檔 export 常數給 trend.tsx——那會變成靜態 import。
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={ct.surface2} />
        {/* 生涯=時段類別；本季=逐場/週期日期 */}
        <XAxis dataKey="name" {...axis} minTickGap={categorical ? 4 : 28} />
        <YAxis {...axis} domain={["auto", "auto"]} />
        <Tooltip contentStyle={chartTooltip(ct)} formatter={(v: number) => v?.toFixed(metric.dp)} />
        {metric.ref != null && (
          <ReferenceLine y={metric.ref} stroke={ct.faint} strokeDasharray="4 3"
            label={{ value: `聯盟 ${metric.ref}`, position: "insideTopRight", fill: ct.faint, fontSize: 10 }} />
        )}
        {metric.roll ? (
          <Line type="monotone" dataKey="v" name={metric.label} stroke={ct.ink} strokeWidth={2}
            isAnimationActive={false} connectNulls
            dot={data.length > 18 ? false : { r: 3, fill: ct.down }} />
        ) : (
          <Bar dataKey="v" name={metric.label} fill={ct.ink} isAnimationActive={false} maxBarSize={18} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
