"use client";

// #415：組成型甜甜圈圖（recharts）自 `parts.tsx` 獨立成模組。`parts.tsx` 被 hero／season／detail／trend 共用，
// 留著 recharts import 會讓所有引用它的路由（含 `/playoffs` 名單抽屜）首載帶 PieChart chunk；
// 本模組只由逐球追蹤視圖（`tracking.tsx`，本身按需載入）引用。圖表本體原樣搬移。
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { EmptyState } from "@/components/ui";
import { PIE_COLORS } from "@/lib/chart-theme";

// 組成型百分位 → 甜甜圈圖 + 圖例（彈道分布/拉打方向；值總和≈100%）。色由色票 API PIE_COLORS 供給。
export function CompositionPie({ items, m }: { items: { k: string; label: string }[]; m: Record<string, number> }) {
  const data = items
    .map((it, i) => ({ name: it.label, value: m[it.k] == null ? 0 : +(m[it.k] * 100).toFixed(1), color: PIE_COLORS[i % PIE_COLORS.length] }))
    .filter((d) => d.value > 0);
  if (!data.length) return <EmptyState>無資料</EmptyState>;
  return (
    <div className="flex items-center gap-3">
      <div className="h-28 w-28 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={26} outerRadius={52} paddingAngle={2} stroke="none">
              {data.map((d) => <Cell key={d.name} fill={d.color} />)}
            </Pie>
            <Tooltip formatter={(v: number | string) => `${v}%`} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="min-w-0 flex-1 space-y-1.5 text-xs">
        {data.map((d) => (
          <li key={d.name} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: d.color }} />{d.name}
            </span>
            <span className="font-mono tabular-nums text-ink">{d.value}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
