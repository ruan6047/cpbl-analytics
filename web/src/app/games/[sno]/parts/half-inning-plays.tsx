"use client";

// 記分板逐局格子展開：該半局的打席列表（每打席一行：局面＋官方結果＋ΔRE24）。
//
// Wave 1 新增（2026-08-06 需求方提問產物）。資料＝打席事實流服務**既有輸出**
// （`half_innings`），零新請求、零新算法——與 recap 關鍵打席、live 逐打席同源。

import { EmptyState, PlayerLink } from "@/components/ui";
import { halfLabel, personName, signedDelta, situationText, type PaFact } from "@/lib/game-facts";

export function HalfInningPlays({ inning, half, plays, onJump, onClose }: {
  inning: number;
  half: string;
  plays: PaFact[] | undefined;
  onJump?: (eventNo: string) => void;
  onClose: () => void;
}) {
  const rows = (plays ?? []).filter((p) => p.state !== "non_pa");
  return (
    <section aria-label={`${inning} 局${halfLabel(half)}打席`}
      className="rounded-xl border border-line bg-surface-2/50 px-3 py-2.5">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-ink">
          {inning} 局{halfLabel(half)}
          <span className="ml-2 text-xs font-normal text-faint">{rows.length} 個打席</span>
        </span>
        <button type="button" onClick={onClose}
          className="rounded px-2 py-0.5 text-xs text-muted transition-colors hover:bg-surface-2">
          收合
        </button>
      </div>
      {rows.length === 0 ? (
        <EmptyState className="py-4">此半局尚無打席資料。</EmptyState>
      ) : (
        <ol className="space-y-0.5">
          {rows.map((play) => {
            const body = (
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="shrink-0 font-mono text-[11px] tabular-nums text-faint">
                  {play.outs_before ?? "—"}出
                  {(play.bases_before ?? []).length
                    ? `・${(play.bases_before ?? []).join("")}壘`
                    : "・空壘"}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">
                  <PlayerLink pid={play.hitter?.player_id} name={personName(play.hitter)} />
                  <span className="mx-1 text-faint">·</span>
                  {(play.result_action ?? "").trim() || "—"}
                  {play.runs_on_play ? <span className="ml-1.5 text-accent">{play.runs_on_play} 分</span> : null}
                </span>
                <span className={`shrink-0 font-mono text-[11px] tabular-nums ${
                  (play.delta_re24 ?? 0) > 0 ? "text-up"
                    : (play.delta_re24 ?? 0) < 0 ? "text-down" : "text-faint"}`}>
                  {play.delta_re24 === null ? "—" : signedDelta(play.delta_re24)}
                </span>
              </div>
            );
            const label = `${situationText(play)}，${personName(play.hitter)} ${play.result_action ?? ""}`;
            return (
              <li key={play.pa_index}>
                {onJump && play.start_event_no ? (
                  <button type="button" aria-label={label}
                    onClick={() => onJump(play.start_event_no!)}
                    className="block w-full rounded px-1.5 py-1 text-left transition-colors hover:bg-surface">
                    {body}
                  </button>
                ) : (
                  <div aria-label={label} className="px-1.5 py-1">{body}</div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
