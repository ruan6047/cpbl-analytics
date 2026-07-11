"use client";

// 球員頁純展示元件：無跨區 state，僅收 props。
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { EmptyState, LetterBadge, divBg } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import { PIE_COLORS } from "@/lib/chart-theme";
import { type StatRow } from "@/lib/client";
import { fmtIP } from "@/lib/format";
import { codeFromName, eraBadge, teamShort } from "@/lib/teams";
import { type PitchType, type Role, type Tenure, eraOf, f3, ipOf, ipText, n0, numOf } from "./lib";

// hero 內「教練／行政」所屬隊伍列：依隊聚合年份、職稱進 tooltip（比照球員所屬隊伍）
export function TenureChips({ label, tenures }: { label: string; tenures: Tenure[] }) {
  const agg = new Map<string, { team: string; from: number | null; to: number | null; roles: Set<string>; ongoing: boolean }>();
  for (const t of tenures) {
    const g = agg.get(t.team) ?? { team: t.team, from: t.from, to: t.to, roles: new Set<string>(), ongoing: false };
    if (t.from != null) g.from = g.from == null ? t.from : Math.min(g.from, t.from);
    if (t.to == null && t.from != null) g.ongoing = true;
    else if (t.to != null) g.to = g.to == null ? t.to : Math.max(g.to, t.to);
    if (t.role) g.roles.add(t.role);
    agg.set(t.team, g);
  }
  const list = [...agg.values()].sort((a, b) => (a.from ?? 9999) - (b.from ?? 9999));
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] text-faint">{label}</span>
      {list.map((t) => {
        const b = eraBadge(t.team, codeFromName(t.team) ?? "");
        const yr = t.from == null ? "" : t.ongoing ? `'${String(t.from).slice(2)}–`
          : t.from === t.to ? `'${String(t.from).slice(2)}`
          : `'${String(t.from).slice(2)}–'${String(t.to).slice(2)}`;
        return (
          <span key={t.team}
            className="inline-flex items-center gap-1 rounded-full py-0.5 pl-0.5 pr-2 text-[11px] font-medium"
            style={{ background: `${b.color}1a`, color: b.color }}
            title={`${t.team} ${label}${t.roles.size ? `（${[...t.roles].join("、")}）` : ""}`}>
            <LetterBadge meta={b} round />
            {t.team}
            {yr && <span className="font-mono tabular-nums opacity-70">{yr}</span>}
          </span>
        );
      })}
    </div>
  );
}

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

export function Tabs<T extends string>({ opts, v, set, vertical = false }: { opts: { v: T; label: string }[]; v: T; set: (x: T) => void; vertical?: boolean }) {
  const handleSelect = (val: T) => {
    if (typeof document !== "undefined" && (document as any).startViewTransition) {
      (document as any).startViewTransition(() => set(val));
    } else {
      set(val);
    }
  };
  return (
    <div className={`inline-flex gap-1 rounded-lg bg-surface-2 p-1 ${vertical ? "flex-col" : ""}`}>
      {opts.map((o) => (
        <button key={o.v} onClick={() => handleSelect(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${v === o.v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// 最佳單季：獨立區塊，每項一張卡（指標／數值／年份）
export function BestSeasonGrid({ items }: { items: { label: string; value: string; year: number }[] }) {
  if (!items.length) return null;
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-lg font-semibold text-ink">最佳單季</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {items.map((b) => (
          <div key={b.label} className="card flex flex-col items-center p-4 text-center">
            <div className="text-xs text-muted">{b.label}</div>
            <div className="mt-1 font-mono text-2xl font-bold tabular-nums text-accent">{b.value}</div>
            <div className="mt-1 rounded-full bg-surface-2 px-2 text-[11px] text-muted">{b.year} 年</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PitchTypeToggle({ value, onChange, types }: {
  value: PitchType; onChange: (v: PitchType) => void; types: string[];
}) {
  return (
    <div className="flex flex-wrap gap-1 text-[11px]">
      {(["all", ...types] as PitchType[]).map((v) => (
        <button key={v} onClick={() => onChange(v)}
          className={`rounded px-2 py-0.5 ${value === v ? "bg-ink text-paper" : "bg-surface-2 text-muted"}`}>
          {v === "all" ? "全部" : v}</button>
      ))}
    </div>
  );
}

export function VsTeamTable({ items, role }: { items: StatRow[]; role: Role }) {
  const stat: { h: string; cell: (r: StatRow) => string; tone?: string }[] = role === "batting"
    ? [{ h: "PA", cell: (r) => n0(r.plate_appearances) },
       { h: "安打", cell: (r) => n0(r.hits) },
       { h: "HR", cell: (r) => n0(r.home_runs) },
       { h: "打點", cell: (r) => n0(r.rbi) },
       { h: "OPS", cell: (r) => f3(numOf(r.ops)), tone: "text-ink" }]
    : [{ h: "局數", cell: ipText },
       { h: "ERA", cell: (r) => numOf(r.era)?.toFixed(2) ?? "—", tone: "text-ink" },
       { h: "WHIP", cell: (r) => numOf(r.whip)?.toFixed(2) ?? "—" },
       { h: "被安", cell: (r) => n0(r.hits) },
       { h: "三振", cell: (r) => n0(r.so) }];
  const columns: Column<StatRow>[] = [
    { header: "對手", cell: (r) => teamShort(codeFromName(String(r.fight_team_name))) || String(r.fight_team_name), nowrap: true, className: "font-sans text-ink" },
    ...stat.map((c): Column<StatRow> => ({ header: c.h, cell: c.cell, align: "right", className: c.tone })),
  ];
  // Card 內 → bare（不重畫卡殼）；長列表 → 垂直捲動 + 表頭 sticky
  return <DataTable columns={columns} rows={items} rowKey={(r) => String(r.fight_team_name)} dense bare maxHeight="230px" />;
}

export function CareerTable({ seasons, role }: { seasons: StatRow[]; role: Role }) {
  const stat: { h: string; cell: (r: StatRow) => string; tone?: string }[] = role === "batting"
    ? [{ h: "G", cell: (r) => n0(r.g) }, { h: "PA", cell: (r) => n0(r.pa) },
       { h: "AVG", cell: (r) => f3(numOf(r.avg)) }, { h: "OBP", cell: (r) => f3(numOf(r.obp)) },
       { h: "SLG", cell: (r) => f3(numOf(r.slg)) }, { h: "OPS", cell: (r) => f3(numOf(r.ops)), tone: "text-ink" },
       { h: "HR", cell: (r) => n0(r.hr) }, { h: "打點", cell: (r) => n0(r.rbi) }, { h: "盜壘", cell: (r) => n0(r.sb) }]
    : [{ h: "G", cell: (r) => n0(r.g) }, { h: "先發", cell: (r) => n0(r.gs) },
       { h: "勝-敗", cell: (r) => `${r.w ?? 0}-${r.l ?? 0}` }, { h: "救援", cell: (r) => n0(r.sv) },
       { h: "局數", cell: (r) => fmtIP(r.ip as number | string | null) }, { h: "ERA", cell: (r) => numOf(r.era)?.toFixed(2) ?? "—", tone: "text-ink" },
       { h: "WHIP", cell: (r) => numOf(r.whip)?.toFixed(2) ?? "—" }, { h: "三振", cell: (r) => n0(r.so) },
       { h: "K9", cell: (r) => numOf(r.k9)?.toFixed(2) ?? "—" }];
  const columns: Column<StatRow>[] = [
    { header: "年度", cell: (r) => String(r.year), sticky: true, nowrap: true, className: "font-sans text-ink" },
    { header: "球隊", cell: (r) => String(r.teams ?? "—"), nowrap: true, className: "font-sans text-muted" },
    ...stat.map((c): Column<StatRow> => ({ header: c.h, cell: c.cell, align: "right", className: c.tone })),
  ];
  return <DataTable columns={columns} rows={seasons} rowKey={(r) => String(r.year)} dense />;
}

export function SplitsTable({ rows, role }: { rows: StatRow[]; role: Role }) {
  // 組內發散上色：同家族各桶（主/客、各局數…）間對比（投手 ERA 低為佳）
  const numsOf = (f: (r: StatRow) => number | null | undefined) => rows.map(f);
  const avgs = numsOf((r) => r.avg as number | null);
  const opss = numsOf((r) => r.ops as number | null);
  const eras = numsOf((r) => eraOf(r));
  const columns: Column<StatRow>[] = role === "batting"
    ? [
        { header: "分項", cell: (r) => String(r.item_name), nowrap: true, className: "font-sans text-ink" },
        { header: "打席", cell: (r) => String(r.plate_appearances ?? "—") },
        { header: "打數", cell: (r) => String(r.at_bats ?? "—"), className: "text-muted" },
        { header: "安打", cell: (r) => String(r.hits ?? "—") },
        { header: "全壘打", cell: (r) => String(r.home_runs ?? "—") },
        { header: "打點", cell: (r) => String(r.rbi ?? "—") },
        { header: "四壞", cell: (r) => String(r.bb ?? "—"), className: "text-muted" },
        { header: "三振", cell: (r) => String(r.so ?? "—"), className: "text-muted" },
        { header: "打擊率", cell: (r) => f3(r.avg), cellStyle: (r) => divBg(r.avg as number | null, avgs) },
        { header: "OPS", cell: (r) => f3(r.ops), className: "font-medium text-ink", cellStyle: (r) => divBg(r.ops as number | null, opss) },
      ]
    : [
        { header: "分項", cell: (r) => String(r.item_name), nowrap: true, className: "font-sans text-ink" },
        { header: "局數", cell: (r) => ipOf(r)?.toFixed(1) ?? "—" },
        { header: "面對", cell: (r) => String(r.plate_appearances ?? "—"), className: "text-muted" },
        { header: "被安", cell: (r) => String(r.hits ?? "—"), className: "text-muted" },
        { header: "被轟", cell: (r) => String(r.home_runs ?? "—"), className: "text-muted" },
        { header: "四壞", cell: (r) => String(r.bb ?? "—"), className: "text-muted" },
        { header: "三振", cell: (r) => String(r.so ?? "—") },
        { header: "自責", cell: (r) => String(r.earned_runs ?? "—"), className: "text-muted" },
        { header: "ERA", cell: (r) => eraOf(r)?.toFixed(2) ?? "—", className: "font-medium text-ink", cellStyle: (r) => divBg(eraOf(r), eras, true) },
      ];
  return <DataTable columns={columns} rows={rows} rowKey={(r) => String(r.item_name)} dense bare />;
}
