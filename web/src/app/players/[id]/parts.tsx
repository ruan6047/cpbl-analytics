"use client";

// 球員頁純展示元件：無跨區 state，僅收 props。
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { LetterBadge } from "@/components/ui";
import { type StatRow } from "@/lib/client";
import { fmtIP } from "@/lib/format";
import { codeFromName, eraBadge, teamShort } from "@/lib/teams";
import { PITCH_TYPES, type PitchType, type Role, type Tenure, eraOf, f3, ipOf, ipText, n0, numOf } from "./lib";

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

// 組成型百分位 → 甜甜圈圖 + 圖例（彈道分布/拉打方向；值總和≈100%）
const PIE_COLORS = ["#1B4DA1", "#3B82C4", "#E8842B", "#9AA3AF"];
export function CompositionPie({ items, m }: { items: { k: string; label: string }[]; m: Record<string, number> }) {
  const data = items
    .map((it, i) => ({ name: it.label, value: m[it.k] == null ? 0 : +(m[it.k] * 100).toFixed(1), color: PIE_COLORS[i % PIE_COLORS.length] }))
    .filter((d) => d.value > 0);
  if (!data.length) return <p className="py-6 text-center text-xs text-faint">無資料</p>;
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
  return (
    <div className={`inline-flex gap-1 rounded-lg bg-surface-2 p-1 ${vertical ? "flex-col" : ""}`}>
      {opts.map((o) => (
        <button key={o.v} onClick={() => set(o.v)}
          className={`rounded-md px-3 py-1 text-sm transition ${v === o.v ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
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

export function PitchTypeToggle({ value, onChange }: { value: PitchType; onChange: (v: PitchType) => void }) {
  return (
    <div className="flex gap-1 text-[11px]">
      {PITCH_TYPES.map(([v, l]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`rounded px-2 py-0.5 ${value === v ? "bg-ink text-white" : "bg-surface-2 text-muted"}`}>{l}</button>
      ))}
    </div>
  );
}

export function VsTeamTable({ items, role }: { items: StatRow[]; role: Role }) {
  const cols: { h: string; cell: (r: StatRow) => string; tone?: string }[] = role === "batting"
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
  return (
    <div className="max-h-[230px] overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-surface text-left text-muted">
          <tr>
            <th className="py-1 font-medium">對手</th>
            {cols.map((c) => <th key={c.h} className="py-1 text-right font-medium">{c.h}</th>)}
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {items.map((r) => (
            <tr key={String(r.fight_team_name)} className="border-t border-line">
              <td className="py-1.5 font-sans text-ink">{teamShort(codeFromName(String(r.fight_team_name))) || String(r.fight_team_name)}</td>
              {cols.map((c) => <td key={c.h} className={`py-1.5 text-right ${c.tone ?? ""}`}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CareerTable({ seasons, role }: { seasons: StatRow[]; role: Role }) {
  const cols: { h: string; cell: (r: StatRow) => string; tone?: string }[] = role === "batting"
    ? [{ h: "G", cell: (r) => n0(r.g) }, { h: "PA", cell: (r) => n0(r.pa) },
       { h: "AVG", cell: (r) => f3(numOf(r.avg)) }, { h: "OBP", cell: (r) => f3(numOf(r.obp)) },
       { h: "SLG", cell: (r) => f3(numOf(r.slg)) }, { h: "OPS", cell: (r) => f3(numOf(r.ops)), tone: "text-ink" },
       { h: "HR", cell: (r) => n0(r.hr) }, { h: "打點", cell: (r) => n0(r.rbi) }, { h: "盜壘", cell: (r) => n0(r.sb) }]
    : [{ h: "G", cell: (r) => n0(r.g) }, { h: "先發", cell: (r) => n0(r.gs) },
       { h: "勝-敗", cell: (r) => `${r.w ?? 0}-${r.l ?? 0}` }, { h: "救援", cell: (r) => n0(r.sv) },
       { h: "局數", cell: (r) => fmtIP(r.ip as number | string | null) }, { h: "ERA", cell: (r) => numOf(r.era)?.toFixed(2) ?? "—", tone: "text-ink" },
       { h: "WHIP", cell: (r) => numOf(r.whip)?.toFixed(2) ?? "—" }, { h: "三振", cell: (r) => n0(r.so) },
       { h: "K9", cell: (r) => numOf(r.k9)?.toFixed(2) ?? "—" }];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">年度</th>
            <th className="px-3 py-2 font-medium">球隊</th>
            {cols.map((c) => <th key={c.h} className="px-3 py-2 text-right font-medium">{c.h}</th>)}
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {seasons.map((r) => (
            <tr key={String(r.year)} className="border-t border-line">
              <td className="px-3 py-2 font-sans text-ink">{String(r.year)}</td>
              <td className="px-3 py-2 font-sans text-muted">{String(r.teams ?? "—")}</td>
              {cols.map((c) => <td key={c.h} className={`px-3 py-2 text-right ${c.tone ?? ""}`}>{c.cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SplitsTable({ rows, role }: { rows: StatRow[]; role: Role }) {
  const heads = role === "batting"
    ? ["分項", "打席", "打數", "安打", "全壘打", "打點", "四壞", "三振", "打擊率", "OPS"]
    : ["分項", "局數", "面對", "被安", "被轟", "四壞", "三振", "自責", "ERA"];
  return (
    <table className="w-full text-sm">
      <thead className="bg-surface-2 text-left text-muted">
        <tr>{heads.map((h) => <th key={h} className="whitespace-nowrap px-2.5 py-2.5 font-medium">{h}</th>)}</tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-line hover:bg-surface-2">
            <td className="whitespace-nowrap px-2.5 py-2 font-sans text-ink">{String(r.item_name)}</td>
            {role === "batting" ? (
              <>
                <td className="px-2.5 py-2">{String(r.plate_appearances ?? "—")}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.at_bats ?? "—")}</td>
                <td className="px-2.5 py-2">{String(r.hits ?? "—")}</td>
                <td className="px-2.5 py-2">{String(r.home_runs ?? "—")}</td>
                <td className="px-2.5 py-2">{String(r.rbi ?? "—")}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.bb ?? "—")}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.so ?? "—")}</td>
                <td className="px-2.5 py-2">{f3(r.avg)}</td>
                <td className="px-2.5 py-2 text-accent">{f3(r.ops)}</td>
              </>
            ) : (
              <>
                <td className="px-2.5 py-2">{ipOf(r)?.toFixed(1) ?? "—"}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.plate_appearances ?? "—")}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.hits ?? "—")}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.home_runs ?? "—")}</td>
                <td className="px-2.5 py-2 text-muted">{String(r.bb ?? "—")}</td>
                <td className="px-2.5 py-2">{String(r.so ?? "—")}</td>
                <td className="px-2.5 py-2 text-accent">{String(r.earned_runs ?? "—")}</td>
                <td className="px-2.5 py-2 text-accent">{eraOf(r)?.toFixed(2) ?? "—"}</td>
              </>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
