// 進壘點視覺化（捕手視角，2026 逐球 TrackMan，覆蓋不全）：
//  進壘熱區 x 打擊成績 — Attack Zones 同心分區（Heart/Shadow/Chase/Waste）聚合成 3×3＋四角，
//  每區聚合值＋樣本 n，發散色(藍↔紅、白=本人均值)、role 方向、低樣本灰底不上色。
"use client";
import { prColor } from "@/components/ui";

export type HPoint = { x: number; y: number; sw: boolean; wh: boolean; result: string; ev: number | null; la: number | null };
// ev/la/ba/whiff/hard=九宮格(進壘熱區x打擊成績)
export type HeatMetric = "ev" | "la" | "ba" | "whiff" | "hard";

// 視窗（與散點一致；inWin 供本壘板紀律過濾用）。
const xMin = -0.5, xMax = 0.5, yMin = 0.05, yMax = 1.4;
const inWin = (p: { x: number; y: number }) => p.x >= xMin && p.x <= xMax && p.y >= yMin && p.y <= yMax;

// 好球帶幾何 + Attack Zone 同心盒（hx=半寬、y0/y1）。b≈一顆球寬（可調）。
const ZHW = 0.21, ZHH = 0.25, ZCY = 0.75, B = 0.10;
type Box = { hx: number; y0: number; y1: number };
const HEART: Box = { hx: ZHW - B, y0: ZCY - ZHH + B, y1: ZCY + ZHH - B };
const SHADOW: Box = { hx: ZHW + B, y0: ZCY - ZHH - B, y1: ZCY + ZHH + B };
const CHASE: Box = { hx: ZHW + 2 * B, y0: ZCY - ZHH - 2 * B, y1: ZCY + ZHH + 2 * B };
const inBox = (p: { x: number; y: number }, b: Box) => Math.abs(p.x) <= b.hx && p.y >= b.y0 && p.y <= b.y1;
type ZoneKey = "heart" | "shadow" | "chase" | "waste";
const zoneOf = (p: { x: number; y: number }): ZoneKey =>
  inBox(p, HEART) ? "heart" : inBox(p, SHADOW) ? "shadow" : inBox(p, CHASE) ? "chase" : "waste";

// ---------- 進壘熱區 x 打擊成績：3×3 九宮格 ＋ 四角（官方版型）----------
const MIN_N = 3;
const SPREAD: Record<string, number> = { ev: 8, la: 12, ba: 0.15, whiff: 0.15, hard: 0.18 };
const fmtVal = (m: HeatMetric, v: number) =>
  m === "ev" || m === "la" ? v.toFixed(1) : v.toFixed(3).replace(/^0\./, ".");
// 13 區：好球帶 3×3（row0=上）＋ 四角 c-{t|b}{l|r}
function cell13(x: number, y: number): string {
  if (Math.abs(x) <= ZHW && y >= ZCY - ZHH && y <= ZCY + ZHH) {
    const col = Math.min(2, Math.max(0, Math.floor((x + ZHW) / ((2 * ZHW) / 3))));
    const rowTop = Math.min(2, Math.max(0, Math.floor((ZCY + ZHH - y) / ((2 * ZHH) / 3))));
    return `g${rowTop}${col}`;
  }
  return `c-${y >= ZCY ? "t" : "b"}${x < 0 ? "l" : "r"}`;
}

// 單張 3×3＋四角 熱圖（官方版型；title 在上、本壘板在下；多張可排成 grid）
export function Grid3x3({ points, metric, title }: { points: HPoint[]; metric: HeatMetric; title?: string }) {
  const acc: Record<string, { num: number; den: number }> = {};
  let gNum = 0, gDen = 0;
  const bip = (p: HPoint) => p.result === "hit" || p.result === "out";
  for (const p of points) {
    let inc = false, val = 0;
    if (metric === "whiff") { if (p.sw) { inc = true; val = p.wh ? 1 : 0; } }
    else if (metric === "ba") { if (bip(p)) { inc = true; val = p.result === "hit" ? 1 : 0; } }
    else if (metric === "ev") { if (bip(p) && p.ev != null) { inc = true; val = p.ev; } }
    else if (metric === "la") { if (bip(p) && p.la != null) { inc = true; val = p.la; } }
    else if (metric === "hard") { if (bip(p) && p.ev != null) { inc = true; val = p.ev >= 150 ? 1 : 0; } }
    if (!inc) continue;
    const k = cell13(p.x, p.y);
    (acc[k] ??= { num: 0, den: 0 }); acc[k].num += val; acc[k].den += 1; gNum += val; gDen += 1;
  }
  const baseline = gDen ? gNum / gDen : 0;
  const cellOf = (k: string) => {
    const a = acc[k];
    if (!a || a.den < MIN_N) return { fill: "#eef2f7", txt: "—", data: false };
    const v = a.num / a.den;
    const pr = 50 + 50 * Math.max(-1, Math.min(1, (v - baseline) / SPREAD[metric]));
    return { fill: prColor(pr), txt: fmtVal(metric, v), data: true };
  };
  // 版型（Savant 風）：外方塊四象限填滿 → 內 3×3 內縮浮在中央（白底襯起）→ 底部本壘板。
  const VW = 170, VH = 184;
  const OX = 14, OY = 12, OS = 142;            // 外方塊（左上 + 邊長）
  const inset = 26, CS = 30, IS = 3 * CS;      // 內格內縮量、內格邊長、內 3×3 邊長
  const IX = OX + inset, IY = OY + inset;      // 內 3×3 左上
  const cx = VW / 2, midY = OY + OS / 2;       // 象限分界（外方塊中線）
  const colX = [IX, IX + CS, IX + 2 * CS];
  const rowY = [IY, IY + CS, IY + 2 * CS];
  // 4 外象限：各佔外方塊 1/4，浮格覆蓋中央後僅露出 L 形外緣；數值放外角。
  const quads = [
    { k: "c-tl", x: OX, y: OY, tx: (OX + IX) / 2, ty: (OY + IY) / 2 },
    { k: "c-tr", x: cx, y: OY, tx: (OX + OS + IX + IS) / 2, ty: (OY + IY) / 2 },
    { k: "c-bl", x: OX, y: midY, tx: (OX + IX) / 2, ty: (OY + OS + IY + IS) / 2 },
    { k: "c-br", x: cx, y: midY, tx: (OX + OS + IX + IS) / 2, ty: (OY + OS + IY + IS) / 2 },
  ];
  const inner: { k: string; x: number; y: number }[] = [];
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) inner.push({ k: `g${r}${c}`, x: colX[c], y: rowY[r] });
  const hy = OY + OS + 12;  // 本壘板 y
  // 數值標籤：低樣本灰、有資料 navy + 白 halo（適配 prColor 在 baseline 近白的情況）。
  const Label = ({ x, y, k }: { x: number; y: number; k: string }) => {
    const { txt, data } = cellOf(k);
    return (
      <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={11}
        fontWeight={700} fill={data ? "#0a2540" : "#94a3b8"}
        stroke={data ? "#fff" : "none"} strokeWidth={data ? 2.4 : 0} style={{ paintOrder: "stroke" }}>{txt}</text>
    );
  };
  return (
    <div>
      {title && <div className="mb-0.5 text-center text-xs font-medium text-ink">{title}</div>}
      <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full">
        {quads.map((q) => (
          <rect key={q.k} x={q.x} y={q.y} width={OS / 2} height={OS / 2} fill={cellOf(q.k).fill} />
        ))}
        <rect x={OX} y={OY} width={OS} height={OS} fill="none" stroke="#cbd5e1" strokeWidth={1} />
        <rect x={IX - 2.5} y={IY - 2.5} width={IS + 5} height={IS + 5} rx={4} fill="#fff" />
        {inner.map(({ k, x, y }) => (
          <rect key={k} x={x} y={y} width={CS} height={CS} fill={cellOf(k).fill} stroke="#fff" strokeWidth={1.4} />
        ))}
        {quads.map((q) => <Label key={q.k + "t"} x={q.tx} y={q.ty} k={q.k} />)}
        {inner.map(({ k, x, y }) => <Label key={k + "t"} x={x + CS / 2} y={y + CS / 2} k={k} />)}
        <polygon points={`${cx - 9},${hy} ${cx + 9},${hy} ${cx + 9},${hy + 5} ${cx},${hy + 10} ${cx - 9},${hy + 5}`}
          fill="none" stroke="#94a3b8" strokeWidth={1} />
      </svg>
    </div>
  );
}

// 本壘板紀律：四區「揮/不揮」發散長條
const ZONE_BAR: { key: ZoneKey; label: string; color: string; light: string }[] = [
  { key: "heart", label: "核心區", color: "#b91c1c", light: "#f1d4d4" },
  { key: "shadow", label: "邊緣區", color: "#ea580c", light: "#f7ddc9" },
  { key: "chase", label: "追打區", color: "#eab308", light: "#f6ecc4" },
  { key: "waste", label: "無效區", color: "#9ca3af", light: "#e5e7eb" },
];
export function PlateDisciplineBars({ points }: { points: HPoint[] }) {
  const acc: Record<ZoneKey, { sw: number; n: number }> =
    { heart: { sw: 0, n: 0 }, shadow: { sw: 0, n: 0 }, chase: { sw: 0, n: 0 }, waste: { sw: 0, n: 0 } };
  for (const p of points.filter(inWin)) { const z = zoneOf(p); acc[z].n += 1; if (p.sw) acc[z].sw += 1; }
  return (
    <div>
      {/* 表頭：「揮 | 不揮」對齊長條中線（= 分界線）*/}
      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-muted">
        <span className="w-16 shrink-0" />
        <span className="flex-1 text-center"><span className="text-accent font-medium">揮</span> <span className="text-faint">|</span> 不揮</span>
        <span className="w-10 shrink-0" />
      </div>
      <div className="space-y-2.5">
        {ZONE_BAR.map(({ key, label, color, light }) => {
          const a = acc[key]; const sw = a.n ? Math.round((a.sw / a.n) * 1000) / 10 : null;
          const s = sw ?? 0;  // 半尺度：100% → 半個軌道，分界線固定在 50% → 跨列對齊
          return (
            <div key={key} className="flex items-center gap-2 text-[11px]">
              <span className="w-16 shrink-0 text-muted">{label} <b className="text-ink">{sw == null ? "—" : `${sw}%`}</b></span>
              <div className="relative h-3.5 flex-1">
                {sw != null && (
                  <>
                    <div className="absolute top-0 h-full rounded-l" style={{ left: `${50 - s / 2}%`, width: `${s / 2}%`, background: color }} />
                    <div className="absolute top-0 h-full rounded-r" style={{ left: "50%", width: `${(100 - s) / 2}%`, background: light }} />
                  </>
                )}
                <div className="absolute top-0 left-1/2 h-full w-px -translate-x-1/2 bg-[#0a2540]/40" />
              </div>
              <span className="w-10 shrink-0 text-right text-faint">{sw == null ? "" : `${Math.round((100 - sw) * 10) / 10}%`}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
