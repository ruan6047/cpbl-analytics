"use client";

// 走勢與對戰。IA 分層（UX-PLAYER-IA1）後拆為三張獨立卡：
// SeasonTrendCard→L1 總覽（本季逐場/滾動）、CareerTrendCard／VsTeamCard→L3 分項與對戰。
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, EmptyState } from "@/components/ui";
import { type Column, DataTable } from "@/components/table";
import { type StatRow } from "@/lib/client";
import { chartAxis, chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { BAT_METRICS, type Metric, n0, PIT_METRICS, type Role } from "./lib";
import { VsTeamTable } from "./parts";
import { MIN_TREND_POINTS, gameLogMetrics, gameLogRows, gameLogSummary, showGameLog } from "./season-trend";

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

// 圖表高度（ResponsiveContainer 固定值）。載入／空態必須佔用同樣高度，
// 否則切 role 時內容瞬間縮水會改變文件高度，讓瀏覽器把捲動位置往回夾（REVIEW-005 P1）。
const CHART_H = 220;

/** 與圖表等高的佔位容器：載入中與空態都用它，確保高度不隨資料狀態變動。 */
function ChartSlot({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center" style={{ minHeight: CHART_H }}>
      {children}
    </div>
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
          <Bar dataKey="v" name={metric.label} fill={ct.ink} isAnimationActive={false} maxBarSize={18} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---- L1 總覽：本季走勢 ----

/**
 * 所選滾動指標可畫的點少於 2 時取代折線（#318 方案一）：一行說明＋本季累計摘要＋逐場小表。
 * 高度固定為 CHART_H，與折線圖同高，切換指標時卡片高度不變（REVIEW-005 P1）；列多時在表內捲動。
 * 文案只陳述「畫不出走勢」，⛔ 不斷言原因是出賽太少（二軍背景的 OPS+／ERA+ 恆為 null，樣本充足也會觸發）。
 */
function SeasonGameLog({ rows, role, metric }: { rows: StatRow[]; role: Role; metric: Metric }) {
  const sum = gameLogSummary(rows, role);
  const cols: Column<StatRow>[] = [
    { header: "日期", cell: (r) => String(r.name), nowrap: true },
    ...gameLogMetrics(role).map((m): Column<StatRow> => ({
      header: m.label, align: "right", cell: (r) => n0(m.get(r)),
    })),
  ];
  return (
    <div className="flex flex-col gap-1.5" style={{ height: CHART_H }} data-testid="season-game-log">
      <p className="text-xs text-muted">
        {metric.label} 以近 15 場滾動計算，目前可畫的點不足 {MIN_TREND_POINTS} 個、連不成走勢，改列本季逐場紀錄。
      </p>
      <p className="text-xs text-ink">
        本季 {sum.games} 場（{sum.first === sum.last ? sum.first : `${sum.first}–${sum.last}`}）
        {sum.totals.map((t) => <span key={t.key}> · {t.label} <span className="font-mono tabular-nums">{n0(t.value)}</span></span>)}
      </p>
      <div className="relative min-h-0 flex-1">
        <DataTable columns={cols} rows={gameLogRows(rows)} rowKey={(r, i) => `${String(r.date)}-${i}`}
          dense bare maxHeight="100%" className="absolute inset-0" />
      </div>
    </div>
  );
}

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
  const gameLog = trend !== null && showGameLog(trend, metric);
  return (
    <Card className="h-full">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-muted">
          {metric.roll ? "賽季走勢（近 15 場滾動）" : "賽季走勢（每 7 天）"}
        </h3>
        <MetricSelect metrics={metrics} value={key} onChange={setKey} />
      </div>
      {trend === null ? <ChartSlot><EmptyState>載入中…</EmptyState></ChartSlot>
        : data.length === 0 ? (
          <ChartSlot>
            <EmptyState>
              {isRetired ? "本季無出賽紀錄（已退役／轉任教練），逐年表現請見「生涯」。" : "本季尚無足夠出賽場次可繪製走勢。"}
            </EmptyState>
          </ChartSlot>
        ) : gameLog ? <SeasonGameLog rows={trend} role={role} metric={metric} />
        : <TrendChart data={data} metric={metric} categorical={false} />}
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
      {careerMonthly === null ? <ChartSlot><EmptyState>載入中…</EmptyState></ChartSlot>
        : data.length === 0 ? <ChartSlot><EmptyState>此指標無足夠生涯逐週樣本。</EmptyState></ChartSlot>
        : <TrendChart data={data} metric={metric} categorical />}
    </Card>
  );
}

export function VsTeamCard({ vsTeam, role }: { vsTeam: StatRow[] | null; role: Role }) {
  return (
    <Card className="h-full">
      <h3 className="mb-3 text-sm font-medium text-muted">對戰各隊（本季）</h3>
      {vsTeam === null ? <ChartSlot><EmptyState>載入中…</EmptyState></ChartSlot>
        : vsTeam.length === 0 ? <ChartSlot><EmptyState>本季無對戰分項（未出賽或資料未產出）。</EmptyState></ChartSlot>
        : <VsTeamTable items={vsTeam} role={role} />}
    </Card>
  );
}
