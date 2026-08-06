// 得分事件的**唯一呈現形式**（與 `re24-badge.tsx` 同一套視覺語言）。
//
// 需求方 2026-08-06 第三輪人工審：「有得分的文字訊息好像有些突兀，它很重要但字好像太大了。
// 字體大小維持（一般字級），但得分出現獨立 UI 來展演得分、或展示比分。」
//
// 原本得分列是靠**放大字級**取得注意力（該分支只給顏色沒給 size，於是繼承 text-base，
// 其餘列都是 text-sm）。改為：敘述文字回到一般字級，重要性改由本 chip 承載——
// 一眼看到「進帳幾分」與「比分變成幾比幾」，資訊量比放大字體更高。
//
// 與 Re24Badge 的關係：**幾何與字體完全一致**（同 rounded / px / py / 字級 / tabular-nums），
// 只有底色語意不同（得分＝accent 淡底、ΔRE24＝中性 surface-2 底），同列並排不打架。

export function RunsBadge({ runs, away, home, className = "" }: {
  /** 該打席／該事件進帳分數（> 0 才顯示）。 */
  runs: number | null | undefined;
  /** 該次得分**之後**的比分；缺值時只顯示進帳分數，不猜。 */
  away?: number | null;
  home?: number | null;
  className?: string;
}) {
  if (!runs || runs <= 0) return null;
  const hasScore = away !== null && away !== undefined && home !== null && home !== undefined;
  return (
    <span
      title={hasScore ? `本打席得 ${runs} 分，比分 ${away}:${home}（客:主）` : `本打席得 ${runs} 分`}
      className={`ml-1.5 inline-flex items-center gap-1 whitespace-nowrap rounded bg-accent/10 px-1.5 py-px align-middle font-mono text-[11px] font-semibold tabular-nums text-accent ${className}`}
    >
      +{runs}
      {hasScore && <span className="font-normal text-muted">{away}–{home}</span>}
    </span>
  );
}
