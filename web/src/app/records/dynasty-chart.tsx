"use client";

// 冠軍王朝榜：甜甜圈圖（各球團佔 36 座冠軍比例，隊色 slice）＋兩欄資訊面板
// （王朝榜圖例 + 近年冠軍時間軸）。指到 slice 顯示該隊奪冠年份。
import Link from "next/link";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Pill, TeamBadge } from "@/components/ui";
import { chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { teamColor } from "@/lib/teams";

export type DynastyRow = { team_code: string; team: string | null; titles: number; years: number[]; rk: number };
export type RegularRow = { code: string; name: string | null; win_pct: number | null; w: number; l: number };

const f3 = (v: number | null) => (v == null ? "—" : v.toFixed(3).replace(/^0/, ""));

function longestStreak(years: number[]): number {
  const ys = [...new Set(years)].sort((a, b) => a - b);
  let best = 1, run = 1;
  for (let i = 1; i < ys.length; i++) {
    run = ys[i] === ys[i - 1] + 1 ? run + 1 : 1;
    if (run > best) best = run;
  }
  return best;
}

function YearTooltip({ active, payload }: { active?: boolean; payload?: { payload: DynastyRow }[] }) {
  const ct = useChartTheme();
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{ ...chartTooltip(ct), padding: "6px 10px", maxWidth: 220 }}>
      <div style={{ fontWeight: 700 }}>{d.team}・{d.titles} 座冠軍</div>
      <div style={{ color: ct.muted, marginTop: 2 }}>{d.years.join("、")}</div>
    </div>
  );
}

// slice 上直接標奪冠數（白字，位於環帶中央）。
function sliceLabel({ cx, cy, midAngle, innerRadius, outerRadius, value }: {
  cx: number; cy: number; midAngle: number; innerRadius: number; outerRadius: number; value: number;
}) {
  const rad = Math.PI / 180;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * rad);
  const y = cy + r * Math.sin(-midAngle * rad);
  return (
    <text x={x} y={y} fill="#fff" textAnchor="middle" dominantBaseline="central"
          style={{ fontWeight: 700, fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
      {value}
    </text>
  );
}

export function DynastyChart({ rows, regular }: { rows: DynastyRow[]; regular: RegularRow[] }) {
  const total = rows.reduce((s, r) => s + r.titles, 0);
  return (
    <div className="card grid items-start gap-5 p-4 sm:grid-cols-[190px_1fr] lg:grid-cols-[190px_minmax(0,1fr)_minmax(0,1fr)]">
      <div className="relative mx-auto h-48 w-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="titles" nameKey="team" innerRadius="58%" outerRadius="95%" paddingAngle={2} stroke="none" label={sliceLabel} labelLine={false} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.team_code} fill={teamColor(r.team_code)} />)}
            </Pie>
            <Tooltip content={<YearTooltip />} wrapperStyle={{ zIndex: 20 }} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 z-0 flex flex-col items-center justify-center">
          <span className="font-mono text-3xl font-extrabold tabular-nums text-ink">{total}</span>
          <span className="text-[11px] text-muted">座冠軍・{rows.length} 隊</span>
        </div>
      </div>

      {/* 欄一：王朝榜圖例 */}
      <ul className="space-y-1.5 self-center">
        {rows.map((r) => {
          const streak = longestStreak(r.years);
          return (
            <li key={r.team_code} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: teamColor(r.team_code) }} />
              <Link href={`/teams/${r.team_code}`} className="font-sans font-medium hover:underline">
                <TeamBadge code={r.team_code} name={r.team} size={16} />
              </Link>
              {r.rk === 1 && <Pill tone="up">榜首</Pill>}
              {streak >= 2 && <Pill tone="muted" className="!bg-accent/15 !text-accent">{streak} 連霸</Pill>}
            </li>
          );
        })}
      </ul>

      {/* 欄二：例行賽勝率（全史 kind A）——與冠軍分布對照 */}
      <div className="hidden self-center lg:block">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">例行賽勝率・全史</div>
        <ul className="space-y-1.5">
          {regular.map((t) => (
            <li key={t.code} className="flex items-center gap-2 text-sm">
              <Link href={`/teams/${t.code}`} className="font-sans font-medium hover:underline">
                <TeamBadge code={t.code} name={t.name} size={16} />
              </Link>
              <span className="ml-auto flex items-baseline gap-2 tabular-nums">
                <span className="text-[11px] text-faint">{t.w}–{t.l}</span>
                <span className="w-9 text-right font-bold text-ink">{f3(t.win_pct)}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
