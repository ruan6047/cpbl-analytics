"use client";

import { useEffect, useRef, useState } from "react";
import type { CalendarGame } from "@/lib/api";
import { detail } from "@/lib/client";
import { nextPollDelay, phaseLabel, type LiveSnapshot } from "@/lib/live-game";
import { StatusBadge, TeamLogo, type StatusTone } from "@/components/ui";

const toneOf = (phase: LiveSnapshot["phase"]): StatusTone =>
  phase === "live" ? "live"
    : phase === "final" ? "done"
      : phase === "postponed" || phase === "reserved" || phase === "unknown" ? "warn"
        : "scheduled";

export function LiveCalendarGame({ game, variant }: { game: CalendarGame; variant: "compact" | "mobile" }) {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [interrupted, setInterrupted] = useState(false);
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
        if (!disposed) schedule();
      }
    };
    const onVisibility = () => {
      clear();
      if (media.matches && document.visibilityState === "visible") void refresh();
    };
    const onMedia = () => { clear(); if (media.matches) void refresh(); };
    document.addEventListener("visibilitychange", onVisibility);
    media.addEventListener("change", onMedia);
    if (media.matches) void refresh();
    return () => {
      disposed = true;
      clear();
      document.removeEventListener("visibilitychange", onVisibility);
      media.removeEventListener("change", onMedia);
    };
  }, [game.game_sno, game.kind_code, game.year, variant]);

  const phase = snapshot?.phase ?? (game.away_score + game.home_score > 0 ? "final" : "scheduled");
  const showScore = phase === "live" || phase === "final";
  const awayScore = snapshot?.away.score ?? game.away_score;
  const homeScore = snapshot?.home.score ?? game.home_score;
  const label = interrupted ? `${phaseLabel(phase)}・更新中斷` : phaseLabel(phase);

  if (variant === "compact") return (
    <div className="flex items-center justify-between gap-1 leading-none" aria-live="polite">
      <span className="flex items-center gap-1">
        <TeamLogo code={game.away_team_code} name={game.away_team_name} size={20} />
        {showScore && <span className="font-mono text-base tabular-nums text-ink">{awayScore}</span>}
      </span>
      <StatusBadge tone={toneOf(phase)} variant="bare">{label}</StatusBadge>
      <span className="flex items-center gap-1">
        {showScore && <span className="font-mono text-base tabular-nums text-ink">{homeScore}</span>}
        <TeamLogo code={game.home_team_code} name={game.home_team_name} size={20} />
      </span>
    </div>
  );

  return (
    <div className="flex flex-col gap-2 rounded-lg bg-surface-2/30 p-3" aria-live="polite">
      <div className="flex items-center justify-between">
        <StatusBadge tone={toneOf(phase)}>{label}</StatusBadge>
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
