"use client";

// 賽季走勢（逐場累積/滾動）+ 對戰各隊。兩者皆空（退役球員）則整段隱藏。
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui";
import { type StatRow } from "@/lib/client";
import { BAT_METRICS, PIT_METRICS, type Role, axis } from "./lib";
import { VsTeamTable } from "./parts";

export function TrendVsSection({ trend, careerMonthly, vsTeam, role }: {
  trend: StatRow[] | null;
  careerMonthly: StatRow[] | null;
  vsTeam: StatRow[] | null;
  role: Role;
}) {
  const [monthMetric, setMonthMetric] = useState(role === "batting" ? "ops_plus" : "era_plus");
  const [trendScope, setTrendScope] = useState<"season" | "career">("season");
  useEffect(() => { setMonthMetric(role === "batting" ? "ops_plus" : "era_plus"); }, [role]);

  const metrics = role === "batting" ? BAT_METRICS : PIT_METRICS;
  const metric = metrics.find((m) => m.key === monthMetric) ?? metrics[0];
  const monthData = useMemo(
    () => (trend ?? []).map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [trend, metric],
  );
  // 生涯月份分項：跨年份把同一月份合併為一點（看慢熱/各月強弱、當下月參考）
  const careerTrendData = useMemo(
    () => (careerMonthly ?? []).filter((r) => metric.get(r) != null)
      .map((r) => ({ name: String(r.name), v: metric.get(r) })),
    [careerMonthly, metric],
  );
  // 本季計數型(柱狀)：逐場太細 → 以 7 天為一箱加總,看期間變化
  const seasonBars = useMemo(() => {
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

  // 本季逐場、生涯逐年、對戰各隊任一有料即顯示（載入中仍顯示）
  const showTrendVs = trend === null || vsTeam === null || monthData.length > 0
    || careerTrendData.length > 0 || (vsTeam?.length ?? 0) > 0;
  if (!showTrendVs) return null;
  // 走勢有效範圍：本季無資料(退役)但有生涯逐年 → 自動切生涯
  const effTrend: "season" | "career" =
    trendScope === "season" && monthData.length === 0 && careerTrendData.length > 0 ? "career" : trendScope;
  const trendData = effTrend === "career" ? careerTrendData : (metric.roll ? monthData : seasonBars);

  return (
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-ink">賽季走勢 · 對戰各隊</h2>
        <div className="grid items-stretch gap-6 lg:grid-cols-2">
          <Card className="h-full">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-muted">{effTrend === "career" ? "生涯各週（跨年合併）" : (metric.roll ? "賽季走勢（近 15 場滾動）" : "賽季走勢（每 7 天）")}</h3>
                {careerTrendData.length > 1 && monthData.length > 0 && (
                  <div className="inline-flex overflow-hidden rounded-full border border-line text-[11px]">
                    {(["season", "career"] as const).map((s) => (
                      <button key={s} onClick={() => setTrendScope(s)}
                        className={`px-2.5 py-0.5 transition ${effTrend === s ? "bg-ink text-white" : "bg-surface text-muted hover:text-ink"}`}>
                        {s === "season" ? "本季" : "生涯"}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <select value={monthMetric} onChange={(e) => setMonthMetric(e.target.value)} aria-label="走勢指標"
                className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none focus:border-ink">
                {metrics.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
            {trendData.length === 0 ? <p className="py-8 text-center text-sm text-faint">無資料</p> : (
              <ResponsiveContainer width="100%" height={220}>
                <ComposedChart data={trendData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid stroke="#eef2f7" />
                  {/* 生涯=月份分項(3月/4月…類別)；本季=逐場/週期日期 */}
                  <XAxis dataKey="name" {...axis} minTickGap={effTrend === "career" ? 4 : 28} />
                  <YAxis {...axis} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number) => v?.toFixed(metric.dp)} />
                  {metric.ref != null && (
                    <ReferenceLine y={metric.ref} stroke="#94a3b8" strokeDasharray="4 3"
                      label={{ value: `聯盟 ${metric.ref}`, position: "insideTopRight", fill: "#94a3b8", fontSize: 10 }} />
                  )}
                  {metric.roll ? (
                    <Line type="monotone" dataKey="v" name={metric.label} stroke="#0a2540" strokeWidth={2}
                      isAnimationActive={false} connectNulls
                      dot={trendData.length > 18 ? false : { r: 3, fill: "#d62839" }} />
                  ) : (
                    <Bar dataKey="v" name={metric.label} fill="#1B4DA1" isAnimationActive={false}
                      maxBarSize={18} />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </Card>
          <Card className="h-full">
            <h3 className="mb-3 text-sm font-medium text-muted">對戰各隊（本季）</h3>
            {vsTeam === null ? <p className="py-8 text-center text-sm text-faint">載入中…</p>
              : vsTeam.length === 0 ? <p className="py-8 text-center text-sm text-faint">無資料</p>
              : <VsTeamTable items={vsTeam} role={role} />}
          </Card>
        </div>
      </section>
  );
}
