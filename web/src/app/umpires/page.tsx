"use client";

// 主審判決報告（推算）：季排行 + 單場報告（版式參考社群 CPBL Umpire Scorecard）。
// 母體＝TrackMan called 球 vs 固定規則好球帶；覆蓋限 2026 起有設備場次；非官方分析。
import { useEffect, useMemo, useState } from "react";
import { clientGet } from "@/lib/client";

type Board = {
  season: number;
  items: { umpire: string; games: number; called: number; acc: number; strike_acc: number; ball_acc: number }[];
};
type Pitch = {
  side: number; height: number; called_strike: boolean; in_zone: boolean; correct: boolean;
  edge_cm: number; miss_cm: number; inning_seq: number | null;
  pitcher_name: string | null; hitter_name: string | null;
  ball_cnt: number | null; strike_cnt: number | null; out_cnt: number | null;
};
type Card = {
  summary: { umpire: string | null; called: number };
  game: { game_date: string; venue: string | null; home_team_name: string; away_team_name: string;
    home_score: number; away_score: number } | null;
  zone: { half_width: number; bot: number; top: number };
  pitches: Pitch[];
};
type RecentGame = { game_sno: number; game_date: string; home_team_name: string; away_team_name: string;
  home_score: number; away_score: number };

function Donut({ pct, label, sub }: { pct: number | null; label: string; sub?: string }) {
  const r = 26, c = 2 * Math.PI * r, v = pct ?? 0;
  return (
    <div className="flex flex-col items-center px-2">
      <svg viewBox="0 0 64 64" className="h-16 w-16">
        <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6" className="stroke-line" />
        <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6"
          className={v >= 92 ? "stroke-[#1B4DA1]" : v >= 88 ? "stroke-[#2A7A4B]" : "stroke-[#C8102E]"}
          strokeDasharray={`${(v / 100) * c} ${c}`} strokeLinecap="round"
          transform="rotate(-90 32 32)" />
        <text x="32" y="36" textAnchor="middle" className="fill-current font-mono text-[13px] font-bold text-ink">
          {pct != null ? `${pct}%` : "—"}
        </text>
      </svg>
      <div className="mt-1 text-[11px] font-medium text-muted">{label}</div>
      {sub && <div className="text-[10px] text-faint">{sub}</div>}
    </div>
  );
}

function judge(p: Pitch, tolCm: number): boolean {
  // 容錯：誤判但離帶界 ≤ tol 視為可接受
  return p.correct || p.edge_cm <= tolCm;
}

export default function UmpiresPage() {
  const [board, setBoard] = useState<Board | null>(null);
  const [games, setGames] = useState<RecentGame[]>([]);
  const [sno, setSno] = useState<number | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [missOnly, setMissOnly] = useState(true);
  const [tol, setTol] = useState(0);

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

  const stats = useMemo(() => {
    if (!card || !card.pitches.length) return null;
    const ps = card.pitches;
    const ok = ps.filter((p) => judge(p, tol));
    const inz = ps.filter((p) => p.in_zone);
    const outz = ps.filter((p) => !p.in_zone);
    const misses = ps.filter((p) => !judge(p, tol));
    // 主審估計好球帶：好球判決位置的 5–95 分位（樣本不足退回規則帶）
    const cs = ps.filter((p) => p.called_strike);
    const q = (arr: number[], f: number) => {
      const s = [...arr].sort((a, b) => a - b);
      return s[Math.min(s.length - 1, Math.floor(f * s.length))];
    };
    const est = cs.length >= 20 ? {
      left: q(cs.map((p) => p.side), 0.05), right: q(cs.map((p) => p.side), 0.95),
      bot: q(cs.map((p) => p.height), 0.05), top: q(cs.map((p) => p.height), 0.95),
    } : null;
    const consistent = est ? ps.filter((p) => {
      const inEst = p.side >= est.left && p.side <= est.right && p.height >= est.bot && p.height <= est.top;
      return inEst === p.called_strike;
    }).length : null;
    return {
      acc: Math.round(1000 * ok.length / ps.length) / 10,
      strikeAcc: inz.length ? Math.round(1000 * inz.filter((p) => judge(p, tol)).length / inz.length) / 10 : null,
      ballAcc: outz.length ? Math.round(1000 * outz.filter((p) => judge(p, tol)).length / outz.length) / 10 : null,
      consistency: consistent != null ? Math.round(1000 * consistent / ps.length) / 10 : null,
      avgMiss: misses.length
        ? Math.round(10 * misses.reduce((s, p) => s + p.edge_cm, 0) / misses.length) / 10 : 0,
      missCount: misses.length, total: ps.length, est,
      keyCalls: [...misses].sort((a, b) => b.edge_cm - a.edge_cm).slice(0, 5),
    };
  }, [card, tol]);

  // 捕手視角繪圖：x 可視 ±0.95m、y 可視 0–2.05m，好球帶置中偏下
  const W = 340, H = 400, sc = 178;
  const px = (s: number) => W / 2 + s * sc;
  const py = (h: number) => H - 15 - h * ((H - 30) / 2.05);

  return (
    <div>
      <h1 className="mb-1 text-2xl font-extrabold tracking-tight">裁判報告</h1>
      <p className="mb-6 text-sm text-muted">
        主審好壞球判決 vs 規則好球帶（TrackMan 逐球）。非官方自動化推算；僅涵蓋有逐球設備的場次（2026 起）。
      </p>
      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <section>
          <h2 className="mb-3 text-lg font-semibold">主審排行（{board?.season ?? "—"}）</h2>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-3 py-2">主審</th>
                  <th className="px-2 py-2 text-right">場</th>
                  <th className="px-2 py-2 text-right">準確率</th>
                  <th className="px-2 py-2 text-right">帶內</th>
                  <th className="px-2 py-2 text-right">帶外</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {(board?.items ?? []).map((u) => (
                  <tr key={u.umpire} className="border-b border-line/50 last:border-0">
                    <td className="px-3 py-1.5 font-sans text-ink">{u.umpire}</td>
                    <td className="px-2 py-1.5 text-right">{u.games}</td>
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
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">單場判決報告</h2>
            <select value={sno ?? ""} onChange={(e) => setSno(Number(e.target.value))}
              aria-label="選擇比賽場次"
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm">
              {games.map((g) => (
                <option key={g.game_sno} value={g.game_sno}>
                  {g.game_date}　{g.away_team_name} {g.away_score}:{g.home_score} {g.home_team_name}
                </option>
              ))}
            </select>
          </div>

          {card && card.pitches.length > 0 && stats ? (
            <div className="rounded-xl border border-line bg-surface">
              {/* 比分頭 */}
              {card.game && (
                <div className="flex items-center justify-center gap-6 border-b border-line px-4 py-4">
                  <div className="text-right">
                    <div className="text-sm font-semibold text-ink">{card.game.away_team_name}</div>
                    <div className="text-[11px] text-faint">客隊</div>
                  </div>
                  <div className="font-mono text-4xl font-black tabular-nums text-ink">
                    {card.game.away_score}<span className="mx-2 text-line">–</span>{card.game.home_score}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-ink">{card.game.home_team_name}</div>
                    <div className="text-[11px] text-faint">主隊</div>
                  </div>
                </div>
              )}
              <div className="border-b border-line px-4 py-2 text-center text-sm">
                <span className="font-bold text-ink">主審 {card.summary.umpire ?? "—"} 判決報告</span>
                <span className="ml-3 text-faint">{card.game?.game_date}　{card.game?.venue}</span>
              </div>

              {/* 統計列（donut） */}
              <div className="flex flex-wrap items-start justify-around gap-2 px-2 py-4">
                <Donut pct={stats.acc} label="整體準確率" sub={`${stats.total - stats.missCount}/${stats.total}`} />
                <Donut pct={stats.strikeAcc} label="好球準確率" sub="帶內" />
                <Donut pct={stats.ballAcc} label="壞球準確率" sub="帶外" />
                <Donut pct={stats.consistency} label="判決一致性" sub="vs 估計帶" />
                <div className="flex flex-col items-center px-2 pt-2">
                  <div className="font-mono text-2xl font-black tabular-nums text-ink">{stats.avgMiss}</div>
                  <div className="text-[11px] text-muted">平均誤差 cm</div>
                  <div className="text-[10px] text-faint">誤判 {stats.missCount} 球</div>
                </div>
              </div>

              {/* 顯示控制 */}
              <div className="flex flex-wrap items-center gap-4 border-t border-line px-4 py-2 text-xs">
                <div className="flex overflow-hidden rounded-md border border-line">
                  <button onClick={() => setMissOnly(true)}
                    className={missOnly ? "bg-cpbl px-2.5 py-1 font-semibold text-white" : "bg-surface px-2.5 py-1 text-muted"}>
                    僅顯示誤判
                  </button>
                  <button onClick={() => setMissOnly(false)}
                    className={!missOnly ? "bg-cpbl px-2.5 py-1 font-semibold text-white" : "bg-surface px-2.5 py-1 text-muted"}>
                    顯示所有判決
                  </button>
                </div>
                <label className="flex items-center gap-2 text-muted">
                  容錯範圍
                  <input type="range" min={0} max={5} step={0.5} value={tol}
                    onChange={(e) => setTol(Number(e.target.value))} className="w-28 accent-cpbl" />
                  <span className="font-mono tabular-nums">{tol.toFixed(1)} cm</span>
                </label>
              </div>

              <div className="grid gap-4 px-4 pb-4 md:grid-cols-[minmax(0,340px)_1fr]">
                {/* 好球帶散點 */}
                <div>
                  <div className="mb-1 mt-2 text-xs font-semibold text-muted">
                    {missOnly ? "誤判球點" : "所有判決"}
                    <span className="font-normal text-faint">實線=規則好球帶　虛線=主審估計帶（捕手視角）</span>
                  </div>
                  <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg border border-line/60 bg-paper">
                    <rect x={px(-card.zone.half_width)} y={py(card.zone.top)}
                      width={px(card.zone.half_width) - px(-card.zone.half_width)}
                      height={py(card.zone.bot) - py(card.zone.top)}
                      fill="none" strokeWidth="1.5" className="stroke-ink/70" />
                    {stats.est && (
                      <rect x={px(stats.est.left)} y={py(stats.est.top)}
                        width={px(stats.est.right) - px(stats.est.left)}
                        height={py(stats.est.bot) - py(stats.est.top)}
                        fill="none" strokeWidth="1.2" strokeDasharray="5 4" className="stroke-accent" />
                    )}
                    {card.pitches.filter((p) => !missOnly || !judge(p, tol)).map((p, i) => (
                      <circle key={i} cx={px(p.side)} cy={py(p.height)}
                        r={judge(p, tol) ? 2.5 : 4.5}
                        fill={judge(p, tol) ? (p.called_strike ? "#1B4DA1" : "#9AA3AF") : "#C8102E"}
                        opacity={judge(p, tol) ? 0.35 : 0.95}>
                        <title>{`${p.inning_seq ?? "?"}局 ${p.hitter_name ?? ""} vs ${p.pitcher_name ?? ""}　${p.ball_cnt}-${p.strike_cnt}　判${p.called_strike ? "好球" : "壞球"}${judge(p, tol) ? "" : `（差 ${p.edge_cm}cm）`}`}</title>
                      </circle>
                    ))}
                  </svg>
                </div>
                {/* 關鍵判決 */}
                <div>
                  <div className="mb-1 mt-2 text-xs font-semibold text-muted">
                    關鍵判決 <span className="font-normal text-faint">（誤差最大的誤判）</span>
                  </div>
                  <ul className="space-y-2">
                    {stats.keyCalls.map((p, i) => (
                      <li key={i} className="rounded-lg border border-line/70 px-3 py-2 text-xs">
                        <div className="text-faint">
                          第 {p.inning_seq ?? "?"} 局・{p.out_cnt ?? 0} 出局・球數 {p.ball_cnt}-{p.strike_cnt}
                        </div>
                        <div className="mt-0.5 text-ink">
                          {p.pitcher_name ?? "?"} 對 {p.hitter_name ?? "?"}
                        </div>
                        <div className="mt-1 flex items-center gap-2 font-semibold">
                          <span className={p.called_strike ? "text-cpbl" : "text-muted"}>
                            判{p.called_strike ? "好球" : "壞球"}
                          </span>
                          <span className="text-faint">應為{p.in_zone ? "好球" : "壞球"}</span>
                          <span className="ml-auto rounded bg-[#C8102E]/10 px-1.5 py-0.5 font-mono text-[#C8102E]">
                            差 {p.edge_cm} cm
                          </span>
                        </div>
                      </li>
                    ))}
                    {!stats.keyCalls.length && <li className="text-xs text-faint">本場無誤判 🎯</li>}
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            <p className="rounded-xl border border-line bg-surface p-4 text-sm text-faint">
              {card === null ? "載入中…" : "此場無逐球資料（球場無 TrackMan 設備）。"}
            </p>
          )}
          <p className="mt-2 text-[11px] text-faint">
            本報告為非官方自動化分析，好球帶採固定規則帶（未依打者身高調整），僅供參考。
          </p>
        </section>
      </div>
    </div>
  );
}
