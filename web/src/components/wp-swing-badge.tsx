// 勝率擺動 [WP swing] 的**唯一呈現形式**（UI_UX_SYSTEM §10.4 registry 精神：同一概念
// 一個 owner，與 `re24-badge.tsx` 同規格）。
//
// 需求方 2026-08-06 第五輪人工審追加裁決：「直接拿預期勝率變化來顯示關鍵打席，我反而
// 覺得比較直覺，也跟我實際看到狀況一樣。」——關鍵打席由「以 |ΔWP| 選取、只顯示 ΔRE24」
// 升版為**直接顯示擺動量**。
//
// 視角紅線：**主隊視角**，正負與同頁下方 WP 曲線的升降完全對齊（曲線亦為主隊視角）。
// 兩處對照不打架是硬需求——所以這裡不做「受益隊視角」的翻號，受益隊資訊改由 tooltip
// 與 aria-label 用文字承載。
//
// 誠實守門（統計紅線修訂的配套，缺一不可）：
//   * 只顯示**變化量**，不顯示勝率水平值——unsupported 的是水平值宣稱（VAL1 中段
//     ±4–6pt 校準偏差），變化量的兩端點同帶偏差、方向性相消。
//   * tooltip 必帶偏差揭露；完整依據見 /methodology#key-plays。
//   * 取整數百分點（`signedWpPt`）：寫到小數是假精度。

import { signedWpPt } from "@/lib/game-facts";

export const WP_SWING_DISCLOSURE =
  "勝率變化依局面勝率模型推算（主隊視角，與下方勝率曲線同一模型）：" +
  "中段勝率的水平值有已知 ±4–6 個百分點偏差，變化量受影響較小。";

export function WpSwingBadge({ value, homeName, className = "" }: {
  value: number | null | undefined;
  /** 主隊隊名；缺席時 tooltip 退回「主隊」，不留空。 */
  homeName?: string | null;
  className?: string;
}) {
  const delta = value ?? null;
  const tone = delta === null ? "text-faint"
    : delta > 0 ? "text-up"
    : delta < 0 ? "text-down"
    : "text-muted";
  const home = homeName || "主隊";
  const direction = delta === null ? ""
    : delta > 0 ? `此打席使${home}勝率上升 ${Math.abs(Math.round(delta * 100))} 個百分點。`
    : delta < 0 ? `此打席使${home}勝率下降 ${Math.abs(Math.round(delta * 100))} 個百分點。`
    : "";
  return (
    <span
      title={`${direction}${WP_SWING_DISCLOSURE}`}
      className={`ml-1.5 inline-block whitespace-nowrap rounded bg-surface-2 px-1.5 py-px align-middle font-mono text-[11px] font-semibold tabular-nums ${tone} ${className}`}
    >
      勝率 {signedWpPt(delta)}
    </span>
  );
}
