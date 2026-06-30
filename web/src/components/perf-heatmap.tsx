// 進壘點平滑色譜熱區（KDE，捕手視角）。藍(低)→黃→紅(高)。
// metric：密度 / 初速(擊球初速) / 安打率 / 揮空率。低資料量區域以透明度淡化避免誤導。
"use client";

export type HPoint = { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null };
export type HeatMetric = "density" | "ev" | "ba" | "whiff";

// 多段色階：淺藍→藍→暖黃→橙→紅
const STOPS = [[234, 242, 251], [150, 197, 232], [246, 210, 107], [238, 123, 70], [200, 26, 41]];
const heat = (t: number) => {
  t = Math.max(0, Math.min(1, t)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(t)), k = t - i;
  const c = STOPS[i].map((v, j) => Math.round(v + (STOPS[i + 1][j] - v) * k));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};

function prep(points: HPoint[], metric: HeatMetric): { x: number; y: number; v: number }[] {
  if (metric === "density") return points.map((p) => ({ x: p.x, y: p.y, v: 0 }));
  if (metric === "whiff") return points.filter((p) => p.sw).map((p) => ({ x: p.x, y: p.y, v: p.wh ? 1 : 0 }));
  const inplay = points.filter((p) => p.result === "hit" || p.result === "out");
  if (metric === "ba") return inplay.map((p) => ({ x: p.x, y: p.y, v: p.result === "hit" ? 1 : 0 }));
  return inplay.filter((p) => p.ev != null).map((p) => ({ x: p.x, y: p.y, v: p.ev as number }));
}

export function PerfHeatmap({ points, metric }: { points: HPoint[]; metric: HeatMetric }) {
  const W = 230, H = 240, pad = 12;
  // 範圍收緊到好球帶周邊（與散點一致；捨棄太外圍野球，放大好球帶）
  const xMin = -0.5, xMax = 0.5, yMin = 0.05, yMax = 1.4;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  const cols = 26, rows = 28, bw = 0.16;
  const inWin = (p: HPoint) => p.x >= xMin && p.x <= xMax && p.y >= yMin && p.y <= yMax;
  const pts = prep(points.filter(inWin), metric);

  const cw = (xMax - xMin) / cols, chh = (yMax - yMin) / rows;
  const cells: { gx: number; gy: number; val: number; sup: number }[] = [];
  let maxSup = 1e-9;
  for (let r = 0; r < rows; r++) {
    for (let cI = 0; cI < cols; cI++) {
      const gx = xMin + (cI + 0.5) * cw, gy = yMin + (r + 0.5) * chh;
      let num = 0, den = 0;
      for (const p of pts) {
        const w = Math.exp(-(((p.x - gx) ** 2) + ((p.y - gy) ** 2)) / (2 * bw * bw));
        den += w; num += w * p.v;
      }
      cells.push({ gx, gy, val: den > 0 ? num / den : 0, sup: den });
      if (den > maxSup) maxSup = den;
    }
  }
  const tOf = (c: { val: number; sup: number }) => {
    if (metric === "density") return c.sup / maxSup;
    if (metric === "ev") return (c.val - 110) / (165 - 110);
    if (metric === "ba") return (c.val - 0.15) / 0.3;
    return c.val / 0.4;
  };
  const supRef = metric === "density" ? maxSup : Math.max(maxSup * 0.35, 1e-9);
  const z = { x1: sx(-0.21), x2: sx(0.21), y1: sy(1.0), y2: sy(0.5) };
  // 外圍邊界（圓角框）
  const bx = 5, by = 5, bw2 = W - 10, bh = H - 24, br = 12;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <defs>
        <filter id="hmblur" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <clipPath id="hmclip"><rect x={bx} y={by} width={bw2} height={bh} rx={br} ry={br} /></clipPath>
      </defs>
      {/* 邊界底色 */}
      <rect x={bx} y={by} width={bw2} height={bh} rx={br} ry={br} fill="#f8fafc" />
      {/* KDE 熱區（裁切在邊界內） */}
      <g clipPath="url(#hmclip)">
        <g filter="url(#hmblur)">
          {cells.map((c, i) => (
            <rect key={i} x={sx(c.gx - cw / 2)} y={sy(c.gy + chh / 2)}
              width={(W - 2 * pad) / cols + 0.8} height={(H - 2 * pad) / rows + 0.8}
              fill={heat(tOf(c))} fillOpacity={Math.min(1, c.sup / supRef)} />
          ))}
        </g>
      </g>
      {/* 好球帶框 */}
      <rect x={z.x1} y={z.y1} width={z.x2 - z.x1} height={z.y2 - z.y1}
        fill="none" stroke="#0a2540" strokeWidth={1.5} />
      {/* 外圍邊界線 */}
      <rect x={bx} y={by} width={bw2} height={bh} rx={br} ry={br} fill="none" stroke="#cbd5e1" strokeWidth={1.2} />
      <text x={W / 2} y={H - 4} textAnchor="middle" className="fill-faint" fontSize={9}>捕手視角</text>
    </svg>
  );
}
