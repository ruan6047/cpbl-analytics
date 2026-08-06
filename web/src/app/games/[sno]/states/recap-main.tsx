"use client";

// 賽後態主區塊：recap 五塊（①結論行 ②關鍵打席 ③得分半局鏈 ④兩隊表現行 ⑤跳入點）。
//
// 資料全部來自單一底層服務「單場打席事實流」（`/api/v1/games/{sno}/facts`），
// 與 live 逐打席、linescore 展開共用同一份事實——不各自重建打席邏輯。
//
// 降級由 `render_state` 驅動（設計稿 §7 七階）：本元件只負責「完整」與「簡版」兩種
// 呈現，其餘階（stale_live／pending／postponed）由頁面殼決定不進賽後態。

import { Skeleton } from "@/components/ui";
import { isProvisional, type GameFacts } from "@/lib/game-facts";
import { DataStateNotice } from "../parts/data-state-notice";
import { ConclusionLine } from "../recap/conclusion-line";
import { JumpLinks } from "../recap/jump-links";
import { KeyPlays } from "../recap/key-plays";
import { ScoringChain } from "../recap/scoring-chain";
import { TeamLines } from "../recap/team-lines";
import type { DecItem, Highlight, MvpLine } from "../game-summary";

export function RecapMain({ facts, decisions, mvp, highlights, milestones, info,
                            onJump, onPlayByPlay }: {
  facts: GameFacts | null;
  decisions: DecItem[];
  mvp: MvpLine | null;
  highlights: Highlight[];
  milestones: Highlight[];
  info: [string, React.ReactNode][];
  onJump: (eventNo: string) => void;
  onPlayByPlay: () => void;
}) {
  // 事實流還在路上：只放骨架，不塌陷（CLS）
  if (!facts) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    );
  }
  const simple = facts.render_state === "provisional_simple" || facts.render_state === "reconciling";
  const provisional = isProvisional(facts);

  return (
    <div className="space-y-4">
      <DataStateNotice state={facts.render_state} reason={facts.reason} />
      <ConclusionLine facts={facts} decisions={decisions} mvp={mvp} provisional={provisional} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {!simple && <KeyPlays plays={facts.key_plays} onJump={onJump} />}
        <ScoringChain chain={facts.scoring_chain}
          awayCode={facts.teams?.away.code ?? null} homeCode={facts.teams?.home.code ?? null}
          onJump={onJump} />
        <TeamLines highlights={highlights} milestones={milestones} info={info} />
      </div>
      <JumpLinks onPlayByPlay={onPlayByPlay} />
    </div>
  );
}
