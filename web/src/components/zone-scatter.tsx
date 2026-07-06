// 進壘點散布（SVG，捕手視角）：好球帶近似框 + 每球依「結果」著色。圖例可點擊開關。
"use client";
import { useState } from "react";

export type ZonePoint = { x: number; y: number; sw: boolean; wh: boolean; result: string; ev?: number | null; la?: number | null };

// 出色擊球（近似 Barrel）：場內球且 仰角 8–40°、初速≥145km/h（同 la-ev-scatter 甜蜜區紅框）
const isBarrel = (p: ZonePoint) =>
  (p.result === "hit" || p.result === "out") &&
  p.ev != null && p.la != null && p.ev >= 145 && p.la >= 8 && p.la <= 40;
// 星星用該類型同色系的較淺色（向白色混合，維持辨識又同調）
const lighten = (hex: string, f = 0.6) => {
  const n = parseInt(hex.slice(1), 16);
  const m = (c: number) => Math.round(c + (255 - c) * f);
  return `rgb(${m((n >> 16) & 255)},${m((n >> 8) & 255)},${m(n & 255)})`;
};

const RESULT: Record<string, { label: string; color: string }> = {
  hit: { label: "安打", color: "#16a34a" },
  out: { label: "出局", color: "#1d6fb8" },
  foul: { label: "界外", color: "#f59e0b" },
  whiff: { label: "揮空", color: "#d62839" },
  take: { label: "未揮棒", color: "#cbd5e1" },
};
const ORDER = ["take", "foul", "out", "whiff", "hit"] as const; // 灰底→重點在上

export function ZoneScatter({ points }: { points: ZonePoint[] }) {
  const W = 230, H = 240, pad = 14;
  // 範圍收緊到好球帶周邊（放大好球帶、捨棄參考價值低的太外圍野球）
  const xMin = -0.5, xMax = 0.5, yMin = 0.15, yMax = 1.35;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  const z = { x1: sx(-0.21), x2: sx(0.21), y1: sy(1.0), y2: sy(0.5) };
  const [off, setOff] = useState<Record<string, boolean>>({});
  const inWin = (p: ZonePoint) => p.x >= xMin && p.x <= xMax && p.y >= yMin && p.y <= yMax;
  const ordered = [...points].filter((p) => !off[p.result] && inWin(p))
    .sort((a, b) => ORDER.indexOf(a.result as never) - ORDER.indexOf(b.result as never));

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
        aria-label={`進壘點散布圖，好球帶框內外共 ${points.length} 顆進球，以打擊結果著色`}>
        <rect x={z.x1} y={z.y1} width={z.x2 - z.x1} height={z.y2 - z.y1}
          fill="#eef2f7" stroke="#94a3b8" strokeWidth={1.2} />
        {ordered.map((p, i) => {
          const barrel = isBarrel(p);
          return (
            <g key={i}>
              <circle cx={sx(p.x)} cy={sy(p.y)} r={barrel ? 4.2 : 3.4}
                fill={(RESULT[p.result] ?? RESULT.take).color}
                fillOpacity={p.result === "take" ? 0.5 : 0.9} />
              {barrel && (
                <text x={sx(p.x)} y={sy(p.y)} textAnchor="middle" dominantBaseline="central"
                  fontSize={6} fontWeight={700} fill={lighten((RESULT[p.result] ?? RESULT.take).color)} style={{ pointerEvents: "none" }}>★</text>
              )}
            </g>
          );
        })}
        <text x={W / 2} y={H - 2} textAnchor="middle" className="fill-faint" fontSize={9}>捕手視角</text>
      </svg>
      <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {(["hit", "out", "foul", "whiff", "take"] as const).map((k) => (
          <button key={k} onClick={() => setOff((o) => ({ ...o, [k]: !o[k] }))}
            className={`inline-flex items-center gap-1 transition ${off[k] ? "opacity-35 line-through" : ""}`}>
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: RESULT[k].color }} />{RESULT[k].label}
          </button>
        ))}
        <span className="inline-flex items-center gap-1 text-faint" title="近似 Barrel：仰角8–40° 且初速≥145km/h">
          <span className="text-ink">★</span>出色擊球
        </span>
      </div>
    </div>
  );
}
