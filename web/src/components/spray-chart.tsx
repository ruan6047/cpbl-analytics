// 擊球落點圖（SVG）：用 TrackMan bearing(方向)＋distance(距離)。本壘貼底部中央
// （本壘後側為界外/死球區，不留空間），球場向上扇形展開；點以擊球初速著色（藍↔紅）。
// 全壘打牆畫在 ~118m，縮放上限取 135m → 越牆全壘打仍能畫在牆弧上方。
import { prColor } from "@/components/ui";

export type SprayPoint = { dir: number; dist: number; ev: number | null };

export function SprayChart({ points, evMin = 100, evMax = 175 }: { points: SprayPoint[]; evMin?: number; evMax?: number }) {
  const W = 300, H = 232, cx = W / 2, baseY = H - 6; // 本壘貼底
  const fenceDist = 118;  // 全壘打牆（畫弧）
  const maxDist = 135;    // 縮放上限，保留牆外長打空間
  const scale = (baseY - 8) / maxDist;
  const pt = (deg: number, dist: number) => {
    const r = (deg * Math.PI) / 180;
    return [cx + dist * scale * Math.sin(r), baseY - dist * scale * Math.cos(r)] as const;
  };
  const [lfx, lfy] = pt(-45, fenceDist);
  const [rfx, rfy] = pt(45, fenceDist);
  const evColor = (ev: number | null) =>
    ev == null ? "#94a3b8" : prColor(Math.max(0, Math.min(100, ((ev - evMin) / (evMax - evMin)) * 100)));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* 外野（全壘打牆）弧 */}
      <path d={`M ${lfx} ${lfy} A ${fenceDist * scale} ${fenceDist * scale} 0 0 1 ${rfx} ${rfy}`}
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
        return <circle key={i} cx={x} cy={y} r={3.6} fill={evColor(p.ev)} fillOpacity={0.8} />;
      })}
      <text x={10} y={H - 4} className="fill-faint" fontSize={10}>左外野</text>
      <text x={W - 42} y={H - 4} className="fill-faint" fontSize={10}>右外野</text>
    </svg>
  );
}
