// 進壘點散布（SVG，捕手視角）：好球帶近似框 + 每球依「結果」著色。圖例可點擊開關。
"use client";
import { useState } from "react";

export type ZonePoint = { x: number; y: number; sw: boolean; wh: boolean; result: string };

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
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <rect x={z.x1} y={z.y1} width={z.x2 - z.x1} height={z.y2 - z.y1}
          fill="#eef2f7" stroke="#94a3b8" strokeWidth={1.2} />
        {/* 九宮格分隔 */}
        {[1, 2].map((i) => (
          <g key={i} stroke="#cbd5e1" strokeWidth={0.5}>
            <line x1={z.x1 + ((z.x2 - z.x1) / 3) * i} y1={z.y1} x2={z.x1 + ((z.x2 - z.x1) / 3) * i} y2={z.y2} />
            <line x1={z.x1} y1={z.y1 + ((z.y2 - z.y1) / 3) * i} x2={z.x2} y2={z.y1 + ((z.y2 - z.y1) / 3) * i} />
          </g>
        ))}
        {ordered.map((p, i) => (
          <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={3.4}
            fill={(RESULT[p.result] ?? RESULT.take).color}
            fillOpacity={p.result === "take" ? 0.5 : 0.9} />
        ))}
        <text x={W / 2} y={H - 2} textAnchor="middle" className="fill-faint" fontSize={9}>捕手視角</text>
      </svg>
      <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {(["hit", "out", "foul", "whiff", "take"] as const).map((k) => (
          <button key={k} onClick={() => setOff((o) => ({ ...o, [k]: !o[k] }))}
            className={`inline-flex items-center gap-1 transition ${off[k] ? "opacity-35 line-through" : ""}`}>
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: RESULT[k].color }} />{RESULT[k].label}
          </button>
        ))}
      </div>
    </div>
  );
}
