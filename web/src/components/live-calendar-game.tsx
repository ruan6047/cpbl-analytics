"use client";

import { useEffect, useRef, useState } from "react";
import type { CalendarGame } from "@/lib/api";
import { detail } from "@/lib/client";
import { hasFinalResult, nextPollDelay, phaseLabel, type LiveSnapshot } from "@/lib/live-game";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";

const toneOf = (phase: LiveSnapshot["phase"]): StatusTone =>
  phase === "live" ? "live"
    : phase === "final" ? "done"
      : phase === "postponed" || phase === "reserved" || phase === "unknown" ? "warn"
        : "scheduled";

/** 季後 E／C 沒有即時快照、已過公告開賽時間時的標示（#237）：不能一直顯示「未開打」。 */
export const NO_LIVE_LABEL = "本站無即時賽況";

export function LiveCalendarGame({ game, variant, startsAt = null }: {
  game: CalendarGame; variant: "compact" | "mobile";
  /** 公告開賽時刻（ISO，含 +08:00）；只有季後場次會帶。 */
  startsAt?: string | null;
}) {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [interrupted, setInterrupted] = useState(false);
  // 首次渲染不讀時鐘（SSR 與 hydration 才一致）；掛載與每次輪詢後補上。
  const [nowMs, setNowMs] = useState<number | null>(null);
  const snapshotRef = useRef<LiveSnapshot | null>(null);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const media = window.matchMedia(variant === "compact" ? "(min-width: 768px)" : "(max-width: 767px)");
    const clear = () => { if (timer) clearTimeout(timer); timer = null; };
    const schedule = () => {
      clear();
      const delay = nextPollDelay(snapshotRef.current, media.matches && document.visibilityState === "visible");
      if (delay !== null) timer = setTimeout(() => void refresh(), delay);
    };
    const refresh = async () => {
      clear();
      if (!media.matches || document.visibilityState !== "visible") return;
      try {
        const status = await detail.gameStatus(game.game_sno, game.kind_code, game.year);
        if (disposed) return;
        snapshotRef.current = status.live_snapshot;
        setSnapshot(status.live_snapshot);
        setInterrupted(status.live_snapshot?.freshness === "stale" || status.live_snapshot?.source_status === "error");
      } catch {
        if (!disposed) setInterrupted(true);
      } finally {
        if (!disposed) {
          setNowMs(Date.now());
          schedule();
        }
      }
    };
    const onVisibility = () => {
      clear();
      if (media.matches && document.visibilityState === "visible") void refresh();
    };
    const onMedia = () => { clear(); if (media.matches) void refresh(); };
    document.addEventListener("visibilitychange", onVisibility);
    media.addEventListener("change", onMedia);
    setNowMs(Date.now());
    if (media.matches) void refresh();
    return () => {
      disposed = true;
      clear();
      document.removeEventListener("visibilitychange", onVisibility);
      media.removeEventListener("change", onMedia);
    };
  }, [game.game_sno, game.kind_code, game.year, variant]);

  // 沒有 snapshot 時的後備：2026 起的 E／C 只認後端 `completed`（#237），賽中部分比分
  // 不得畫成「比賽結束」；其餘沿用比分判斷。
  const phase = snapshot?.phase ?? (hasFinalResult(game) ? "final" : "scheduled");
  const showScore = phase === "live" || phase === "final";
  const awayScore = snapshot?.away.score ?? game.away_score;
  const homeScore = snapshot?.home.score ?? game.home_score;
  const startMs = startsAt ? Date.parse(startsAt) : NaN;
  const noLive = !snapshot && phase === "scheduled" && (game.kind_code === "E" || game.kind_code === "C")
    && nowMs !== null && Number.isFinite(startMs) && nowMs >= startMs;
  const label = noLive ? NO_LIVE_LABEL
    : interrupted ? `${phaseLabel(phase)}・更新中斷` : phaseLabel(phase);

  if (variant === "compact") return (
    <div className="flex items-center justify-between gap-1 leading-none" aria-live="polite">
      <span className="flex items-center gap-1">
        <TeamLogo code={game.away_team_code} name={game.away_team_name} size={20} />
        {showScore && <span className="font-mono text-base tabular-nums text-ink">{awayScore}</span>}
      </span>
      <StatusBadge tone={noLive ? "warn" : toneOf(phase)} variant="bare">{label}</StatusBadge>
      <span className="flex items-center gap-1">
        {showScore && <span className="font-mono text-base tabular-nums text-ink">{homeScore}</span>}
        <TeamLogo code={game.home_team_code} name={game.home_team_name} size={20} />
      </span>
    </div>
  );

  return (
    <div className="flex flex-col gap-2 rounded-sm bg-surface-2 p-3" aria-live="polite">
      <div className="flex items-center justify-between">
        <StatusBadge tone={noLive ? "warn" : toneOf(phase)}>{label}</StatusBadge>
        {game.venue && <span className="text-[10px] text-faint">{game.venue}</span>}
      </div>
      {(["away", "home"] as const).map((side) => {
        const away = side === "away";
        return (
          <div key={side} className="flex min-h-11 items-center justify-between px-1">
            <span className="flex min-w-0 flex-1 items-center gap-2">
              <TeamLogo code={away ? game.away_team_code : game.home_team_code}
                name={away ? game.away_team_name : game.home_team_name} size={22} />
              <span className="truncate text-sm text-ink">{away ? game.away_team_name : game.home_team_name}</span>
            </span>
            {showScore && <span className="min-w-8 text-right font-mono text-lg font-bold tabular-nums text-ink">
              {away ? awayScore : homeScore}
            </span>}
          </div>
        );
      })}
    </div>
  );
}
