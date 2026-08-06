// /methodology deep-link map（PRODUCT_UX_BLUEPRINT v0.2 §5.14、§7.1-5）。
// 頁面本體由 UX-MODEL-METHOD1 建立；本模組先固定 section id 與連結產生方式，
// 讓模型旁的說明 badge 有唯一且穩定的 anchor 契約，兩張卡不各自造字串。

export const METHODOLOGY_PATH = "/methodology";

/** §5.14 依「產品使用中的模型」分類的段落。key 即 anchor id。
 * winprob-validation（UX-WP-DISCLOSURE1）：場中 WP 的時間外驗證結論獨立成節，
 * 賽況頁 WP 曲線旁的誠實註記 deep-link 至此。
 * key-plays（UX-GAME-RECAP1）：賽後 recap 的關鍵打席「以勝率擺動選取＋顯示」的
 * 統計依據與守門條件，關鍵打席卡 deep-link 至此。 */
export const METHODOLOGY_SECTIONS = {
  pregame: "賽前勝率",
  winprob: "場中勝率 WP",
  "winprob-validation": "場中 WP 時間外驗證",
  "key-plays": "關鍵打席選取",
  "pa-sim": "打席結果分布",
  "matchup-credibility": "對戰 credibility",
  "pitch-type": "推定球種",
} as const;

export type MethodologySection = keyof typeof METHODOLOGY_SECTIONS;

/** 產生指向方法頁對應段落的連結；不帶 section 時回頁首。 */
export function methodologyHref(section?: MethodologySection): string {
  return section ? `${METHODOLOGY_PATH}#${section}` : METHODOLOGY_PATH;
}
