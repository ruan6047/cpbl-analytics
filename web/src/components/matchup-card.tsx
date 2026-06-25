"use client";

import { useEffect, useState } from "react";
import { type Card } from "@/components/ability-card";
import { AbilityRadarVS } from "@/components/ability-card";
import { detail, type Matchup, type Starter, winProb } from "@/lib/client";

function fmt(key: string, v: number | null): string {
  if (v === null) return "—";
  if (key === "rest_days_diff") return `${v.toFixed(0)} 天`;
  if (key === "runs_scored_diff" || key === "runs_allowed_diff" || key === "starter_era_diff")
    return v.toFixed(2);
  return v.toFixed(3);
}

function starterText(s: Starter): string {
  if (!s) return "先發未公布";
  if (!s.name) return "先發未列合格投手";
  return `${s.name}${s.era !== null ? ` · ERA ${s.era.toFixed(2)}` : ""}`;
}

export function MatchupCard({
  m,
  weights,
}: {
  m: Matchup;
  weights: Record<string, number>;
}) {
  const [open, setOpen] = useState(false);
  const prob = winProb(m.z, weights);
  const homePct = prob * 100;

  // 先發投手能力值卡（展開後才抓，避免一次拉滿所有場次）。
  const homePid = m.home.starter?.pid;
  const awayPid = m.away.starter?.pid;
  const [cards, setCards] = useState<{ home?: Card; away?: Card }>({});
  useEffect(() => {
    if (!open || !homePid || !awayPid || cards.home || cards.away) return;
    Promise.all([detail.abilityCard(homePid), detail.abilityCard(awayPid)])
      .then(([h, a]) => setCards({ home: h.pitching, away: a.pitching }))
      .catch(() => {});
  }, [open, homePid, awayPid, cards.home, cards.away]);
  const showRadar = cards.home?.available && cards.away?.available;

  return (
    <div className="rounded-xl border border-line bg-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        {m.game_date && (
          <span className="w-12 shrink-0 text-xs text-faint">{m.game_date.slice(5)}</span>
        )}
        <span className="flex-1 text-right text-sm">
          {m.away.name} <span className="text-faint">{m.away.record}</span>
        </span>
        {/* 客隊(左,紅)｜主隊(右,綠)：綠色從右邊長出，與右側主隊對齊 */}
        <div className="relative h-7 w-44 shrink-0 overflow-hidden rounded bg-accent">
          <div
            className="absolute right-0 top-0 h-7 bg-ink/50"
            style={{ width: `${homePct}%` }}
          />
          <span className="absolute inset-y-0 left-2 flex items-center font-mono text-[11px] text-muted">
            {(100 - homePct).toFixed(0)}
          </span>
          <span className="absolute inset-y-0 right-2 flex items-center font-mono text-xs font-bold text-white">
            {homePct.toFixed(0)}%
          </span>
        </div>
        <span className="flex-1 text-sm">
          {m.home.name} <span className="text-faint">{m.home.record}</span>
          <span className="ml-1 text-xs text-accent/70">(主)</span>
        </span>
        <span className="w-4 text-faint">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="border-t border-line px-4 py-3">
          {/* 先發投手 */}
          <div className="mb-3 grid grid-cols-[1fr_auto_1fr] items-center gap-x-4 text-xs">
            <div className="text-right text-amber-300/80">{starterText(m.away.starter ?? null)}</div>
            <div className="text-faint">先發</div>
            <div className="text-amber-300/80">{starterText(m.home.starter ?? null)}</div>
          </div>

          {/* 先發投手能力值卡疊圖（生涯 PR）：直覺看出兩位先發強弱輪廓 */}
          {showRadar && (
            <div className="mb-3">
              <AbilityRadarVS home={cards.home!} away={cards.away!} />
              <div className="flex justify-center gap-4 text-[10px] text-faint">
                <span><span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: "#1B4DA1" }} />{m.away.name} 先發</span>
                <span><span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: "#C4122F" }} />{m.home.name} 先發</span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-4 text-sm">
            <div className="text-right text-xs text-faint">{m.away.name}</div>
            <div className="text-center text-xs text-faint">變因</div>
            <div className="text-xs text-faint">{m.home.name}</div>

            {m.factors
              .filter((f) => f.key !== "home_field")
              .map((f) => {
                const homeFav = f.favored === "home";
                const awayFav = f.favored === "away";
                return (
                  <div key={f.key} className="contents">
                    <div
                      className={`text-right font-mono tabular-nums ${awayFav ? "font-bold text-accent" : "text-muted"}`}
                    >
                      {fmt(f.key, f.away_val ?? (f.key === "h2h_home" ? 1 - m.h2h_home : null))}
                    </div>
                    <div className="text-center text-xs text-faint">{f.label}</div>
                    <div
                      className={`font-mono tabular-nums ${homeFav ? "font-bold text-accent" : "text-muted"}`}
                    >
                      {fmt(f.key, f.home_val)}
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
