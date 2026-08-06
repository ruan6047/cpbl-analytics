"use client";

// recap ①結論行：比分 ＋ 一句事實句 ＋ 決勝資訊 ＋ 官方單場 MVP。
//
// 「致勝方式」欄**已取消**（Phase A spike 實查：`game_detail.winning_type` 是「勝方是主隊
// 還客隊」的旗標，與比分 100% 共變、資訊量為零，4,163 場零例外）。該語意改由一句事實句
// 的 walkoff／blowout／close／regular 分支承載，全部可查證。
//
// 暫定期（當晚 snapshot 源）的**勝敗投**顯示「官方確認中」——實測 snapshot 只有 2/5
// 的完賽場帶得出勝投；不顯示可能錯誤的值，也不留白冒充「沒有勝投」。

import { Card, PlayerLink } from "@/components/ui";
import { personName, type FactDecisions, type GameFacts } from "@/lib/game-facts";
import type { DecItem, MvpLine } from "../game-summary";

function DecisionCell({ label, value, note, pid }: DecItem) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] leading-tight text-muted">{label}</dt>
      <dd className="truncate text-sm font-semibold text-ink">
        {pid ? <PlayerLink pid={pid} name={value} /> : value}
        {note ? <span className="ml-1 text-[11px] font-normal text-muted">{note}</span> : null}
      </dd>
    </div>
  );
}

function PendingCell({ label }: { label: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] leading-tight text-muted">{label}</dt>
      <dd className="truncate text-sm font-medium text-faint">官方確認中</dd>
    </div>
  );
}

/** 暫定源時的決勝列：官方已給的照顯，未給的標「官方確認中」。 */
function provisionalItems(decisions: FactDecisions | undefined): {
  filled: DecItem[]; pending: string[];
} {
  const filled: DecItem[] = [];
  const pending: string[] = [];
  const add = (label: string, person: FactDecisions["mvp"]) => {
    if (person) filled.push({ label, value: personName(person), pid: person.player_id });
    else pending.push(label);
  };
  add("勝投", decisions?.winning_pitcher ?? null);
  add("敗投", decisions?.losing_pitcher ?? null);
  return { filled, pending };
}

export function ConclusionLine({ facts, decisions, mvp, provisional }: {
  facts: GameFacts;
  /** 權威源的決勝資訊（來自 box payload，含本季第 N 勝等註記）。 */
  decisions: DecItem[];
  mvp: MvpLine | null;
  provisional: boolean;
}) {
  const final = facts.final;
  const teams = facts.teams;
  const snapshotMvp = facts.decisions?.mvp ?? null;
  const provisionalDecisions = provisionalItems(facts.decisions);

  return (
    <Card className="min-w-0">
      {final && teams && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-xl font-extrabold tracking-tight text-ink">
            {teams.away.name} <span className="font-mono tabular-nums">{final.away_score}</span>
            <span className="mx-1.5 text-faint">:</span>
            <span className="font-mono tabular-nums">{final.home_score}</span> {teams.home.name}
          </h2>
        </div>
      )}
      {facts.conclusion?.sentence && (
        <p className="mt-2 text-sm leading-relaxed text-ink">{facts.conclusion.sentence}</p>
      )}

      {(mvp || snapshotMvp) && (
        <div className="mt-3 flex items-center gap-3 rounded-lg bg-accent/5 px-3 py-2.5">
          <span className="shrink-0 rounded-md bg-accent px-2 py-0.5 text-xs font-bold text-white">MVP</span>
          <div className="min-w-0">
            {mvp ? (
              <>
                <PlayerLink pid={mvp.pid} name={mvp.name} className="text-base font-bold" />
                {mvp.count ? <span className="ml-1.5 text-xs font-normal text-muted">本季第 {mvp.count} 次</span> : null}
                <span className="ml-2 font-mono text-xs tabular-nums text-muted">{mvp.line}</span>
              </>
            ) : (
              <PlayerLink pid={snapshotMvp!.player_id} name={personName(snapshotMvp)}
                className="text-base font-bold" />
            )}
          </div>
        </div>
      )}

      {provisional ? (
        <dl className="mt-3.5 grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-line pt-3.5 sm:grid-cols-3">
          {provisionalDecisions.filled.map((d) => <DecisionCell key={d.label} {...d} />)}
          {provisionalDecisions.pending.map((label) => <PendingCell key={label} label={label} />)}
        </dl>
      ) : decisions.length > 0 ? (
        <dl className="mt-3.5 grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-line pt-3.5 sm:grid-cols-3">
          {decisions.map((d) => <DecisionCell key={d.label} {...d} />)}
        </dl>
      ) : null}
    </Card>
  );
}
