"use client";

import { useEffect, useMemo, useRef } from "react";
import type { StatRow } from "@/lib/client";

type Props = {
  log: StatRow[];
  game: StatRow;
  idx: number;
  setIdx: (i: number | ((p: number) => number)) => void;
  playing: boolean;
  setPlaying: (b: boolean) => void;
  speed: number;
  setSpeed: (n: number) => void;
};

const occupied = (v: StatRow[string]) => v !== null && v !== undefined && String(v) !== "";

// 球數燈：填滿 n 顆
function Dots({ n, total, label, color }: { n: number; total: number; label: string; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-3 font-mono text-xs font-semibold text-muted">{label}</span>
      <div className="flex gap-1">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className="h-2.5 w-2.5 rounded-full border"
            style={{
              borderColor: i < n ? color : "var(--color-line)",
              background: i < n ? color : "transparent",
            }}
          />
        ))}
      </div>
    </div>
  );
}

// 壘包鑽石
function Diamond({ b1, b2, b3, names }: { b1: boolean; b2: boolean; b3: boolean; names: (string | undefined)[] }) {
  // home(60,108) 1B(108,60) 2B(60,12) 3B(12,60)
  const base = (cx: number, cy: number, on: boolean, name?: string) => (
    <g>
      <rect
        x={cx - 10} y={cy - 10} width={20} height={20}
        transform={`rotate(45 ${cx} ${cy})`}
        rx={3}
        fill={on ? "var(--color-accent)" : "var(--color-surface)"}
        stroke={on ? "var(--color-accent)" : "var(--color-line)"}
        strokeWidth={2}
      >
        {on && name && <title>{name}</title>}
      </rect>
    </g>
  );
  return (
    <svg viewBox="0 0 120 120" className="h-28 w-28">
      {/* 內野連線 */}
      <polygon
        points="60,108 108,60 60,12 12,60"
        fill="var(--color-surface-2)"
        stroke="var(--color-line)"
        strokeWidth={1.5}
      />
      {base(108, 60, b1, names[0])}
      {base(60, 12, b2, names[1])}
      {base(12, 60, b3, names[2])}
      {/* 本壘 */}
      <polygon points="54,110 66,110 66,116 60,121 54,116" fill="var(--color-ink)" />
    </svg>
  );
}

export default function GameReplay({ log, game, idx, setIdx, playing, setPlaying, speed, setSpeed }: Props) {
  const total = log.length;
  const e = log[idx] ?? log[total - 1];

  // 棒次 → 球員名（依攻方半局）：用於壘上跑者標示
  const nameByOrder = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of log) {
      const k = `${r.visiting_home_type}:${r.batting_order}`;
      if (r.hitter_name && !m.has(k)) m.set(k, String(r.hitter_name));
    }
    return m;
  }, [log]);

  // 自動播放
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      setIdx((p) => {
        if (p >= total - 1) {
          setPlaying(false);
          return p;
        }
        return p + 1;
      });
    }, 900 / speed);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, speed, total, setIdx, setPlaying]);

  if (!e) return null;

  const half = String(e.visiting_home_type); // 1=客攻(上) 2=主攻(下)
  const away = Number(e.visiting_score) || 0;
  const home = Number(e.home_score) || 0;
  const isScore = Boolean(e.is_score);
  const runnerNames = [
    occupied(e.first_base) ? nameByOrder.get(`${half}:${e.first_base}`) : undefined,
    occupied(e.second_base) ? nameByOrder.get(`${half}:${e.second_base}`) : undefined,
    occupied(e.third_base) ? nameByOrder.get(`${half}:${e.third_base}`) : undefined,
  ];

  const togglePlay = () => {
    if (!playing && idx >= total - 1) setIdx(0); // 播到底再按 → 從頭重播
    setPlaying(!playing);
  };
  const step = (d: number) => {
    setPlaying(false);
    setIdx((p) => Math.max(0, Math.min(total - 1, p + d)));
  };

  return (
    <div className="sticky top-3 z-10 rounded-2xl border border-line bg-surface/95 p-4 shadow-sm backdrop-blur">
      {/* 比分 + 局數 */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3 font-mono tabular-nums">
          <span className="text-sm text-muted">{String(game.away_team_name)}</span>
          <span className="text-2xl font-bold">{away}</span>
          <span className="text-faint">:</span>
          <span className="text-2xl font-bold">{home}</span>
          <span className="text-sm text-muted">{String(game.home_team_name)}</span>
        </div>
        <div className="flex items-center gap-1 text-sm font-semibold text-accent">
          <span>{half === "1" ? "▲" : "▼"}</span>
          <span>{Number(e.inning_seq)} 局{half === "1" ? "上" : "下"}</span>
        </div>
      </div>

      {/* 鑽石 + 球數 */}
      <div className="flex items-center gap-5">
        <Diamond
          b1={occupied(e.first_base)}
          b2={occupied(e.second_base)}
          b3={occupied(e.third_base)}
          names={runnerNames}
        />
        <div className="space-y-2">
          <Dots n={Number(e.ball_cnt) || 0} total={3} label="B" color="#16a34a" />
          <Dots n={Number(e.strike_cnt) || 0} total={2} label="S" color="#eab308" />
          <Dots n={Math.min(Number(e.out_cnt) || 0, 2)} total={2} label="O" color="var(--color-accent)" />
        </div>
        <div className="ml-auto text-right text-sm">
          <div><span className="text-muted">打</span> <span className="font-medium text-ink">{String(e.hitter_name ?? "—")}</span></div>
          <div><span className="text-muted">投</span> <span className="font-medium text-ink">{String(e.pitcher_name ?? "—")}</span></div>
          <div className="mt-1 font-mono text-xs text-faint">第 {Number(e.pitch_cnt) || 0} 球</div>
        </div>
      </div>

      {/* 當前事件描述 */}
      <p className={`mt-3 min-h-[2.5rem] rounded-lg px-3 py-2 text-sm ${isScore ? "bg-accent/10 font-medium text-accent" : "bg-surface-2 text-ink"}`}>
        {String(e.content ?? "")}
        {isScore && <span className="ml-2 font-mono">({away}-{home})</span>}
      </p>

      {/* 控制列 */}
      <div className="mt-3 flex items-center gap-3">
        <button onClick={() => step(-1)} className="rounded-lg border border-line px-2.5 py-1.5 text-sm hover:bg-surface-2" aria-label="上一球">◀</button>
        <button onClick={togglePlay} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-white hover:opacity-90" aria-label="播放/暫停">
          {playing ? "❚❚ 暫停" : idx >= total - 1 ? "↺ 重播" : "▶ 播放"}
        </button>
        <button onClick={() => step(1)} className="rounded-lg border border-line px-2.5 py-1.5 text-sm hover:bg-surface-2" aria-label="下一球">▶</button>

        <input
          type="range" min={0} max={total - 1} value={idx}
          onChange={(ev) => { setPlaying(false); setIdx(Number(ev.target.value)); }}
          className="h-1 flex-1 cursor-pointer accent-[var(--color-accent)]"
          aria-label="賽況進度"
        />
        <span className="w-16 text-right font-mono text-xs text-faint">{idx + 1}/{total}</span>

        <select
          value={speed} onChange={(ev) => setSpeed(Number(ev.target.value))}
          className="rounded-lg border border-line bg-surface px-1.5 py-1 text-xs text-muted"
          aria-label="播放速度"
        >
          <option value={0.5}>0.5×</option>
          <option value={1}>1×</option>
          <option value={2}>2×</option>
          <option value={4}>4×</option>
        </select>
      </div>
    </div>
  );
}
