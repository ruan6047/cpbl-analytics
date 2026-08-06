"use client";

// recap ②關鍵打席 3–5：**|ΔWP| 選取、直接顯示勝率擺動、時間序呈現、帶局面脈絡**。
//
// 選取與顯示契約（2026-08-06 需求方第五輪人工審數次裁決，後端 `pa_facts.key_plays()`
// 與 `tests/test_pa_facts.py` 一起釘住）：
//   * 主排序＝|ΔWP|（勝率擺動絕對值）取前 3–5，呈現時改回時間序。
//   * 版式沿用生產「關鍵時刻」卡（需求方 2026-08-06 定稿）：上排＝局面脈絡（左）＋
//     **置右獨立**的受益隊擺動標示，中排＝打者·結果·投手（＋得分 chip、ΔRE24 chip），
//     下排＝雙色勝率條。新增的壘況與 ΔRE24 融入左側資訊區，不動右側元素的位置與存在感。
//   * 勝率擺動為主資訊、ΔRE24 降為次要 chip（`muted`）——一個對勝負、一個對得分期望，
//     互補而不重複。擺動量以**受益隊＋恆正值**標示（同生產卡），方向由隊名與隊色承載；
//     主隊視角只留在資料層與勝率條的幾何。
//   * WP 模型不可用時後端降級為 |ΔRE24| 選取，本卡**必須顯示降級註記**（不靜默換準則）。
//   * 垃圾時間（分差 ≥7）**不再降飽和**：|ΔWP| 選取下 81 場實測 0 命中（舊 |ΔRE24| 選法
//     為 15 命中），呈現層的補丁已無對象。事實旗標仍在資料裡、降級路徑仍可能選到，故
//     保留「分差 ≥7」文字標籤，只移除淡底。
//   * 每筆必附局面標示（局數／出局／壘況／分差），把「這打席重不重要」的判讀交給讀者。

import Link from "next/link";
import { Card, EmptyState, Eyebrow, PlayerLink } from "@/components/ui";
import { Re24Badge } from "@/components/re24-badge";
import { RunsBadge } from "@/components/runs-badge";
import { WP_SWING_DISCLOSURE, WpSwingBadge } from "@/components/wp-swing-badge";
import { WpSwingBar } from "@/components/wp-swing-bar";
import {
  halfLabel, marginText, personName, scoreAfterPlay, signedDelta, situationText, wpSwingLabel,
  type KeyPlaySelection, type PaFact,
} from "@/lib/game-facts";
import { methodologyHref } from "@/lib/methodology-anchors";
import { teamColor } from "@/lib/teams";

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

export function KeyPlays({ plays, selection, homeName, awayName, homeCode, awayCode, onJump }: {
  plays: PaFact[];
  selection?: KeyPlaySelection | null;
  homeName?: string | null;
  awayName?: string | null;
  homeCode?: string | null;
  awayCode?: string | null;
  onJump?: (eventNo: string) => void;
}) {
  const homeColor = teamColor(String(homeCode ?? ""));
  const awayColor = teamColor(String(awayCode ?? ""));
  // 降級＝後端拿不到 WP 模型時退回 |ΔRE24| 選取（signal 由後端揭露，前端不自行推斷）。
  const degraded = selection?.signal === "delta_re24";
  if (plays.length === 0) {
    return (
      <Card padding="p-3" className="min-w-0">
        <Eyebrow className="mb-2 px-1">關鍵打席</Eyebrow>
        <EmptyState>
          {degraded
            ? "本場沒有足以列為關鍵的打席（|ΔRE24| 皆低於門檻）。"
            : "本場沒有足以列為關鍵的打席（勝率擺動皆低於門檻）。"}
        </EmptyState>
      </Card>
    );
  }
  return (
    <Card padding="p-3" className="min-w-0">
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-2 px-2 pt-1">
        <span className="text-sm font-semibold">
          關鍵打席{" "}
          <span className="text-xs font-normal text-faint">
            {degraded ? "（依 |ΔRE24| 選出・依時間排列）" : "（依勝率擺動選出・依時間排列）"}
          </span>
        </span>
        {!degraded && (
          <Link href={methodologyHref("key-plays")}
            title={WP_SWING_DISCLOSURE}
            className="text-[10px] text-muted underline-offset-2 hover:underline">
            勝率變化・選取準則
          </Link>
        )}
      </div>
      {degraded && (
        <p className="mx-2 mb-1.5 rounded-lg bg-surface-2 px-2 py-1 text-[11px] text-muted">
          勝率模型目前不可用，本場改以得分期望值變化 |ΔRE24| 選取關鍵打席。
        </p>
      )}
      <ol className="space-y-0.5">
        {plays.map((play) => {
          // ΔRE24 併進打席敘述的同一行（需求方 2026-08-06：不要跟打席訊息分開）；
          // 受益隊擺動則獨立置右（同日定稿：沿用生產卡版式）。
          const hasSwing = play.delta_wp !== null && play.delta_wp !== undefined;
          const row = (
            <>
              {/* 上排＝局面脈絡（左）＋受益隊擺動（右，獨立元素）：生產「關鍵時刻」卡的
                  版式骨架，只把壘況／出局／分差併進左側資訊區。 */}
              <div className="flex items-baseline justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-muted">
                  {play.inning}{halfLabel(play.half)}
                  <BaseDiamond bases={play.bases_before} />
                  <span className="text-faint">{play.outs_before ?? "—"} 出局</span>
                  {marginText(play) && <span className="text-faint">{marginText(play)}</span>}
                  {play.garbage_time && (
                    <span className="rounded bg-surface-2 px-1 py-px text-[10px] text-muted">
                      分差 ≥7
                    </span>
                  )}
                </span>
                {hasSwing && (
                  <WpSwingBadge value={play.delta_wp} homeName={homeName} awayName={awayName}
                    homeColor={homeColor} awayColor={awayColor} />
                )}
              </div>
              <div className="mt-0.5 text-sm text-ink">
                <PlayerLink pid={play.hitter?.player_id} name={personName(play.hitter)} />
                <span className="mx-1 text-faint">·</span>
                {(play.result_action ?? "").trim()}
                <span className="ml-1.5 text-xs text-faint">投：{personName(play.pitcher)}</span>
                <RunsBadge runs={play.runs_on_play} {...(scoreAfterPlay(play) ?? {})} />
                <Re24Badge value={play.delta_re24} muted={hasSwing} />
              </div>
              {hasSwing && (
                <WpSwingBar before={play.wp_before} after={play.wp_after}
                  terminal={play.wp_after_terminal} homeColor={homeColor} awayColor={awayColor}
                  homeName={homeName} awayName={awayName} />
              )}
            </>
          );
          const swingLabel = wpSwingLabel(play.delta_wp, homeName, awayName);
          const swing = swingLabel ? `，勝率推向${swingLabel.team} ${swingLabel.pt} 個百分點` : "";
          const label = `${situationText(play)}，${personName(play.hitter)} `
            + `${play.result_action ?? ""}${swing}，ΔRE24 ${signedDelta(play.delta_re24)}`;
          return (
            <li key={play.pa_index}>
              {onJump && play.start_event_no ? (
                <button type="button" aria-label={label}
                  onClick={() => onJump(play.start_event_no!)}
                  className="block w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-2">
                  {row}
                </button>
              ) : (
                <div aria-label={label} className="rounded-lg px-2.5 py-2">
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
