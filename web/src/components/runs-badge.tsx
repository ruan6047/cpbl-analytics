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

/**
 * 打席層級的**比分**（得分打席才顯示）。
 *
 * 需求方 2026-08-06 第五輪人工審：「分數變動可以放到跟球員名稱同樣層級，字樣可以放大
 * ——畢竟是關鍵資訊；打點數（+N 進帳）留在原先位置。」故比分自事件列上移到打席標題列，
 * 與打者名同層級同字級；`RunsBadge` 的 `+N` 留在原位、原大小（進帳是事件層級的事實）。
 *
 * 客隊在前（`{away}–{home}`），與記分板欄序、`RunsBadge` 內的比分寫法完全一致。
 */
export function ScoreAfterBadge({ away, home, className = "" }: {
  away?: number | null;
  home?: number | null;
  className?: string;
}) {
  if (away === null || away === undefined || home === null || home === undefined) return null;
  return (
    <span
      title={`此打席後比分 ${away}:${home}（客:主）`}
      className={`ml-2 inline-block whitespace-nowrap rounded bg-accent/10 px-1.5 align-middle font-mono text-sm font-bold tabular-nums text-accent ${className}`}
    >
      {away}–{home}
    </span>
  );
}
