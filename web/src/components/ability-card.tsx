"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { contrastText } from "@/lib/teams";
import { gradeColor, useChartTheme } from "@/lib/chart-theme";
import { Tooltip } from "./tooltip";

// 能力值卡：以全史生涯 rate 的全聯盟百分位 [PR] 畫遊戲風雷達 + 等級條。
// 資料皆我們自算的客觀指標，等級 S–G 純由 PR 換算（非抄遊戲數值）。
export type AxisComp = { label: string; weight: number; pr: number };
export type Axis = { key: string; label: string; pr: number | null; grade: string | null; components: AxisComp[] };
export type Card = { available: boolean; role: string; scope?: string; has_advanced?: boolean; signature?: string | null; axes?: Axis[]; overall?: { pr: number; grade: string } };

// 方法論說明（自製指標誠實揭露；雷達右上角 ? 觸發，hover/點擊皆可）。
function methodNote(card: Card) {
  const scopeLine = card.scope === "season"
    ? "本季尺度：母體＝本季 打者 AB≥50／投手 IP≥20 的球員。"
    : "生涯尺度：母體＝生涯累積 打者 AB≥300／投手 IP≥100 的球員。";
  return (
    <div className="space-y-1">
      <p className="font-semibold">本站自製能力指標</p>
      <p>各軸＝該面向 rate 數據在全聯盟的百分位 [PR]（0–100，越外圈越強），全部由本站自算，並非遊戲或官方數值。</p>
      <p>{scopeLine}</p>
      <p>等級由 PR 換算：S≥90 · A≥80 · B≥65 · C≥50 · D≥35 · E≥20 · F≥10 · G。</p>
      <p className="opacity-70">滑鼠移到（或點擊）軸名可看該軸的組成指標與權重{card.has_advanced ? "；本季卡已摻入官方進階數據" : ""}。</p>
    </div>
  );
}

// 軸名提示內容：該軸由哪些指標、各佔多少權重綜合而成。
function axisTipContent(a: Axis) {
  if (!a.components.length) return <p>{a.label}：無資料</p>;
  return (
    <div className="space-y-0.5">
      <p className="font-semibold">{a.label}　PR {a.pr}{a.grade ? `（${a.grade}）` : ""}</p>
      {a.components.map((c) => (
        <p key={c.label} className="flex justify-between gap-3">
          <span>{c.label}</span>
          <span className="font-mono tabular-nums">{c.weight}%　PR {c.pr}</span>
        </p>
      ))}
      {a.components.length > 1 && <p className="opacity-70">依權重加權平均後換算等級</p>}
    </div>
  );
}

// 等級色（S金 A紅 B橘 C黃 D綠 E青 F/G灰）由色票 API gradeColor() 供給（單一來源）。
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
  color,
  compact = false,
  hideNote = false,
}: {
  card: Card;
  title?: string;
  color?: string;
  compact?: boolean;
  hideNote?: boolean;
}) {
  const ct = useChartTheme();
  const radarColor = color ?? ct.cpbl;
  if (!card?.available || !card.axes) return null;
  const axes = card.axes;
  const data = axes.map((a) => ({ axis: a.label, pr: a.pr ?? 0 }));
  const byLabel = Object.fromEntries(axes.map((a) => [a.label, a]));
  // 自訂軸名刻度：包共用 Tooltip（取代原生 SVG <title>：無延遲、觸控可點、內容可排版）。
  const renderTick = (props: { x: number; y: number; textAnchor: string; payload: { value: string } }) => {
    const a = byLabel[props.payload.value];
    const g = a?.grade ?? null;
    const txt = (
      <text x={props.x} y={props.y} textAnchor={props.textAnchor} dominantBaseline="central"
        fontSize={11} fontWeight={600} style={{ cursor: "help" }} fill={gradeColor(g)}>
        {props.payload.value}
      </text>
    );
    if (!a) return txt;
    return <Tooltip content={axisTipContent(a)} suppressUnderline delayIn={0}>{txt}</Tooltip>;
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
      <div className={`relative ${compact ? "h-36" : "h-64"}`} role="img"
        aria-label={`${title ?? "能力值"}雷達圖，各項為全聯盟百分位（越外圈越強）`}>
        {!compact && (
          <Tooltip content={methodNote(card)} suppressUnderline interactive>
            <button type="button" aria-label="能力值計算方式說明"
              className="absolute right-0 top-0 z-10 grid h-4.5 w-4.5 cursor-help place-items-center rounded-full border border-line bg-surface text-[10px] font-semibold leading-none text-muted hover:text-ink">
              ?
            </button>
          </Tooltip>
        )}
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius={compact ? "70%" : "78%"}>
            <PolarGrid stroke={ct.line} />
            <PolarAngleAxis dataKey="axis" tick={compact ? { fontSize: 10, fill: ct.muted } : renderTick} />
            <Radar dataKey="pr" stroke={radarColor} fill={radarColor} fillOpacity={0.35} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      {!compact && !hideNote && (
        <p className="mt-1 text-center text-[10px] text-faint">
          自製指標：全聯盟百分位換算，點軸名看組成、點 ? 看計算方式{card.has_advanced ? "；本季含官方進階數據" : ""}。
        </p>
      )}
    </div>
  );
}

// 兩人雷達疊圖（對戰卡：主投 vs 客投）。
export function AbilityRadarVS({
  home,
  away,
  homeColor,
  awayColor,
}: {
  home: Card;
  away: Card;
  homeColor?: string;
  awayColor?: string;
}) {
  const ct = useChartTheme();
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
          <PolarGrid stroke={ct.line} />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 10, fill: ct.muted }} />
          <Radar dataKey="away" stroke={awayColor ?? ct.cpbl} fill={awayColor ?? ct.cpbl} fillOpacity={0.25} />
          <Radar dataKey="home" stroke={homeColor ?? ct.down} fill={homeColor ?? ct.down} fillOpacity={0.25} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
