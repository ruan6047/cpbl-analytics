// 進壘點熱區圖（捕手視角）：把逐球進壘點分格，依「投球密度」或「揮空率」著色。
import { prColor } from "@/components/ui";

export type ZonePt = { x: number; y: number; sw: boolean; wh: boolean };

export function ZoneHeatmap({ points, metric }: { points: ZonePt[]; metric: "density" | "whiff" }) {
  const W = 230, H = 240, pad = 12;
  const xMin = -0.62, xMax = 0.62, yMin = 0.0, yMax = 1.55;
  const cols = 5, rows = 6;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  const cw = (W - 2 * pad) / cols, ch = (H - 2 * pad) / rows;

  // 分格統計
  const cell: { n: number; sw: number; wh: number }[][] =
    Array.from({ length: rows }, () => Array.from({ length: cols }, () => ({ n: 0, sw: 0, wh: 0 })));
  for (const p of points) {
    const ci = Math.floor(((p.x - xMin) / (xMax - xMin)) * cols);
    const ri = Math.floor(((yMax - p.y) / (yMax - yMin)) * rows);
    if (ci < 0 || ci >= cols || ri < 0 || ri >= rows) continue;
    const c = cell[ri][ci];
    c.n++; if (p.sw) c.sw++; if (p.wh) c.wh++;
  }
  const maxN = Math.max(1, ...cell.flat().map((c) => c.n));
  const z = { x1: sx(-0.21), x2: sx(0.21), y1: sy(1.0), y2: sy(0.5) };

  // 密度：白→紅順序色（越密越紅）；揮空：發散色（藍低→紅高，揮空/揮棒）
  const fill = (c: { n: number; sw: number; wh: number }) => {
    if (c.n === 0) return "#f8fafc";
    if (metric === "density") return `rgba(214,40,57,${(0.1 + 0.9 * (c.n / maxN)).toFixed(3)})`;
    return c.sw ? prColor((c.wh / c.sw) * 100) : "#eef2f7";
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {cell.map((row, ri) => row.map((c, ci) => (
        <rect key={`${ri}-${ci}`} x={pad + ci * cw} y={pad + ri * ch} width={cw} height={ch}
          fill={fill(c)} stroke="#fff" strokeWidth={0.5} />
      )))}
      {/* 好球帶框 */}
      <rect x={z.x1} y={z.y1} width={z.x2 - z.x1} height={z.y2 - z.y1}
        fill="none" stroke="#0a2540" strokeWidth={1.4} />
      <text x={W / 2} y={H - 1} textAnchor="middle" className="fill-faint" fontSize={9}>捕手視角</text>
    </svg>
  );
}
