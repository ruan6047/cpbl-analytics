// PitchMind 示意頁：戰術清單與對應（#452）。
//
// 這是**唯一**要改戰術時動的檔案：名稱、來球條件、說明標籤、關注的打者反應，
// 以及情蒐依據／動態累積各自讀哪些來源。初版全部為示意對應，不是已驗證的戰術定義；
// 指標、模型與門檻由 PitchMind 研究另行處理（~/Dev/Rebas）。
//
// ⛔ 不在這裡放「有效率」「被識破機率」或任何把多個指標合成分數的欄位：
//    示意頁只呈現條件歷史率與本場累積，不解讀戰術好壞（#452 限制與非目標）。

import type { Family, HLoc, ReactionKey, SourceKey, TacticTag, VLoc } from "./model.ts";

export type Tactic = {
  id: string;
  name: string;
  /** 來球條件：同時符合球種族群、水平與垂直位置，且壘上無人才算一次機會。 */
  condition: { family: Family; h: readonly HLoc[]; v: readonly VLoc[]; text: string };
  /** 隨戰術自動帶出的說明標籤（顯示用，不可操作）。 */
  tags: readonly TacticTag[];
  /** 每個標籤在此戰術下的白話說明。 */
  tagNotes: Partial<Record<TacticTag, string>>;
  /** 關注的打者反應（依序顯示）。 */
  reactions: readonly ReactionKey[];
  /** 情蒐依據要並列的來源（依序顯示）。 */
  scoutingSources: readonly SourceKey[];
  /** 左側熱區圖要看的既有指標（沿用 Grid3x3 的 metric）。 */
  heatMetric: { metric: "whiff" | "la"; title: string };
};

export const ALL_TAGS: readonly TacticTag[] = ["共軌", "速差", "引誘"];

export const TACTICS: readonly Tactic[] = [
  {
    id: "outside-high",
    name: "外角高球",
    condition: { family: "fastball", h: ["outside"], v: ["high"], text: "速球族群・外角高（含帶外一顆球）・壘上無人" },
    tags: ["速差", "引誘"],
    tagNotes: {
      速差: "對照同打席前一球的球速差（實測值列於下方來球對照）",
      引誘: "關注打者是否對帶外高球出棒",
    },
    reactions: ["swing", "whiff"],
    scoutingSources: ["long", "recent", "league", "pitcher"],
    heatMetric: { metric: "whiff", title: "揮空率" },
  },
  {
    id: "inside-low",
    name: "內角低球",
    condition: { family: "breaking", h: ["inside"], v: ["low"], text: "變化球族群・內角低・壘上無人" },
    tags: ["共軌", "引誘"],
    tagNotes: {
      共軌: "前後兩球出手後軌跡相近的程度；本頁未接軌跡資料，僅列為說明",
      引誘: "關注打者是否對內角低變化球出棒、出棒後是否擊成滾地",
    },
    reactions: ["swing", "grounder"],
    scoutingSources: ["long", "recent", "league", "pitcher"],
    heatMetric: { metric: "la", title: "擊球仰角 AVG" },
  },
];

/** 反應的定義：分子欄位與分母。說明只描述量的是什麼，不寫「越高越好」。 */
export const REACTIONS: Record<ReactionKey, { label: string; den: "n" | "swing"; denLabel: string; meaning: string }> = {
  swing: { label: "出棒", den: "n", denLabel: "符合條件來球", meaning: "打者對這類來球出棒的比例" },
  whiff: { label: "揮空", den: "swing", denLabel: "出棒", meaning: "出棒中未碰到球的比例" },
  grounder: { label: "擊成滾地", den: "swing", denLabel: "出棒", meaning: "出棒中擊成滾地球的比例" },
};

export const SOURCES: Record<SourceKey, { label: string; period: string; scope: "batter" | "league" | "pitcher" }> = {
  long: { label: "打者長期", period: "2025–2026 例行賽（扣除近 10 出賽日）", scope: "batter" },
  recent: { label: "打者近期", period: "近 10 個出賽日", scope: "batter" },
  league: { label: "聯盟參考", period: "2026 例行賽・全體右打者", scope: "league" },
  pitcher: { label: "投手對右打", period: "2025–2026・投手 B 對右打者", scope: "pitcher" },
};

export const FAMILY_ZH: Record<Family, string> = { fastball: "速球", breaking: "變化球" };
export const H_ZH: Record<HLoc, string> = { inside: "內角", middle: "中間", outside: "外角" };
export const V_ZH: Record<VLoc, string> = { high: "高", mid: "中", low: "低" };
