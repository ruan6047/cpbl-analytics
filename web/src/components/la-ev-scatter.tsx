// 擊球品質散點：x=擊球仰角(°)、y=擊球初速(km/h)，依結果著色。圖例可點擊開關。
"use client";
import { useState } from "react";
import { CartesianGrid, ReferenceArea, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

export type BattedBall = { la: number; ev: number; result: string };

const RESULT: Record<string, { label: string; color: string }> = {
  hr: { label: "全壘打", color: "#d62839" },
  "3b": { label: "三壘打", color: "#f59e0b" },
  "2b": { label: "二壘打", color: "#16a34a" },
  "1b": { label: "一壘安打", color: "#1d6fb8" },
  out: { label: "出局", color: "#94a3b8" },
};
const ORDER = ["out", "1b", "2b", "3b", "hr"] as const;
const axis = { tick: { fill: "#5b6b7a", fontSize: 11 }, stroke: "#cbd5e1" };

export function LaEvScatter({ balls }: { balls: BattedBall[] }) {
  const [off, setOff] = useState<Record<string, boolean>>({});
  const byResult = ORDER.map((k) => ({ k, pts: balls.filter((b) => b.result === k) }))
    .filter((g) => g.pts.length && !off[g.k]);
  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: 0 }}>
          <CartesianGrid stroke="#eef2f7" />
          {/* 強勁擊球 + 理想仰角帶（近似 barrel 區） */}
          <ReferenceArea x1={8} x2={40} y1={145} y2={185} fill="#d62839" fillOpacity={0.06} />
          <XAxis type="number" dataKey="la" name="仰角" unit="°" domain={[-40, 70]} allowDataOverflow
            ticks={[-40, -20, 0, 20, 40, 60]} tickFormatter={(v: number) => `${Math.round(v)}`} {...axis}
            label={{ value: "擊球仰角 (°)", position: "insideBottom", offset: -8, fill: "#5b6b7a", fontSize: 11 }} />
          <YAxis type="number" dataKey="ev" name="初速" domain={[60, 185]} allowDataOverflow
            ticks={[60, 90, 120, 150, 180]} tickFormatter={(v: number) => `${Math.round(v)}`} width={30} {...axis} />
          <ZAxis range={[34, 34]} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 12 }}
            formatter={(v: number, n: string) => [n === "仰角" ? `${v.toFixed(0)}°` : `${v.toFixed(0)} km/h`, n]} />
          {byResult.map(({ k, pts }) => (
            <Scatter key={k} name={RESULT[k].label} data={pts} fill={RESULT[k].color}
              fillOpacity={k === "out" ? 0.45 : 0.85} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
      <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {(["hr", "3b", "2b", "1b", "out"] as const).map((k) => (
          <button key={k} onClick={() => setOff((o) => ({ ...o, [k]: !o[k] }))}
            className={`inline-flex items-center gap-1 transition ${off[k] ? "opacity-35 line-through" : ""}`}>
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: RESULT[k].color }} />{RESULT[k].label}
          </button>
        ))}
      </div>
    </div>
  );
}
