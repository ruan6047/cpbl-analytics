// 擊球落點圖（SVG）：用 TrackMan bearing(方向)＋distance(距離)。本壘貼底部中央，
// 球場向上扇形展開；點以「擊球結果」著色（全壘打紅 / 安打藍 / 出局灰）。
// 全壘打牆畫在 ~118m，縮放上限取 135m → 越牆全壘打仍能畫在牆弧上方。
export type SprayPoint = { dir: number; dist: number; ev: number | null; result: string };

const RESULT = {
  hr: { label: "全壘打", color: "#d62839" },
  "3b": { label: "三壘打", color: "#f59e0b" },
  "2b": { label: "二壘打", color: "#16a34a" },
  "1b": { label: "一壘安打", color: "#1d6fb8" },
  out: { label: "出局", color: "#94a3b8" },
} as const;
const LEGEND = ["hr", "3b", "2b", "1b", "out"] as const;

export function SprayChart({ points }: { points: SprayPoint[] }) {
  const W = 300, H = 232, cx = W / 2, baseY = H - 6; // 本壘貼底
  const centerR = 122, cornerR = 100; // 全壘打牆：中外野深、邊線淺（CPBL 近似）
  const maxDist = 142;                 // 縮放上限（最遠長打 ~139m）
  const scale = (baseY - 8) / maxDist;
  const pt = (deg: number, dist: number) => {
    const r = (deg * Math.PI) / 180;
    return [cx + dist * scale * Math.sin(r), baseY - dist * scale * Math.cos(r)] as const;
  };
  // 牆半徑隨方向變化：中央(0°)深、邊線(±45°)淺，餘弦內插
  const fenceR = (deg: number) => cornerR + (centerR - cornerR) * Math.cos((Math.abs(deg) / 45) * (Math.PI / 2));
  // 場地外形：本壘 → 沿牆採樣 → 回本壘（含邊線）
  let field = `M ${cx} ${baseY} `;
  for (let a = -45; a <= 45; a += 3) {
    const [x, y] = pt(a, fenceR(a));
    field += `L ${x} ${y} `;
  }
  field += "Z";
  const col = (r: string) => (RESULT[r as keyof typeof RESULT] ?? RESULT.out).color;
  // 全壘打、安打畫在出局之上，避免被蓋住
  const ordered = [...points].sort((a, b) => (a.result === "out" ? 0 : 1) - (b.result === "out" ? 0 : 1));

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {/* 場地（含邊線與全壘打牆） */}
        <path d={field} fill="#eef2f7" stroke="#cbd5e1" strokeWidth={1} />
        {/* 內野菱形 */}
        {(() => {
          const b = 27; // 壘間約 27m
          const [s1x, s1y] = pt(-45, b), [s2x, s2y] = pt(0, b * 1.414), [s3x, s3y] = pt(45, b);
          return <polygon points={`${cx},${baseY} ${s1x},${s1y} ${s2x},${s2y} ${s3x},${s3y}`}
            fill="none" stroke="#cbd5e1" strokeWidth={1} />;
        })()}
        {ordered.map((p, i) => {
          // 落地距離與牆深會 overlap，但結果分類可靠 → 依結果定位：HR 推到牆外、其餘壓在牆內
          const f = fenceR(p.dir);
          const d = p.result === "hr" ? Math.max(p.dist, f + 6) : Math.min(p.dist, f - 3);
          const [x, y] = pt(p.dir, d);
          return <circle key={i} cx={x} cy={y} r={3.6} fill={col(p.result)}
            fillOpacity={p.result === "out" ? 0.55 : 0.9} />;
        })}
        <text x={10} y={H - 4} className="fill-faint" fontSize={10}>左外野</text>
        <text x={W - 42} y={H - 4} className="fill-faint" fontSize={10}>右外野</text>
      </svg>
      <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {LEGEND.map((k) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: RESULT[k].color }} />
            {RESULT[k].label}
          </span>
        ))}
      </div>
    </div>
  );
}
