"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { contrastText } from "@/lib/teams";

// 能力值卡：以全史生涯 rate 的全聯盟百分位 [PR] 畫遊戲風雷達 + 等級條。
// 資料皆我們自算的客觀指標，等級 S–G 純由 PR 換算（非抄遊戲數值）。
export type Axis = { key: string; label: string; fmt: string; source: string; value: number | null; pr: number; grade: string };
export type Card = { available: boolean; role: string; axes?: Axis[]; overall?: { pr: number; grade: string } };

function fmtVal(fmt: string, v: number | null): string {
  if (v === null) return "—";
  if (fmt === "avg" || fmt === "ops" || fmt === "iso") return v.toFixed(3).replace(/^0\./, ".");
  if (fmt === "pct") return `${(v * 100).toFixed(0)}%`;
  if (fmt === "int") return v.toFixed(0);
  return v.toFixed(2); // rate（K9 / BB9 / ERA / IP per G）
}

// 遊戲感分段等級色（パワプロ 風）：S金 A紅 B橘 C黃 D綠 E青 F/G灰。
const GRADE_COLOR: Record<string, string> = {
  S: "#E6B422", A: "#D23A3A", B: "#E8842B", C: "#E0C53A",
  D: "#4CAF50", E: "#3B82C4", F: "#7C8696", G: "#9AA3AF",
};
const gradeColor = (grade: string) => GRADE_COLOR[grade] ?? "#9AA3AF";

export function GradeChip({ grade }: { grade: string }) {
  const bg = gradeColor(grade);
  return (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded text-[11px] font-extrabold"
      style={{ background: bg, color: contrastText(bg) }}
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
              總評 <GradeChip grade={card.overall.grade} />
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
        <>
          <div className="mt-2 space-y-1.5">
            {card.axes.map((a) => (
              <div key={a.key} className="flex items-center gap-2 text-xs">
                <span
                  title={`${a.label} ← ${a.source}`}
                  className="w-12 shrink-0 cursor-help text-muted underline decoration-line decoration-dotted underline-offset-2"
                >
                  {a.label}
                </span>
                <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full" style={{ width: `${a.pr}%`, background: gradeColor(a.grade) }} />
                </div>
                <GradeChip grade={a.grade} />
                <span className="w-20 shrink-0 text-right font-mono tabular-nums text-faint">
                  {fmtVal(a.fmt, a.value)}
                </span>
              </div>
            ))}
          </div>
          {/* 各軸由哪個指標換算（回答「雷達數值怎麼來」）*/}
          <p className="mt-2 text-[10px] leading-relaxed text-faint">
            {card.axes.map((a) => `${a.label}=${a.source.replace(/（.*）/, "")}`).join("　·　")}
          </p>
        </>
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
