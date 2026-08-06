// 勝率擺動 [WP swing] 的**唯一呈現形式**（UI_UX_SYSTEM §10.4 registry 精神：同一概念
// 一個 owner，與 `re24-badge.tsx` 同規格）。
//
// 需求方 2026-08-06 第五輪人工審追加裁決：「直接拿預期勝率變化來顯示關鍵打席，我反而
// 覺得比較直覺，也跟我實際看到狀況一樣。」＋樣式回饋：「上線版資訊比較少但可視度比較
// 清楚，像『ＸＸＸ隊＋Ｏ％』就很明顯。」
//
// 標示法＝**受益隊＋恆正值**（同生產「關鍵時刻」卡）：不是「勝率 −23pt」而是
// 「樂天桃猿 +23pt」。內部資料維持主隊視角（`delta_wp` 正＝主隊上升），受益方轉換只在
// 顯示層（`wpSwingLabel`）——讀者不必先知道誰是主隊、也不必解讀負號。方向資訊改由隊名
// 與隊色承載，同列的雙色勝率條再給出位移的位置與幅度；曲線對照則由條的幾何維持。
//
// 版式（需求方 2026-08-06 定稿）：**沿用生產「關鍵時刻」卡的原本版式**——不是內嵌在
// 敘述行裡的 chip，而是該列**置右、獨立**的元素（呼叫端以 `justify-between` 放在資訊列
// 右側，本元件負責 `shrink-0` 不被擠壓）。呈現＝受益隊隊色的等寬粗體文字、無底色，
// 與生產版逐項相同：底色會削弱「獨立標示」的存在感，也和左側的 chip 群打架。
//
// 色彩：受益隊隊色（隊色＝身分，走 `lib/teams.ts`，不進 @theme）。
//
// 誠實守門（統計紅線修訂的配套，缺一不可）：
//   * 只顯示**變化量**，不顯示勝率水平值——unsupported 的是水平值宣稱（VAL1 中段
//     ±4–6pt 校準偏差），變化量的兩端點同帶偏差、方向性相消。
//   * tooltip 必帶偏差揭露；完整依據見 /methodology#key-plays。
//   * 取整數百分點：寫到小數是假精度。

import { wpSwingLabel } from "@/lib/game-facts";

export const WP_SWING_DISCLOSURE =
  "勝率變化依局面勝率模型推算（與下方勝率曲線同一模型）：" +
  "中段勝率的水平值有已知 ±4–6 個百分點偏差，變化量受影響較小。";

export function WpSwingBadge({ value, homeName, awayName, homeColor, awayColor, className = "" }: {
  /** 主隊視角的勝率變化（0–1；正＝主隊上升）。顯示時轉為受益隊視角。 */
  value: number | null | undefined;
  homeName?: string | null;
  awayName?: string | null;
  homeColor: string;
  awayColor: string;
  className?: string;
}) {
  const swing = wpSwingLabel(value, homeName, awayName);
  if (!swing) return null;
  const color = swing.home ? homeColor : awayColor;
  return (
    <span
      title={`此打席把勝率推向${swing.team} ${swing.pt} 個百分點。${WP_SWING_DISCLOSURE}`}
      className={`shrink-0 whitespace-nowrap font-mono text-xs font-semibold tabular-nums ${className}`}
      style={{ color }}
    >
      {swing.text}
    </span>
  );
}
