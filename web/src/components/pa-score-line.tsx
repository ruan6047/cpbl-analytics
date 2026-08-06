// 得分事件的**唯一呈現形式**：合體版比分列 `[客隊徽] 2：4(+2) [主隊徽]`。
//
// 需求方 2026-08-06 第六輪人工審定案：比分與進帳原本是兩個各自為政的 chip（`+2` 掛在事件列、
// `2–4` 掛在卡內），讀者要自己把兩處拼起來才知道「誰得分、變成幾比幾」。合體為單一元素後
// 一眼可讀：隊徽錨定左右（客左主右，與記分板／全站欄序一致），`(+N)` 黏在**得分側**的數字上，
// 所以「哪隊得分」由位置本身表達，不必再讀文字。
//
// 位置是**清單級**而非卡內：與「更換選手」那類事件列同層級，獨立成一列排在該得分打席之後
// （得分是打席的結算事實，不是卡內的又一個 chip）。卡內因此不再重複比分，同一數字不兩處各說一次。
//
// 比分語意：一律吃 `score_after`（該打席**得分後**的比分），**禁止**用前值＋進帳推算——
// 那是已修過的 bug（多次得分／佈局列會算錯）；取值單點收斂在 `paScoreLineOf`。

import { TeamLogo } from "@/components/ui";
import type { PaScoreLineData } from "@/lib/pa-card";

export function PaScoreLine({ away, home, runs, side, awayName, homeName, className = "" }: PaScoreLineData & {
  awayName?: string | null;
  homeName?: string | null;
  className?: string;
}) {
  const gain = <span className="text-accent">(+{runs})</span>;
  const teamText = (which: "away" | "home") =>
    (which === "away" ? awayName : homeName) || (which === "away" ? "客隊" : "主隊");
  // 隊徽與數字排版對螢幕閱讀器是無意義的碎片，故視覺部分 aria-hidden，另給完整句子。
  const sr = `此打席後比分 ${teamText("away")} ${away}，${teamText("home")} ${home}；`
    + `${side ? teamText(side) : "本打席"}進帳 ${runs} 分`;
  return (
    <div className={`flex items-center gap-1.5 rounded bg-accent/5 px-2 py-0.5 text-sm ${className}`}>
      <span className="sr-only">{sr}</span>
      <TeamLogo name={awayName} size={16} decorative />
      <span aria-hidden className="font-mono font-semibold tabular-nums text-ink">
        {away}{side === "away" && gain}
        <span className="text-faint">：</span>
        {home}{side === "home" && gain}
        {side === null && <span className="ml-1">{gain}</span>}
      </span>
      <TeamLogo name={homeName} size={16} decorative />
    </div>
  );
}
