// 擊球落點圖（SVG）：用 TrackMan bearing(方向)＋distance(距離)。本壘在底部中央，
// 球場向上扇形展開；點以擊球初速著色（藍↔紅）。
import { prColor } from "@/components/ui";

export type SprayPoint = { dir: number; dist: number; ev: number | null };

export function SprayChart({ points, evMin = 100, evMax = 175 }: { points: SprayPoint[]; evMin?: number; evMax?: number }) {
  const W = 320, H = 300, cx = W / 2, baseY = H - 18;
  const maxDist = 130; // m
  const scale = (H - 40) / maxDist;
  const foul = 45 * (Math.PI / 180);
  const pt = (deg: number, dist: number) => {
    const r = (deg * Math.PI) / 180;
    return [cx + dist * scale * Math.sin(r), baseY - dist * scale * Math.cos(r)] as const;
  };
  const [lfx, lfy] = pt(-foul * (180 / Math.PI), maxDist);
  const [rfx, rfy] = pt(foul * (180 / Math.PI), maxDist);
  const evColor = (ev: number | null) =>
    ev == null ? "#94a3b8" : prColor(Math.max(0, Math.min(100, ((ev - evMin) / (evMax - evMin)) * 100)));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* 外野弧 */}
      <path d={`M ${lfx} ${lfy} A ${maxDist * scale} ${maxDist * scale} 0 0 1 ${rfx} ${rfy}`}
        fill="#eef2f7" stroke="#cbd5e1" strokeWidth={1} />
      {/* 邊線 */}
      <line x1={cx} y1={baseY} x2={lfx} y2={lfy} stroke="#cbd5e1" strokeWidth={1} />
      <line x1={cx} y1={baseY} x2={rfx} y2={rfy} stroke="#cbd5e1" strokeWidth={1} />
      {/* 內野菱形 */}
      {(() => {
        const b = 27; // 壘間約 27m
        const [s1x, s1y] = pt(-45, b), [s2x, s2y] = pt(0, b * 1.414), [s3x, s3y] = pt(45, b);
        return <polygon points={`${cx},${baseY} ${s1x},${s1y} ${s2x},${s2y} ${s3x},${s3y}`}
          fill="none" stroke="#cbd5e1" strokeWidth={1} />;
      })()}
      {points.map((p, i) => {
        const [x, y] = pt(p.dir, p.dist);
        return <circle key={i} cx={x} cy={y} r={3} fill={evColor(p.ev)} fillOpacity={0.8} />;
      })}
      <text x={10} y={H - 4} className="fill-faint" fontSize={10}>左外野</text>
      <text x={W - 42} y={H - 4} className="fill-faint" fontSize={10}>右外野</text>
    </svg>
  );
}
