"use client";

// 逐球追蹤（落點/進壘點/揮棒紀律/熱區，共用單一球種鏡頭）+ 擊球品質彈道 + 打者散點/投手配球。
// pitchType 內化於 TrackingSection；page 以 key={id-role-seasonKind} 重掛以保留原重置語義。
import { useState } from "react";
import { LaEvScatter } from "@/components/la-ev-scatter";
import { type HeatMetric, Grid3x3, PlateDisciplineBars } from "@/components/perf-heatmap";
import { SprayChart } from "@/components/spray-chart";
import { Card, EmptyState, PR_GRADIENT, StatTile } from "@/components/ui";
import { type StatRow } from "@/lib/client";
import { ZoneScatter } from "@/components/zone-scatter";
import {
  CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip as ChartTip, XAxis, YAxis,
} from "recharts";
import { DataTable, type Column } from "@/components/table";
import { chartTooltip, pitchColor, useChartTheme } from "@/lib/chart-theme";
import { type Disc, type PitchType, type Role, QUALITY_GROUPS, ptSort, ptTypesFrom } from "./lib";
import { CompositionPie, PitchTypeToggle } from "./parts";

export function TrackingSection({ disc, role, seasonKind }: { disc: Disc | null; role: Role; seasonKind: "A" | "D" }) {
  const [pitchType, setPitchType] = useState<PitchType>("all");
  // 逐球追蹤是否有資料（無則整段隱藏；載入中仍顯示避免閃爍）
  const trackingReady = disc !== null;
  const hasTracking = !!(
    disc && (disc.points.length || disc.spray.length || disc.batted.length || disc.summary.swing_pct != null)
  );
  if (trackingReady && !hasTracking) return null;
  // 球種篩選（推算球種；all 不過濾）。可選球種由該球員實際投/面對的資料決定。
  const sprayF = disc ? (pitchType === "all" ? disc.spray : disc.spray.filter((p) => p.pt === pitchType)) : [];
  const pointsF = disc ? (pitchType === "all" ? disc.points : disc.points.filter((p) => p.pt === pitchType)) : [];
  const ptTypes = disc ? ptTypesFrom(disc.points.map((p) => p.pt)) : [];

  return (
      <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">逐球追蹤
            {seasonKind === "D" && <span className="ml-2 align-middle rounded bg-accent/10 px-1.5 py-0.5 text-xs font-semibold text-accent">二軍</span>}
            <span className="ml-2 align-middle text-xs font-normal text-faint">本季 · TrackMan 2026 起</span></h2>
          {ptTypes.length > 1 && <PitchTypeToggle value={pitchType} onChange={setPitchType} types={ptTypes} />}
        </div>
        <div className="grid items-stretch gap-6 lg:grid-cols-3">
          <Card className="flex flex-col lg:col-span-2">
            <div className="grid gap-x-4 sm:grid-cols-2">
              <div className="relative flex flex-col">
                <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">擊球落點（{sprayF.length} 球）</h3>
                {disc === null ? <EmptyState className="py-12">載入中…</EmptyState>
                  : sprayF.length > 0 ? <div className="mt-auto mb-[13%]"><SprayChart points={sprayF} /></div>
                  : <EmptyState className="py-12">{disc.spray.length ? "此球種無擊球" : "無擊球追蹤資料"}</EmptyState>}
              </div>
              <div className="relative">
                <h3 className="absolute left-0 top-0 z-10 text-sm font-medium text-muted">進壘點（{pointsF.length} 球）</h3>
                {disc === null ? <EmptyState className="py-12">載入中…</EmptyState>
                  : pointsF.length > 0 ? <ZoneScatter points={pointsF} />
                  : <EmptyState className="py-12">{disc.points.length ? "此球種無資料" : "無逐球資料"}</EmptyState>}
              </div>
            </div>
          </Card>
          {/* 揮棒紀律(打者)：揮/不揮 分歧長條；投手為「誘使揮棒」去標題並在下方接球質（皆依球種鏡頭）*/}
          {disc && disc.summary.swing_pct != null && (
            <Card className="flex flex-col">
              {role === "batting" && <h3 className="mb-3 text-sm font-medium text-muted">揮棒紀律</h3>}
              <PlateDisciplineBars points={pointsF} />
              {role === "pitching" && (() => {
                const q = pitchType === "all" ? disc.quality : (disc.quality_by_pt[pitchType] ?? {});
                const tiles: [string, number | null, string][] =
                  [["平均球速", q.avg_speed ?? null, "km/h"], ["平均延伸", q.avg_extension ?? null, "m"], ["平均放球高", q.avg_rel_height ?? null, "m"]];
                if (tiles.every(([, v]) => v == null)) return null;
                return (
                  <div className="mt-auto border-t border-line pt-3">
                    <div className="mb-2 text-xs text-muted">球質<span className="text-faint">（逐球追蹤樣本）</span></div>
                    <div className="grid grid-cols-3 gap-2">
                      {tiles.map(([l, v, u]) => (
                        <div key={l} className="card px-3 py-2 text-center">
                          <div className="text-[11px] text-muted">{l}</div>
                          <div className="mt-0.5 font-mono text-base tabular-nums text-ink">{v == null ? "—" : v}<span className="ml-0.5 text-[10px] text-faint">{u}</span></div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </Card>
          )}
        </div>
        {/* 進壘熱區 × 打擊成績（3×3＋四角 熱圖，依球種篩）*/}
        {disc && disc.points.length > 0 && (
          <div className="mt-6">
            <h3 className="mb-2 text-sm font-medium text-muted">進壘熱區 × 打擊成績</h3>
            <Card className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {(([["ev", "擊球初速 AVG"], ["la", "擊球仰角 AVG"], ["ba", "安打率"], ["hard", "強擊球%"], ["whiff", "揮空率"]] as [HeatMetric, string][])).map(([m, t]) => (
                <Grid3x3 key={m} points={pointsF} metric={m} title={t} />
              ))}
            </Card>
            <div className="mt-2 flex items-center justify-center gap-2 text-[10px] text-faint">
              低<span className="inline-block h-2 w-20 rounded-full" style={{ background: PR_GRADIENT }} />高
              <span>白＝本人均值 · 每格 n&lt;3 顯「—」· 捕手視角</span>
            </div>
          </div>
        )}
      </section>
  );
}

// 擊球品質與彈道（官方 /rankings 全季進階；非逐球樣本）
export function QualitySection({ advanced, role }: {
  advanced: { batting: StatRow | null; pitching: StatRow | null } | null;
  role: Role;
}) {
  const a = role === "batting" ? advanced?.batting : advanced?.pitching;
  const m = a?.metrics as Record<string, number> | undefined;
  if (!m || m.gbp == null) return null;
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-lg font-semibold text-ink">擊球品質與彈道<span className="ml-2 align-middle text-xs font-normal text-faint">本季 · 官方進階 2026 起</span></h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {QUALITY_GROUPS.map((g) => (
          <Card key={g.title} className="p-4">
            <div className="mb-2 text-sm font-semibold text-ink">{g.title}</div>
            {g.pie ? (
              <CompositionPie items={g.items} m={m} />
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {g.items.map((it) => (
                  <StatTile key={it.k} label={it.label}
                    value={m[it.k] == null ? "—" : it.fmt(m[it.k])} />
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </section>
  );
}

type ArsenalItem = { pitch_type: string; n: number; usage: number; avg_speed: number | null;
  avg_spin: number | null; whiff_pct: number | null; avg_ev: number | null };

// 球種卡：用量 + 均速 + 轉速 + 揮空%（TrackMan；球種為推算，見 models/pitch_type.py）
function ArsenalCards({ items }: { items: ArsenalItem[] }) {
  const ct = useChartTheme();
  if (!items.length) return null;
  return (
    <div className="mb-4 grid gap-3 sm:grid-cols-2">
      {items.map((a) => {
        const color = pitchColor(ct, a.pitch_type);
        return (
          <div key={a.pitch_type} className="rounded-lg border border-line p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                {a.pitch_type}
              </span>
              <span className="font-mono text-xs text-faint">{a.n} 球</span>
            </div>
            <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-line/60">
              <div className="h-full rounded-full" style={{ width: `${a.usage}%`, background: color }} />
            </div>
            <div className="grid grid-cols-4 gap-1 text-center">
              {([["用量", a.usage, "%"], ["均速", a.avg_speed, "km/h"],
                 ["轉速", a.avg_spin, "rpm"], ["揮空", a.whiff_pct, "%"]] as const).map(([l, v, u]) => (
                <div key={l}>
                  <div className="text-[10px] text-muted">{l}</div>
                  <div className="font-mono text-sm tabular-nums text-ink">
                    {v == null ? "—" : v}<span className="ml-0.5 text-[9px] text-faint">{u}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// 打者：擊球品質散點（仰角×初速） / 投手：球種卡 + 配球傾向（依球數）
export function BattedMixSection({ disc, pitchMix, arsenal, role }: {
  disc: Disc | null;
  pitchMix: { bucket: string; n: number; mix: { pitch_type: string; pct: number }[] }[] | null;
  arsenal: ArsenalItem[] | null;
  role: Role;
}) {
  const ct = useChartTheme();
  if (role === "batting") {
    if ((disc?.batted.length ?? 0) === 0) return null;
    return (
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-ink">擊球品質分布（仰角 × 初速）</h2>
        <Card>
          <LaEvScatter balls={disc!.batted} />
        </Card>
      </section>
    );
  }
  if ((pitchMix?.length ?? 0) === 0 && (arsenal?.length ?? 0) === 0) return null;
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-lg font-semibold text-ink">配球傾向<span className="ml-2 align-middle text-xs font-normal text-faint">TrackMan 逐球樣本</span></h2>
      <Card>
        <ArsenalCards items={arsenal ?? []} />
        {(pitchMix?.length ?? 0) > 0 && (() => {
          // 圖例＝各球數情境出現過的球種，依標準順序；段序也依此以維持顏色位置一致
          const legend = ptSort(pitchMix!.flatMap((b) => b.mix.map((m) => m.pitch_type)));
          return (
          <>
            <div className="mb-2 text-xs text-muted">依球數情境</div>
            <div className="space-y-2.5">
              {pitchMix!.map((b) => {
                const segs = legend
                  .map((t) => ({ t, pct: b.mix.find((m) => m.pitch_type === t)?.pct ?? 0 }))
                  .filter((s) => s.pct > 0);
                return (
                  <div key={b.bucket} className="flex items-center gap-2 text-xs">
                    <span className="w-16 shrink-0 text-muted">{b.bucket}</span>
                    <div className="flex h-5 flex-1 overflow-hidden rounded">
                      {segs.map((s) => (
                        <div key={s.t} className="flex items-center justify-center text-[10px] text-white"
                          style={{ width: `${s.pct}%`, background: pitchColor(ct, s.t) }} title={`${s.t} ${s.pct}%`}>
                          {s.pct >= 14 ? `${s.pct}%` : ""}
                        </div>
                      ))}
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-faint">{b.n}</span>
                  </div>
                );
              })}
            </div>
            <div className="mt-2.5 flex flex-wrap justify-center gap-3 text-[11px] text-muted">
              {legend.map((t) => (
                <span key={t} className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: pitchColor(ct, t) }} />{t}</span>
              ))}
            </div>
          </>
          );
        })()}
      </Card>
    </section>
  );
}

// ───────── 球種位移（ML-PT2 Phase1）：IVB×HB 散點 + 球種成績單 vs 聯盟 ─────────
// 位移為軌跡推算（ivb_cm/hb_cm）；聯盟平均已在後端依慣用手鏡像對齊本人視角。
export type Movement = {
  throws: string | null;
  points: { pt: string; hb: number; ivb: number }[];
  summary: { pt: string; n: number; usage: number; speed: number | null; spin: number | null;
    ivb: number | null; hb: number | null;
    lg: { speed: number | null; spin: number | null; ivb: number | null; hb: number | null } }[];
};

export function MovementSection({ mov }: { mov: Movement | null }) {
  const ct = useChartTheme();
  if (!mov || mov.points.length === 0) return null;
  const order = mov.summary.map((s) => s.pt);
  const ext = Math.ceil((Math.max(30, ...mov.points.map((p) => Math.max(Math.abs(p.hb), Math.abs(p.ivb)))) + 5) / 10) * 10;
  const lgMarks = mov.summary.filter((s) => s.lg.ivb != null && s.lg.hb != null)
    .map((s) => ({ pt: s.pt, hb: s.lg.hb!, ivb: s.lg.ivb! }));
  const vs = (v: number | null, l: number | null) => (
    <div className="leading-tight">
      <div className="font-semibold text-ink">{v ?? "—"}</div>
      <div className="text-[10px] text-faint">聯盟 {l ?? "—"}</div>
    </div>
  );
  const cols: Column<Movement["summary"][number]>[] = [
    {
      header: "球種", nowrap: true,
      cell: (r) => (
        <span className="flex items-center gap-1.5 font-sans text-ink">
          <i className="inline-block h-2 w-2 rounded-full" style={{ background: pitchColor(ct, r.pt) }} />{r.pt}
        </span>
      ),
    },
    { header: "球數", cell: (r) => String(r.n), align: "right" },
    { header: "使用率", cell: (r) => `${r.usage}%`, align: "right" },
    { header: "均速", cell: (r) => vs(r.speed, r.lg.speed), align: "right" },
    { header: "轉速", cell: (r) => vs(r.spin, r.lg.spin), align: "right" },
    { header: "IVB(cm)", cell: (r) => vs(r.ivb, r.lg.ivb), align: "right" },
    { header: "HB(cm)", cell: (r) => vs(r.hb, r.lg.hb), align: "right" },
  ];
  return (
    <section className="mb-8">
      <Card>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-medium text-muted">球種位移（軌跡推算・{mov.points.length} 球）</h3>
          <span className="text-[10px] text-faint">
            ◆＝聯盟同球種平均{mov.throws === "左投" ? "（已鏡像至左投視角）" : ""}・IVB=垂直誘導位移、HB=橫向位移
          </span>
        </div>
        <div className="grid gap-4 lg:grid-cols-[minmax(280px,400px)_1fr]">
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={ct.line} />
              <XAxis type="number" dataKey="hb" domain={[-ext, ext]}
                tick={{ fontSize: 10, fill: ct.faint }} tickLine={false} axisLine={false}
                label={{ value: "HB (cm)", position: "insideBottomRight", offset: -2, fontSize: 10, fill: ct.faint }} />
              <YAxis type="number" dataKey="ivb" domain={[-ext, ext]}
                tick={{ fontSize: 10, fill: ct.faint }} tickLine={false} axisLine={false}
                label={{ value: "IVB", angle: -90, position: "insideLeft", fontSize: 10, fill: ct.faint }} />
              <ReferenceLine x={0} stroke={ct.lineStrong} />
              <ReferenceLine y={0} stroke={ct.lineStrong} />
              <ChartTip contentStyle={chartTooltip(ct)} labelFormatter={() => ""}
                formatter={(v: number, name: string) => [`${v} cm`, name === "hb" ? "HB" : "IVB"]} />
              {order.map((pt) => (
                <Scatter key={pt} name={pt} data={mov.points.filter((p) => p.pt === pt)}
                  fill={pitchColor(ct, pt)} fillOpacity={0.45} isAnimationActive={false} />
              ))}
              {/* 聯盟平均：菱形、描邊突出 */}
              <Scatter data={lgMarks} shape="diamond" isAnimationActive={false}>
                {lgMarks.map((m, i) => <Cell key={i} fill={pitchColor(ct, m.pt)} stroke={ct.ink} strokeWidth={1.2} />)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <DataTable columns={cols} rows={mov.summary} rowKey={(r) => r.pt} dense bare className="self-start" />
        </div>
      </Card>
    </section>
  );
}
