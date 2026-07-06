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
export type AxisComp = { label: string; weight: number; pr: number };
export type Axis = { key: string; label: string; pr: number | null; grade: string | null; components: AxisComp[] };
export type Card = { available: boolean; role: string; scope?: string; has_advanced?: boolean; signature?: string | null; axes?: Axis[]; overall?: { pr: number; grade: string } };

// 軸名 hover 提示：該軸由哪些指標、各佔多少權重綜合而成。
function axisTitle(a: Axis | undefined): string {
  if (!a) return "";
  if (!a.components.length) return `${a.label}：無資料`;
  return `${a.label}（PR ${a.pr}）＝ ` + a.components.map((c) => `${c.label} ${c.weight}%`).join(" · ");
}

// 遊戲感分段等級色（パワプロ 風）：S金 A紅 B橘 C黃 D綠 E青 F/G灰。
const GRADE_COLOR: Record<string, string> = {
  S: "#E6B422", A: "#D23A3A", B: "#E8842B", C: "#E0C53A",
  D: "#4CAF50", E: "#3B82C4", F: "#7C8696", G: "#9AA3AF",
};
const gradeColor = (grade: string) => GRADE_COLOR[grade] ?? "#9AA3AF";

export function GradeChip({ grade, size = "sm" }: { grade: string | null; size?: "sm" | "lg" }) {
  const bg = gradeColor(grade ?? "G");
  const dim = size === "lg" ? "h-8 w-8 rounded-lg text-base" : "h-5 w-5 rounded text-[11px]";
  if (!grade) return <span className={`inline-flex items-center justify-center text-faint ${dim}`}>—</span>;
  return (
    <span
      className={`inline-flex items-center justify-center font-extrabold ${dim}`}
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
  hideNote = false,
}: {
  card: Card;
  title?: string;
  color?: string;
  compact?: boolean;
  hideNote?: boolean;
}) {
  if (!card?.available || !card.axes) return null;
  const axes = card.axes;
  const data = axes.map((a) => ({ axis: a.label, pr: a.pr ?? 0 }));
  const byLabel = Object.fromEntries(axes.map((a) => [a.label, a]));
  // 自訂軸名刻度：附 SVG <title> → 滑鼠移到軸名即顯示組成與權重。
  const renderTick = (props: { x: number; y: number; textAnchor: string; payload: { value: string } }) => {
    const a = byLabel[props.payload.value];
    const g = a?.grade ?? null;
    return (
      <text x={props.x} y={props.y} textAnchor={props.textAnchor} dominantBaseline="central"
        fontSize={11} fontWeight={600} style={{ cursor: "help" }} fill={g ? gradeColor(g) : "#9AA3AF"}>
        <title>{axisTitle(a)}</title>
        {props.payload.value}
      </text>
    );
  };
  return (
    <div>
      {title && (
        <div className="mb-1 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
            {title}
            {card.signature && (
              <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold text-accent"
                title={card.role === "pitching"
                  ? "投球風格：最突出的出局方式（三振／滾地／飛球）"
                  : "打擊特色：進攻工具中最突出者（多項頂尖＝全能）"}>
                {card.signature}型
              </span>
            )}
          </span>
          {card.overall && (
            <span className="flex items-center gap-1 text-xs text-muted">
              總評 <GradeChip grade={card.overall.grade} />
            </span>
          )}
        </div>
      )}
      <div className={compact ? "h-36" : "h-64"} role="img"
        aria-label={`${title ?? "能力值"}雷達圖，各項為全聯盟百分位（越外圈越強）`}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius={compact ? "70%" : "78%"}>
            <PolarGrid stroke="var(--color-line, #e2e8f0)" />
            <PolarAngleAxis dataKey="axis" tick={compact ? { fontSize: 10, fill: "#64748b" } : renderTick} />
            <Radar dataKey="pr" stroke={color} fill={color} fillOpacity={0.35} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      {!compact && !hideNote && (
        <p className="mt-1 text-center text-[10px] text-faint">
          滑鼠移到軸名看綜合組成與權重{card.has_advanced ? "；本季含官方進階數據" : ""}。
        </p>
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
    home: a.pr ?? 0,
    away: away.axes?.[i]?.pr ?? 0,
  }));
  return (
    <div className="h-44" role="img" aria-label="兩位先發投手能力值雷達疊圖，各項為全聯盟百分位">
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
