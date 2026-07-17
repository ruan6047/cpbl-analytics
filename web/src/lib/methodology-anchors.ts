// /methodology deep-link map（PRODUCT_UX_BLUEPRINT v0.2 §5.14、§7.1-5）。
// 頁面本體由 UX-MODEL-METHOD1 建立；本模組先固定 section id 與連結產生方式，
// 讓模型旁的說明 badge 有唯一且穩定的 anchor 契約，兩張卡不各自造字串。

export const METHODOLOGY_PATH = "/methodology";

/** §5.14 依「產品使用中的模型」分類的段落。key 即 anchor id。 */
export const METHODOLOGY_SECTIONS = {
  pregame: "賽前勝率",
  winprob: "場中勝率 WP",
  "pa-sim": "打席結果分布",
  "matchup-credibility": "對戰 credibility",
  "pitch-type": "推定球種",
} as const;

export type MethodologySection = keyof typeof METHODOLOGY_SECTIONS;

/** 產生指向方法頁對應段落的連結；不帶 section 時回頁首。 */
export function methodologyHref(section?: MethodologySection): string {
  return section ? `${METHODOLOGY_PATH}#${section}` : METHODOLOGY_PATH;
}
