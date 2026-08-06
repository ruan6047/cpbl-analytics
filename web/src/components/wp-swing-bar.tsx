// 關鍵打席的**勝率條**：打席後的勝率水平 ＋ 該打席造成的位移段。
//
// 需求方 2026-08-06 第五輪人工審第三階裁決：「我想保留原先的長條圖來顯示當前勝率以及
// 該打席造成的變化，而不是只顯示數字。」＋第四階樣式回饋：「之前關鍵打席差值會改用輔色，
// 感覺那樣效果比較好」——**視覺完全對齊生產上線版**的「關鍵時刻」卡
// （`games/[sno]/overview.tsx` 的 `MomentRow`，即目前 cpbl.ruan-ruan.com 跑的版本）：
//   * 底層雙色條：左＝客隊色、右＝主隊色，交界＝打席後的主隊勝率。
//   * 位移段＝**受益隊的輔助色**（同色相的亮版 tint，`color-mix` 55% white）＋白色左右邊界，
//     色相相同保住「這一打席往哪隊推」的語意，亮度差提供辨識度。
//   * 條高 h-2、邊界 border-x border-white/70 皆與生產版逐項相同。
//
// 為什麼是複製而不是 import 生產那支：`MomentRow` 是舊 fallback 路徑的內部元件，吃的是
// 近似分組的 `Moment`；本元件吃事實流的 canonical 打席。兩者資料源不同、生命週期不同
//（fallback 遲早退場），共用會把舊路徑釘死；視覺契約則以本註解與下方常數對齊。
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

  // 受益隊用**原值**判定，不吃夾層（與生產版同一條註記）：夾層是顯示規則，極端局面下
  // 夾過的兩端可能相等，但「這一打席往哪隊推」是事實，不該被顯示規則抹掉。
  const gain = after - before > 0;                       // 主隊受益
  const aux = `color-mix(in srgb, ${gain ? homeColor : awayColor} 55%, white)`;
  // 幾何與生產版同式：以客隊側（左）為座標，交界＝1 − 主隊勝率。
  const lo = Math.min(100 - a, 100 - b);
  const hi = Math.max(100 - a, 100 - b);
  const label = `${awayName || "客隊"} ${100 - a}%／${homeName || "主隊"} ${a}%`
    + `（此打席位移 ${hi - lo} 個百分點）`;

  return (
    <div className={`mt-1.5 ${className}`} title={label} aria-label={label} role="img">
      <div className="relative flex h-2 overflow-hidden rounded-full">
        {/* 底層：打席**後**的水平（客隊左、主隊右，與記分條的勝率條同方向） */}
        <div style={{ width: `${100 - a}%`, background: awayColor }} />
        <div style={{ width: `${a}%`, background: homeColor }} />
        {/* 位移段：受益隊輔助色（亮版隊色）＋白色左右邊界，同生產版 */}
        <div aria-hidden className="absolute inset-y-0 border-x border-white/70"
          style={{ left: `${lo}%`, width: `${hi - lo}%`, background: aux }} />
      </div>
    </div>
  );
}
