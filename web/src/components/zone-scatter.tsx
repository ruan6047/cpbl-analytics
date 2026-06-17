// 進壘點散布（SVG，捕手視角）：好球帶近似框 + 每球點（揮空紅/揮棒藍/未揮棒灰）。
export type ZonePoint = { x: number; y: number; sw: boolean; wh: boolean };

export function ZoneScatter({ points }: { points: ZonePoint[] }) {
  const W = 260, H = 300, pad = 16;
  const xMin = -0.8, xMax = 0.8, yMin = -0.2, yMax = 1.7;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  // 好球帶（校準值 side±0.21、高 0.5–1.0）
  const z = { x1: sx(-0.21), x2: sx(0.21), y1: sy(1.0), y2: sy(0.5) };

  return (
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
      {points.map((p, i) => (
        <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={2.6}
          fill={p.wh ? "#d62839" : p.sw ? "#1d6fb8" : "#cbd5e1"}
          fillOpacity={p.sw ? 0.85 : 0.5} />
      ))}
      <text x={W / 2} y={H - 2} textAnchor="middle" className="fill-faint" fontSize={9}>捕手視角</text>
    </svg>
  );
}
