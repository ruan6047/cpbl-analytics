"use client";

// recap ③得分半局事實鏈：依時間序列出**有得分的半局**與該半局的得分打席。
// 資料源＝打席事實流（runs_on_play > 0 的打席聚合到半局），與 linescore 同源、不另算。

import { Card, EmptyState, Eyebrow, PlayerLink } from "@/components/ui";
import { halfLabel, personName, signedDelta, type ScoringHalf } from "@/lib/game-facts";
import { teamColor } from "@/lib/teams";

export function ScoringChain({ chain, awayCode, homeCode, onJump }: {
  chain: ScoringHalf[];
  awayCode: string | null;
  homeCode: string | null;
  onJump?: (eventNo: string) => void;
}) {
  return (
    <Card padding="p-3" className="min-w-0">
      <Eyebrow className="mb-2 px-1">得分過程</Eyebrow>
      {chain.length === 0 ? (
        <EmptyState>本場沒有得分半局。</EmptyState>
      ) : (
        <ol className="space-y-2.5 px-1">
          {chain.map((half) => {
            const code = String((half.half === "1" ? awayCode : homeCode) ?? "");
            const color = teamColor(code);
            return (
              <li key={`${half.inning}|${half.half}`} className="flex gap-2.5">
                <span aria-hidden className="mt-1 h-2 w-2 shrink-0 rounded-full"
                  style={{ background: color }} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-muted">
                    {half.inning} 局{halfLabel(half.half)}
                    <span className="ml-1.5 font-mono font-semibold" style={{ color }}>
                      +{half.runs}
                    </span>
                  </div>
                  <ul className="mt-0.5 space-y-0.5">
                    {half.plays.map((play) => {
                      const body = (
                        <>
                          <PlayerLink pid={play.hitter?.player_id} name={personName(play.hitter)} />
                          <span className="mx-1 text-faint">·</span>
                          {(play.result_action ?? "").trim()}
                          <span className="ml-1.5 text-accent">{play.runs} 分</span>
                          {play.delta_re24 !== null && (
                            <span className="ml-1.5 font-mono text-[11px] tabular-nums text-faint">
                              ΔRE24 {signedDelta(play.delta_re24)}
                            </span>
                          )}
                        </>
                      );
                      return (
                        <li key={play.pa_index} className="truncate text-sm text-ink">
                          {onJump && play.start_event_no ? (
                            <button type="button" onClick={() => onJump(play.start_event_no!)}
                              className="w-full truncate rounded px-1 py-0.5 text-left transition-colors hover:bg-surface-2">
                              {body}
                            </button>
                          ) : body}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
