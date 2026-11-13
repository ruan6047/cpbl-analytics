// PitchMind 示意頁：戰術清單與對應（#452）。
//
// 這是**唯一**要改戰術時動的檔案：名稱（球種＋區域）、戰術目的、來球條件、說明標籤、
// 關注的打者反應，以及情蒐指標要並列哪些來源。全部為示意對應，不是已驗證的戰術定義；
// 指標、模型、刻度、權重與門檻由 PitchMind 研究另行處理（~/Dev/Rebas）。
//
// ⛔ 不在這裡放有效率、被識破機率、警戒線，或把多個指標合成分數的欄位（#452 修正二第五節）。

import type { HLoc, ReactionKey, SourceKey, TacticTag, VLoc } from "./model.ts";

export type Tactic = {
  id: string;
  /** 名稱＝區域＋球種（或球種家族） */
  name: string;
  /** 戰術目的（一句話，示意） */
  purpose: string;
  /** 來球條件：球種、水平與垂直位置都符合，且壘上無人，才算一次相關觀察。 */
  condition: { pitch: string; h: readonly HLoc[]; v: readonly VLoc[]; text: string };
  /** 隨戰術帶出的唯讀說明標籤（不可操作、不代表已量測效果）。 */
  tags: readonly TacticTag[];
  tagNotes: Partial<Record<TacticTag, string>>;
  /** 關注的打者反應；第一個用在兩欄上方的快讀摘要。 */
  reactions: readonly ReactionKey[];
  /** 情蒐指標要並列的來源（依序顯示）。 */
  scoutingSources: readonly SourceKey[];
  /** 左欄熱區圖要看的既有指標（沿用 Grid3x3 的 metric）。 */
  heatMetric: { metric: "whiff" | "la"; title: string };
};

export const ALL_TAGS: readonly TacticTag[] = ["共軌", "速差", "引誘"];

export const TACTICS: readonly Tactic[] = [
  {
    id: "outside-high-fastball",
    name: "外角高速球",
    purpose: "引誘打者追打帶外的高速球",
    condition: { pitch: "速球", h: ["outside"], v: ["high"], text: "速球・外角高（含帶外一顆球）・壘上無人" },
    tags: ["速差", "引誘"],
    tagNotes: {
      速差: "對照前一球的球速差（實測球速見下方量測對照）",
      引誘: "關注打者是否對帶外高球出棒",
    },
    reactions: ["swing", "whiff"],
    scoutingSources: ["long", "recent", "league", "pitcher"],
    heatMetric: { metric: "whiff", title: "揮空率" },
  },
  {
    id: "outside-low-slider",
    name: "外角低滑球",
    purpose: "引誘打者追打往外角低處跑的滑球",
    condition: { pitch: "滑球", h: ["outside"], v: ["low"], text: "滑球・外角低・壘上無人" },
    tags: ["共軌", "引誘"],
    tagNotes: {
      共軌: "前後兩球出手後軌跡相近的程度；本頁未接軌跡資料，僅列為說明",
      引誘: "關注打者是否對外角低滑球出棒、是否擊成滾地",
    },
    reactions: ["swing", "grounder"],
    scoutingSources: ["long", "recent", "league", "pitcher"],
    heatMetric: { metric: "la", title: "擊球仰角 AVG" },
  },
];

/** 反應的定義。分母一律是「符合條件的來球」；說明只描述量的是什麼，不寫好壞。 */
export const REACTIONS: Record<ReactionKey, { label: string; denLabel: string; meaning: string }> = {
  swing: { label: "出棒", denLabel: "符合條件來球", meaning: "打者對這類來球出棒的比例" },
  whiff: { label: "揮空", denLabel: "符合條件來球", meaning: "這類來球中打者揮空的比例" },
  grounder: { label: "擊成滾地", denLabel: "符合條件來球", meaning: "這類來球中被擊成滾地球的比例" },
};

export const SOURCES: Record<SourceKey, { label: string; period: string; scope: "batter" | "league" | "pitcher" }> = {
  long: { label: "打者長期", period: "2025–2026 例行賽（扣除近 30 出賽日）", scope: "batter" },
  recent: { label: "打者近況", period: "近 30 個出賽日", scope: "batter" },
  league: { label: "聯盟參考", period: "2026 例行賽・全體右打者", scope: "league" },
  pitcher: { label: "投手對右打", period: "2025–2026・投手 B 對右打者", scope: "pitcher" },
};

export const H_ZH: Record<HLoc, string> = { inside: "內角", middle: "中間", outside: "外角" };
export const V_ZH: Record<VLoc, string> = { high: "高", mid: "中", low: "低" };
