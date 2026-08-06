// 關鍵打席的**勝率條**：打席後的勝率水平 ＋ 該打席造成的位移段。
//
// 需求方 2026-08-06 第五輪人工審第三階裁決：「我想保留原先的長條圖來顯示當前勝率以及
// 該打席造成的變化，而不是只顯示數字。」——沿用 `game-board.tsx` 的雙色勝率條視覺語言
// （客隊色｜主隊色，主隊佔比＝主隊勝率），再疊一段標示此打席造成的位移。
//
// 統計守門（裁決演進第三階，交付說明已寫給查核者）：條顯示的是**水平值的視覺化**，
// 與已上線的 WP 曲線同資訊類——曲線本來就逐點畫水平值，故揭露沿曲線既有框架
// （/methodology#winprob-validation 的 ±4–6pt 已知偏差），不另開新的誠實暴露面。
// 機率**水平值仍不作文字宣稱**：條上不印「X 隊有 62% 勝算」這種句子，只有視覺與擺動量。
//
// 顯示夾層（`lib/win-prob-display.ts` 是該規則的唯一擁有者）：非終點一律夾到 [1%, 99%]，
// 只有終場那一點（`terminal`）豁免——再見打席的條走到底是對的，8 局的 99.6% 不是。

import { displayWpPctInt } from "@/lib/win-prob-display";

export function WpSwingBar({ before, after, terminal = false, homeColor, awayColor,
                             homeName, awayName, className = "" }: {
  /** 打席前／後的主隊勝率（0–1）。 */
  before: number | null | undefined;
  after: number | null | undefined;
  /** `after` 是終場結果（豁免顯示夾層）。 */
  terminal?: boolean;
  homeColor: string;
  awayColor: string;
  homeName?: string | null;
  awayName?: string | null;
  className?: string;
}) {
  if (before === null || before === undefined || after === null || after === undefined) return null;
  // 打席前一律是局面推算值（不可能是終場點）→ 恆夾；打席後只有終點豁免。
  const b = displayWpPctInt(before, false);
  const a = displayWpPctInt(after, terminal);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;

  // 位移段＝兩個主隊勝率之間的區間（畫在主隊側的邊界上，方向即升降）。
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  const rising = a >= b;   // 主隊勝率上升
  const label = `${awayName || "客隊"} ${100 - a}%／${homeName || "主隊"} ${a}%`
    + `（此打席位移 ${hi - lo} 個百分點）`;

  return (
    <div className={`mt-1 ${className}`} title={label} aria-label={label} role="img">
      <div className="relative flex h-1.5 overflow-hidden rounded-full">
        {/* 底層：打席**後**的水平（客隊左、主隊右，與記分條的勝率條同方向） */}
        <div style={{ width: `${100 - a}%`, background: awayColor }} />
        <div style={{ width: `${a}%`, background: homeColor }} />
        {/* 疊層：此打席造成的位移段——用受益方的隊色描邊，方向靠位置本身表達 */}
        <span
          aria-hidden
          className="absolute inset-y-0 rounded-full ring-1 ring-inset ring-paper/70"
          style={{
            left: `${100 - hi}%`,
            width: `${Math.max(hi - lo, 0.6)}%`,
            background: rising ? homeColor : awayColor,
          }}
        />
      </div>
    </div>
  );
}
