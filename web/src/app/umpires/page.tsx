"use client";

// 傘審記分卡（推算）：主審好壞球判決準確率排行 + 單場記分卡（誤判散點 + 固定規則好球帶）。
// 母體＝TrackMan called 球；覆蓋限 2026 起有設備的場次；非官方自動化分析。
import { useEffect, useState } from "react";
import { clientGet } from "@/lib/client";

type Board = {
  season: number;
  zone: { half_width: number; bot: number; top: number };
  items: { umpire: string; games: number; called: number; acc: number; strike_acc: number; ball_acc: number }[];
};
type Card = {
  summary: { umpire: string | null; called: number; acc: number | null; missed: number; avg_miss_cm: number };
  zone: { half_width: number; bot: number; top: number };
  pitches: { side: number; height: number; called_strike: boolean; in_zone: boolean; correct: boolean }[];
};
type RecentGame = { game_sno: number; game_date: string; home_team_name: string; away_team_name: string;
  home_score: number; away_score: number };

function ZonePlot({ card }: { card: Card }) {
  // 捕手視角：x=side（左右反轉不做，TrackMan side 已為捕手視角正右）；y 上下翻轉
  const W = 300, H = 340, sc = 110, cx = W / 2, cy = H - 40;
  const px = (s: number) => cx + s * sc;
  const py = (h: number) => cy - h * sc * 1.4 + 100; // 高度壓縮平移到視窗
  const z = card.zone;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[300px]">
      <rect x={px(-z.half_width)} y={py(z.top)} width={px(z.half_width) - px(-z.half_width)}
        height={py(z.bot) - py(z.top)} fill="none" stroke="currentColor" strokeWidth="1.5"
        className="text-ink/60" />
      {card.pitches.map((p, i) => (
        <circle key={i} cx={px(p.side)} cy={py(p.height)} r={p.correct ? 2.5 : 4.5}
          fill={p.correct ? (p.called_strike ? "#1B4DA1" : "#9AA3AF") : "#C8102E"}
          opacity={p.correct ? 0.35 : 0.95} />
      ))}
      <text x={cx} y={H - 6} textAnchor="middle" className="fill-current text-[10px] text-faint">
        捕手視角 · 紅=誤判 藍=好球 灰=壞球
      </text>
    </svg>
  );
}

export default function UmpiresPage() {
  const [board, setBoard] = useState<Board | null>(null);
  const [games, setGames] = useState<RecentGame[]>([]);
  const [sno, setSno] = useState<number | null>(null);
  const [card, setCard] = useState<Card | null>(null);

  useEffect(() => {
    clientGet<Board>("/api/v1/umpires").then(setBoard).catch(() => setBoard(null));
    clientGet<{ items: RecentGame[] }>("/api/v1/games/recent?limit=30")
      .then((d) => {
        const done = d.items.filter((g) => g.home_score + g.away_score > 0);
        setGames(done);
        if (done.length) setSno(done[0].game_sno);
      }).catch(() => setGames([]));
  }, []);
  useEffect(() => {
    if (sno == null) return;
    setCard(null);
    clientGet<Card>(`/api/v1/games/${sno}/umpire`).then(setCard).catch(() => setCard(null));
  }, [sno]);

  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight">傘審記分卡</h1>
      <p className="mb-6 text-sm text-muted">
        主審好壞球判決 vs 規則好球帶（TrackMan 逐球，固定帶 ±25cm／42–108cm 含球半徑）。
        非官方自動化推算；僅涵蓋有逐球設備的場次（2026 起）。
      </p>
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <section>
          <h2 className="mb-3 text-lg font-semibold">主審排行（{board?.season ?? "—"}）</h2>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-3 py-2">主審</th>
                  <th className="px-2 py-2 text-right">場</th>
                  <th className="px-2 py-2 text-right">判決球</th>
                  <th className="px-2 py-2 text-right">準確率</th>
                  <th className="px-2 py-2 text-right">好球帶內</th>
                  <th className="px-2 py-2 text-right">帶外</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {(board?.items ?? []).map((u) => (
                  <tr key={u.umpire} className="border-b border-line/50 last:border-0">
                    <td className="px-3 py-1.5 font-sans text-ink">{u.umpire}</td>
                    <td className="px-2 py-1.5 text-right">{u.games}</td>
                    <td className="px-2 py-1.5 text-right">{u.called}</td>
                    <td className="px-2 py-1.5 text-right font-semibold">{u.acc}%</td>
                    <td className="px-2 py-1.5 text-right">{u.strike_acc}%</td>
                    <td className="px-2 py-1.5 text-right">{u.ball_acc}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section>
          <h2 className="mb-3 text-lg font-semibold">單場記分卡</h2>
          <select value={sno ?? ""} onChange={(e) => setSno(Number(e.target.value))}
            className="mb-3 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm">
            {games.map((g) => (
              <option key={g.game_sno} value={g.game_sno}>
                {g.game_date}　{g.away_team_name} {g.away_score}:{g.home_score} {g.home_team_name}
              </option>
            ))}
          </select>
          {card && card.pitches.length > 0 ? (
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="mb-2 text-sm">
                <span className="font-semibold text-ink">主審 {card.summary.umpire ?? "—"}</span>
                <span className="ml-3 text-muted">準確率 <b className="font-mono text-ink">{card.summary.acc}%</b></span>
                <span className="ml-3 text-muted">誤判 <b className="font-mono text-ink">{card.summary.missed}</b> 球
                  （平均差 {card.summary.avg_miss_cm}cm）</span>
              </div>
              <ZonePlot card={card} />
            </div>
          ) : (
            <p className="rounded-xl border border-line bg-surface p-4 text-sm text-faint">
              {card === null ? "載入中…" : "此場無逐球資料（球場無 TrackMan 設備）。"}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
