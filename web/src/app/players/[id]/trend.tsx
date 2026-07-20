"use client";

// 走勢與對戰。IA 分層（UX-PLAYER-IA1）後拆為三張獨立卡：
// SeasonTrendCard→L1 總覽（本季逐場/滾動）、CareerTrendCard／VsTeamCard→L3 分項與對戰。
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, EmptyState } from "@/components/ui";
import { type StatRow } from "@/lib/client";
import { chartAxis, chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { BAT_METRICS, type Metric, PIT_METRICS, type Role } from "./lib";
import { VsTeamTable } from "./parts";

/** 指標下拉：各卡獨立持有選擇，role 變更時回到該 role 的預設指標。 */
function useMetric(role: Role) {
  const metrics = role === "batting" ? BAT_METRICS : PIT_METRICS;
  const [key, setKey] = useState(metrics[0].key);
  useEffect(() => { setKey((role === "batting" ? BAT_METRICS : PIT_METRICS)[0].key); }, [role]);
  const metric = metrics.find((m) => m.key === key) ?? metrics[0];
  return { metrics, metric, key, setKey };
}

function MetricSelect({ metrics, value, onChange }: {
  metrics: Metric[]; value: string; onChange: (v: string) => void;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="走勢指標"
      className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none focus:border-ink">
      {metrics.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
    </select>
  );
}

function TrendChart({ data, metric, categorical }: {
  data: { name: string; v: number | null }[]; metric: Metric; categorical: boolean;
}) {
  const ct = useChartTheme();
  const axis = chartAxis(ct);
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
          <Bar dataKey="v" name={metric.label} fill={ct.cpbl} isAnimationActive={false} maxBarSize={18} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---- L1 總覽：本季走勢 ----

export function SeasonTrendCard({ trend, role, isRetired }: {
  trend: StatRow[] | null; role: Role; isRetired: boolean;
}) {
  const { metrics, metric, key, setKey } = useMetric(role);
  const rollData = useMemo(
    () => (trend ?? []).map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [trend, metric],
  );
  // 本季計數型(柱狀)：逐場太細 → 以 7 天為一箱加總,看期間變化
  const bars = useMemo(() => {
    if (metric.roll) return [];
    const rows = trend ?? [];
    if (rows.length === 0) return [];
    const t0 = new Date(String(rows[0].date)).getTime();
    const buckets = new Map<number, { name: string; v: number }>();
    for (const r of rows) {
      const dt = new Date(String(r.date));
      const wk = Math.floor((dt.getTime() - t0) / (7 * 86400000));
      const b = buckets.get(wk) ?? { name: `${dt.getMonth() + 1}/${dt.getDate()}`, v: 0 };
      b.v += metric.get(r) ?? 0;
      buckets.set(wk, b);
    }
    return [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([, b]) => b);
  }, [trend, metric]);

  const data = metric.roll ? rollData : bars;
  return (
    <Card className="h-full">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-muted">
          {metric.roll ? "賽季走勢（近 15 場滾動）" : "賽季走勢（每 7 天）"}
        </h3>
        <MetricSelect metrics={metrics} value={key} onChange={setKey} />
      </div>
      {trend === null ? <EmptyState>載入中…</EmptyState>
        : data.length === 0 ? (
          <EmptyState>
            {isRetired ? "本季無出賽紀錄（已退役／轉任教練），逐年表現請見「生涯」。" : "本季尚無足夠出賽場次可繪製走勢。"}
          </EmptyState>
        ) : <TrendChart data={data} metric={metric} categorical={false} />}
    </Card>
  );
}

// ---- L3 分項與對戰：生涯時段分項、對戰各隊 ----

export function CareerTrendCard({ careerMonthly, role }: {
  careerMonthly: StatRow[] | null; role: Role;
}) {
  const { metrics, metric, key, setKey } = useMetric(role);
  // 生涯時段分項：跨年份把同一時段合併為一點（看慢熱/各時段強弱）
  const data = useMemo(
    () => (careerMonthly ?? []).filter((r) => metric.get(r) != null)
      .map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [careerMonthly, metric],
  );
  return (
    <Card className="h-full">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-muted">生涯各週（跨年合併）</h3>
        <MetricSelect metrics={metrics} value={key} onChange={setKey} />
      </div>
      {careerMonthly === null ? <EmptyState>載入中…</EmptyState>
        : data.length === 0 ? <EmptyState>此指標無足夠生涯逐週樣本。</EmptyState>
        : <TrendChart data={data} metric={metric} categorical />}
    </Card>
  );
}

export function VsTeamCard({ vsTeam, role }: { vsTeam: StatRow[] | null; role: Role }) {
  return (
    <Card className="h-full">
      <h3 className="mb-3 text-sm font-medium text-muted">對戰各隊（本季）</h3>
      {vsTeam === null ? <EmptyState>載入中…</EmptyState>
        : vsTeam.length === 0 ? <EmptyState>本季無對戰分項（未出賽或資料未產出）。</EmptyState>
        : <VsTeamTable items={vsTeam} role={role} />}
    </Card>
  );
}
