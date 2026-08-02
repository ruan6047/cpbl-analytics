type BrandMarkProps = {
  className?: string;
  title?: string;
  /**
   * `full`（預設）＝含五官的完整標誌，用於 logo 與 favicon。
   * `silhouette`＝只有本壘板外形，用於放大當背景紋理的場合。
   *
   * 為什麼要分兩態：五官的尺寸是為 16–32px 調的，放大到數百 px 當浮水印時，眼睛會變成
   * 孤立大圓、微笑弧被容器裁切，臉的讀法反而散掉。繁簡兩態是標誌設計的常規解法，
   * 不是兩個不同的標誌——外形完全一致。
   */
  variant?: "full" | "silhouette";
};

/** 本壘板外形；五官另外疊加。兩處（本檔與 app/icon.svg）必須同形。 */
const PLATE = "M8 8h48v24L32 56 8 32z";
/** 側面笑臉：圓＝眼＝球，弧＝微笑＝進壘軌跡。 */
const FACE =
  " M36 21a4.4 4.4 0 1 0 8.8 0 4.4 4.4 0 1 0-8.8 0z M16 28.5Q23 44 39 36.5L37.4 33.3Q24.8 39.2 19.3 27.2Z";

/** 本壘板輪廓中的 R：品牌文字已提供名稱時，呼叫端應標為 aria-hidden。 */
export function BrandMark({ className, title, variant = "full" }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title && <title>{title}</title>}
      {/* 本壘板：最寬處＝上緣，兩側先垂直下行再收斂成尖端；17×17 等比（上邊 48、直邊 24、
          斜邊投影 24）。勿改成上緣內縮的版本——那會讀成盾牌／徽章而非本壘板。

          板內是**側面笑臉**（需求方 2026-08-02 人工審定案）：圓＝眼睛，同時是球；弧＝微笑，
          同時是進壘軌跡。一個形狀兩種讀法，對應「用視覺化讓棒球更好懂」——親近感是刻意的，
          不是意外。改動前先讀三條約束：
          1. **不得放字母。** 原版用 R，需求方指出撞樂天桃猿標誌；聯盟內球隊的識別不可挪用，
             且 wordmark 旁就是品牌名，字母是重複資訊。
          2. **笑臉是需求，不是待修的巧合。** 曾一度把它改成離散取樣點以「避免被讀成臉」，
             需求方明確退回——要的就是笑臉意象。
          3. 眼與弧的相對位置決定側臉讀法能否成立（規劃者曾指出對稱五邊形不提供側臉輪廓、
             讀法依賴觀者腦補，需求方權衡後仍選側面）。移動任一元素前先確認臉還在。

          全部以 evenodd 打成真鏤空而非填色遮蓋：填色版只在 surface-2 底上正確，放到頂欄
          （surface 底）會變成比背景淺的色塊。單一 path 才能讓任何底色透出來。 */}
      <path
        fill="currentColor"
        fillRule="evenodd"
        d={variant === "silhouette" ? PLATE : PLATE + FACE}
      />
    </svg>
  );
}
