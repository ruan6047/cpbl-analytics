"use client";

// 逐打席勝率曲線（WP；推算）：自建 run_dist × WE 邊界 DP，中性隊伍+主場優勢。
// 每點=打席開始時的主隊勝率；完賽補終點。開局值 ≈ 該模型 span 的聯盟主場基準，
// 會隨 span 重建而變動——勿在 UI 或註解寫死百分比（要對數字請打 winprob 端點看首點）。
// 模型的適用邊界與已知偏差揭露統一由賽況頁曲線下方的 caption 承擔（UX-WP-DISCLOSURE1），
// 本元件不再自帶弱化版說明，避免兩處文案各自漂移。
// 點擊任一點 → onSelect(evt) 跳到該打席（由父層切到逐打席視圖）。
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTooltip, useChartTheme } from "@/lib/chart-theme";
import { Card } from "@/components/ui";
import { displayWpPct, isTerminalWpPoint } from "@/lib/win-prob-display";

export type WpPoint = { evt: string | null; inning: number | null; half: string | null;
  hitter: string | null; away: number; home: number; wp: number };

export function WinProbChart({ items, homeName, awayName, homeColor, onSelect }: {
  items: WpPoint[]; homeName: string; awayName: string; homeColor: string;
  onSelect?: (evt: string) => void;
}) {
  const ct = useChartTheme();
  if (!items || items.length < 4) return null;
  // 顯示夾層：比賽終結前不顯示 100%／0%（`lib/win-prob-display.ts` 是該規則的唯一擁有者）。
  // 曲線點、activeDot 與 tooltip 都吃同一個 `pct` 欄位，故夾一次即全處一致。
  // Y 軸刻度是座標尺規、不是任一點的勝率，維持 0–100 不夾。
  const data = items.map((p, i) => ({ ...p, i, pct: displayWpPct(p.wp, isTerminalWpPoint(p)) }));
  // X 軸刻度：每局第一個打席
  const ticks: number[] = [];
  let lastKey = "";
  data.forEach((p) => {
    const k = p.inning != null ? `${p.inning}` : "";
    if (k && k !== lastKey) { ticks.push(p.i); lastKey = k; }
  });

  return (
    <Card>
      <div className="mb-1 text-sm font-semibold">
        勝率變化 <span className="text-xs font-normal text-faint">（逐打席推算・{homeName} 視角{onSelect ? "・點擊跳至該打席" : ""}）</span>
      </div>
      <ResponsiveContainer width="100%" height={190}>
        <LineChart data={data} margin={{ top: 6, right: 12, bottom: 2, left: -22 }}
          onClick={(st) => {
            const i = (st as { activeLabel?: number | string })?.activeLabel;
            const p = typeof i === "number" ? data[i] : undefined;
            if (p?.evt && onSelect) onSelect(p.evt);
          }}
          style={onSelect ? { cursor: "pointer" } : undefined}>
          <CartesianGrid strokeDasharray="3 3" stroke={ct.line} />
          <XAxis dataKey="i" type="number" domain={[0, data.length - 1]} ticks={ticks}
            tickFormatter={(v: number) => {
              const p = data[v];
              return p?.inning != null ? `${p.inning}` : "";
            }}
            tick={{ fontSize: 10, fill: ct.faint }} tickLine={false} axisLine={false}
            label={{ value: "局", position: "insideBottomRight", offset: 0, fontSize: 10, fill: ct.faint }} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontSize: 10, fill: ct.faint }} tickLine={false} axisLine={false} />
          <ReferenceLine y={50} stroke={ct.faint} strokeDasharray="4 4" />
          <Tooltip
            formatter={(v) => [`${v}%`, `${homeName} 勝率`]}
            labelFormatter={(v: number) => {
              const p = data[v];
              if (!p) return "";
              if (p.inning == null) return `終場 ${p.away}-${p.home}`;
              return `${p.inning}${p.half === "1" ? "上" : "下"} ${p.hitter ?? ""}（${awayName} ${p.away}-${p.home} ${homeName}）`;
            }}
            contentStyle={chartTooltip(ct)} />
          <Line type="linear" dataKey="pct" stroke={homeColor} strokeWidth={2}
            dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
