"use client";

// 逐打席勝率曲線（WP；推算）：自建 run_dist × WE 邊界 DP，中性隊伍+主場優勢。
// 每點=打席開始時的主隊勝率；完賽補終點。開局 ≈ 聯盟主場基準 52.8%。
// 點擊任一點 → onSelect(evt) 跳到該打席（由父層切到逐打席視圖）。
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type WpPoint = { evt: string | null; inning: number | null; half: string | null;
  hitter: string | null; away: number; home: number; wp: number };

export function WinProbChart({ items, homeName, awayName, homeColor, onSelect }: {
  items: WpPoint[]; homeName: string; awayName: string; homeColor: string;
  onSelect?: (evt: string) => void;
}) {
  if (!items || items.length < 4) return null;
  const data = items.map((p, i) => ({ ...p, i, pct: Math.round(p.wp * 1000) / 10 }));
  // X 軸刻度：每局第一個打席
  const ticks: number[] = [];
  let lastKey = "";
  data.forEach((p) => {
    const k = p.inning != null ? `${p.inning}` : "";
    if (k && k !== lastKey) { ticks.push(p.i); lastKey = k; }
  });

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-1 flex items-baseline justify-between">
        <div className="text-sm font-semibold">
          勝率變化 <span className="text-xs font-normal text-faint">（逐打席推算・{homeName} 視角{onSelect ? "・點擊跳至該打席" : ""}）</span>
        </div>
        <div className="text-[10px] text-faint">中性隊伍+主場基準 52.8%，不含先發/戰力差</div>
      </div>
      <ResponsiveContainer width="100%" height={190}>
        <LineChart data={data} margin={{ top: 6, right: 12, bottom: 2, left: -22 }}
          onClick={(st) => {
            const i = (st as { activeLabel?: number | string })?.activeLabel;
            const p = typeof i === "number" ? data[i] : undefined;
            if (p?.evt && onSelect) onSelect(p.evt);
          }}
          style={onSelect ? { cursor: "pointer" } : undefined}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
          <XAxis dataKey="i" type="number" domain={[0, data.length - 1]} ticks={ticks}
            tickFormatter={(v: number) => {
              const p = data[v];
              return p?.inning != null ? `${p.inning}` : "";
            }}
            tick={{ fontSize: 10, fill: "var(--color-faint)" }} tickLine={false} axisLine={false}
            label={{ value: "局", position: "insideBottomRight", offset: 0, fontSize: 10, fill: "var(--color-faint)" }} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontSize: 10, fill: "var(--color-faint)" }} tickLine={false} axisLine={false} />
          <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="4 4" />
          <Tooltip
            formatter={(v) => [`${v}%`, `${homeName} 勝率`]}
            labelFormatter={(v: number) => {
              const p = data[v];
              if (!p) return "";
              if (p.inning == null) return `終場 ${p.away}-${p.home}`;
              return `${p.inning}${p.half === "1" ? "上" : "下"} ${p.hitter ?? ""}（${awayName} ${p.away}-${p.home} ${homeName}）`;
            }}
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid var(--color-line)",
              background: "var(--color-surface)" }} />
          <Line type="stepAfter" dataKey="pct" stroke={homeColor} strokeWidth={2}
            dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
