"use client";

// recap ②關鍵打席 3–5：**|ΔRE24| 選取、時間序呈現、帶局面脈絡**。
//
// 紅線（v1.3 排序契約，由 `tests/test_pa_facts.py` 與後端 `key_plays()` 一起釘住）：
//   * 主排序＝|ΔRE24|，不加任何權重；**禁 WPA／WP 參與排序**。
//   * 每筆必附局面標示（局數／出局／壘況／分差），把「這打席重不重要」的判讀交給讀者。
//   * 分差 ≥7 的打席**降飽和呈現，不剔除、不加權**——垃圾時間用呈現層解決，不用數學
//     加工解決。降飽和後仍須通過對比度檢查，故走 surface-2 底 + muted 文字（皆為
//     語意 token，深色模式自動適配），**不用 opacity**。

import { Card, EmptyState, Eyebrow, PlayerLink } from "@/components/ui";
import { Re24Badge } from "@/components/re24-badge";
import { RunsBadge } from "@/components/runs-badge";
import {
  halfLabel, marginText, personName, scoreAfterPlay, signedDelta, situationText, type PaFact,
} from "@/lib/game-facts";

function BaseDiamond({ bases }: { bases: string[] }) {
  const on = (b: string) => (bases ?? []).includes(b);
  const cell = (filled: boolean) =>
    `inline-block h-2 w-2 rotate-45 border ${filled ? "border-ink bg-ink" : "border-line-strong"}`;
  return (
    <span aria-hidden className="inline-grid grid-cols-3 grid-rows-2 items-center gap-px">
      <span /><span className={cell(on("2"))} /><span />
      <span className={cell(on("3"))} /><span /><span className={cell(on("1"))} />
    </span>
  );
}

export function KeyPlays({ plays, onJump }: {
  plays: PaFact[];
  onJump?: (eventNo: string) => void;
}) {
  if (plays.length === 0) {
    return (
      <Card padding="p-3" className="min-w-0">
        <Eyebrow className="mb-2 px-1">關鍵打席</Eyebrow>
        <EmptyState>本場沒有足以列為關鍵的打席（|ΔRE24| 皆低於門檻）。</EmptyState>
      </Card>
    );
  }
  return (
    <Card padding="p-3" className="min-w-0">
      <div className="mb-1.5 flex items-baseline justify-between px-2 pt-1">
        <span className="text-sm font-semibold">
          關鍵打席 <span className="text-xs font-normal text-faint">（依 |ΔRE24| 選出・依時間排列）</span>
        </span>
        <span className="text-[10px] text-muted">ΔRE24＝該打席造成的得分期望值變化</span>
      </div>
      <ol className="space-y-0.5">
        {plays.map((play) => {
          // ΔRE24 併進打席資訊的同一行（需求方 2026-08-06：不要跟打席訊息分開）。
          const row = (
            <>
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
                {play.inning}{halfLabel(play.half)}
                <BaseDiamond bases={play.bases_before} />
                <span className="text-faint">{play.outs_before ?? "—"} 出局</span>
                {marginText(play) && <span className="text-faint">{marginText(play)}</span>}
                {play.garbage_time && (
                  <span className="rounded bg-surface-2 px-1 py-px text-[10px] text-muted">
                    分差 ≥7
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-sm text-ink">
                <PlayerLink pid={play.hitter?.player_id} name={personName(play.hitter)} />
                <span className="mx-1 text-faint">·</span>
                {(play.result_action ?? "").trim()}
                <span className="ml-1.5 text-xs text-faint">投：{personName(play.pitcher)}</span>
                <RunsBadge runs={play.runs_on_play} {...(scoreAfterPlay(play) ?? {})} />
                <Re24Badge value={play.delta_re24} />
              </div>
            </>
          );
          const label = `${situationText(play)}，${personName(play.hitter)} ${play.result_action ?? ""}，ΔRE24 ${signedDelta(play.delta_re24)}`;
          return (
            <li key={play.pa_index}>
              {onJump && play.start_event_no ? (
                <button type="button" aria-label={label}
                  onClick={() => onJump(play.start_event_no!)}
                  className={`block w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-2 ${
                    play.garbage_time ? "bg-surface-2/60" : ""}`}>
                  {row}
                </button>
              ) : (
                <div aria-label={label}
                  className={`rounded-lg px-2.5 py-2 ${play.garbage_time ? "bg-surface-2/60" : ""}`}>
                  {row}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
