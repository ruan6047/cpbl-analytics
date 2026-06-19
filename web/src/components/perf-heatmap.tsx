// 進壘點平滑色譜熱區（KDE，捕手視角）。藍(低)→黃→紅(高)。
// metric：密度 / 初速(擊球初速) / 安打率 / 揮空率。低資料量區域以透明度淡化避免誤導。
export type HPoint = { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null };
export type HeatMetric = "density" | "ev" | "ba" | "whiff";

const heat = (t: number) => {
  t = Math.max(0, Math.min(1, t));
  const lerp = (a: number[], b: number[], k: number) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
  const lo = [207, 226, 255], mid = [255, 247, 204], hi = [214, 40, 57];
  const c = t < 0.5 ? lerp(lo, mid, t * 2) : lerp(mid, hi, (t - 0.5) * 2);
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};

// 取該 metric 的相關點與其值(0/1 或 km/h)；密度回傳 null（只看分布）
function prep(points: HPoint[], metric: HeatMetric): { x: number; y: number; v: number }[] {
  if (metric === "density") return points.map((p) => ({ x: p.x, y: p.y, v: 0 }));
  if (metric === "whiff") return points.filter((p) => p.sw).map((p) => ({ x: p.x, y: p.y, v: p.wh ? 1 : 0 }));
  const inplay = points.filter((p) => p.result === "hit" || p.result === "out");
  if (metric === "ba") return inplay.map((p) => ({ x: p.x, y: p.y, v: p.result === "hit" ? 1 : 0 }));
  return inplay.filter((p) => p.ev != null).map((p) => ({ x: p.x, y: p.y, v: p.ev as number }));
}

export function PerfHeatmap({ points, metric }: { points: HPoint[]; metric: HeatMetric }) {
  const W = 230, H = 240, pad = 12;
  const xMin = -0.78, xMax = 0.78, yMin = -0.1, yMax = 1.7;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin)) * (H - 2 * pad);
  const cols = 22, rows = 24, bw = 0.16;
  const pts = prep(points, metric);

  // KDE：每格計算 加權平均值(rate/ev) 與 支撐度(密度)
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
  // metric → 顏色強度 t
  const tOf = (c: { val: number; sup: number }) => {
    if (metric === "density") return c.sup / maxSup;
    if (metric === "ev") return (c.val - 110) / (165 - 110);
    if (metric === "ba") return (c.val - 0.15) / 0.3;   // .15→藍 .30→中 .45→紅
    return c.val / 0.4;                                  // whiff 40% → 全紅
  };
  // 透明度：密度看自身、率值看支撐度（資料少→淡）
  const supRef = metric === "density" ? maxSup : Math.max(maxSup * 0.35, 1e-9);
  const z = { x1: sx(-0.21), x2: sx(0.21), y1: sy(1.0), y2: sy(0.5) };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <defs>
        <filter id="hmblur" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      <g filter="url(#hmblur)">
        {cells.map((c, i) => (
          <rect key={i} x={sx(c.gx - cw / 2)} y={sy(c.gy + chh / 2)}
            width={(W - 2 * pad) / cols + 0.6} height={(H - 2 * pad) / rows + 0.6}
            fill={heat(tOf(c))} fillOpacity={Math.min(1, c.sup / supRef)} />
        ))}
      </g>
      <rect x={z.x1} y={z.y1} width={z.x2 - z.x1} height={z.y2 - z.y1}
        fill="none" stroke="#0a2540" strokeWidth={1.4} />
      <text x={W / 2} y={H - 1} textAnchor="middle" className="fill-faint" fontSize={9}>捕手視角</text>
    </svg>
  );
}
