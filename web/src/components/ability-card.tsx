"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { prColor } from "@/components/ui";

// 能力值卡：以全史生涯 rate 的全聯盟百分位 [PR] 畫遊戲風雷達 + 等級條。
// 資料皆我們自算的客觀指標，等級 S–G 純由 PR 換算（非抄遊戲數值）。
export type Axis = { key: string; label: string; fmt: string; value: number | null; pr: number; grade: string };
export type Card = { available: boolean; role: string; axes?: Axis[]; overall?: { pr: number; grade: string } };

function fmtVal(fmt: string, v: number | null): string {
  if (v === null) return "—";
  if (fmt === "avg" || fmt === "ops" || fmt === "iso") return v.toFixed(3).replace(/^0\./, ".");
  if (fmt === "pct") return `${(v * 100).toFixed(0)}%`;
  if (fmt === "int") return v.toFixed(0);
  return v.toFixed(2); // rate（K9 / BB9 / ERA / IP per G）
}

// 等級色：沿用 PR 發散色階（藍→灰→紅），與球員頁百分位條一致。
const gradeColor = (pr: number) => prColor(pr);

export function GradeChip({ grade, pr }: { grade: string; pr: number }) {
  return (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded text-[11px] font-extrabold text-white"
      style={{ background: gradeColor(pr) }}
    >
      {grade}
    </span>
  );
}

// 單人能力值卡（雷達 + 等級條）。compact=只畫雷達（對戰卡並排用）。
export function AbilityCard({
  card,
  title,
  color = "#1B4DA1",
  compact = false,
}: {
  card: Card;
  title?: string;
  color?: string;
  compact?: boolean;
}) {
  if (!card?.available || !card.axes) return null;
  const data = card.axes.map((a) => ({ axis: a.label, pr: a.pr }));
  return (
    <div>
      {title && (
        <div className="mb-1 flex items-center justify-between">
          <span className="text-sm font-medium text-ink">{title}</span>
          {card.overall && (
            <span className="flex items-center gap-1 text-xs text-muted">
              總評 <GradeChip grade={card.overall.grade} pr={card.overall.pr} />
            </span>
          )}
        </div>
      )}
      <div className={compact ? "h-36" : "h-52"}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="var(--color-line, #e2e8f0)" />
            <PolarAngleAxis dataKey="axis" tick={{ fontSize: 11, fill: "var(--color-muted, #64748b)" }} />
            <Radar dataKey="pr" stroke={color} fill={color} fillOpacity={0.35} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      {!compact && (
        <div className="mt-2 space-y-1.5">
          {card.axes.map((a) => (
            <div key={a.key} className="flex items-center gap-2 text-xs">
              <span className="w-12 shrink-0 text-muted">{a.label}</span>
              <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full" style={{ width: `${a.pr}%`, background: gradeColor(a.pr) }} />
              </div>
              <GradeChip grade={a.grade} pr={a.pr} />
              <span className="w-12 shrink-0 text-right font-mono tabular-nums text-faint">
                {fmtVal(a.fmt, a.value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 兩人雷達疊圖（對戰卡：主投 vs 客投）。
export function AbilityRadarVS({
  home,
  away,
  homeColor = "#C4122F",
  awayColor = "#1B4DA1",
}: {
  home: Card;
  away: Card;
  homeColor?: string;
  awayColor?: string;
}) {
  if (!home?.available || !away?.available || !home.axes) return null;
  const data = home.axes.map((a, i) => ({
    axis: a.label,
    home: a.pr,
    away: away.axes?.[i]?.pr ?? 0,
  }));
  return (
    <div className="h-44">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke="var(--color-line, #e2e8f0)" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 10, fill: "var(--color-muted, #64748b)" }} />
          <Radar dataKey="away" stroke={awayColor} fill={awayColor} fillOpacity={0.25} />
          <Radar dataKey="home" stroke={homeColor} fill={homeColor} fillOpacity={0.25} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
