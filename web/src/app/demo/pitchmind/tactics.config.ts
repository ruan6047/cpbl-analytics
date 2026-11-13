// PitchMind 示意頁：戰術清單、反應種類與示意指標的增減（#452 修正三）。
//
// 這是**唯一**要改戰術時動的檔案：名稱（球種＋區域）、戰術目的、來球條件、說明標籤、
// 關注的打者反應、每類反應讓示意指標增減多少。全部為示意，不是已驗證的定義或權重；
// 正式指標、刻度、權重與門檻由 PitchMind 研究另行處理（~/Dev/Rebas）。
//
// ⛔ 示意指標不是有效率、被識破機率或已校準的警戒線；不要在這裡加這類欄位。

import type { HLoc, Outcome, ReactionKey, SourceKey, TacticTag, VLoc } from "./model.ts";

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
  /** 這個戰術關注的反應：主畫面先列這幾類，其餘收在「其他反應」。 */
  focus: readonly ReactionKey[];
  /** 每類反應讓示意指標增減多少（示意點數）：正＝與戰術目的相反的反應，負＝符合戰術目的。 */
  points: Record<Outcome, number>;
  /** 情蒐指標要並列的來源（依序顯示）。 */
  scoutingSources: readonly SourceKey[];
  /** 左欄熱區圖要看的既有指標（沿用 Grid3x3 的 metric）。 */
  heatMetric: { metric: "whiff" | "la"; title: string };
};

export const ALL_TAGS: readonly TacticTag[] = ["共軌", "速差", "引誘"];

/** 反應種類（示意定義）。六類互斥，每球恰好一類；「出棒」是彙總。分母一律是符合條件的來球數。 */
export const REACTIONS: Record<ReactionKey, { label: string; def: string }> = {
  swing: { label: "出棒", def: "對這類來球揮棒（＝揮空＋界外＋擊入場內）" },
  whiff: { label: "揮空", def: "揮棒沒碰到球" },
  foul: { label: "界外", def: "碰到球但打成界外" },
  weak: { label: "無效擊球", def: "擊入場內的弱擊球（示意：內野滾地、內野高飛，或擊球初速偏低）" },
  solid: { label: "一般擊球", def: "擊入場內，不屬於無效擊球或強勁擊球" },
  hard: { label: "強勁擊球", def: "擊入場內且擊球初速高（示意：150 km/h 以上）" },
  take: { label: "未出棒", def: "沒有揮棒（含看好球與選掉的壞球）" },
};
/** 畫面列出反應時的固定順序。 */
export const REACTION_ORDER: readonly ReactionKey[] = ["swing", "whiff", "foul", "weak", "solid", "hard", "take"];

/** 示意指標的共用設定：尺度 0–100；與參考線差距在 nearBand 以內算「正在接近」。 */
export const DEMO_RULES = { min: 0, max: 100, nearBand: 15 };

/** 引誘型戰術共用的示意點數：沒被引誘或打得紮實＝上升；追打揮空、打不好＝下降。 */
const LURE_POINTS: Record<Outcome, number> = { take: 12, foul: 8, solid: 8, hard: 14, whiff: -12, weak: -10 };

export const TACTICS: readonly Tactic[] = [
  {
    id: "outside-high-fastball",
    name: "外角高速球",
    purpose: "引誘打者追打帶外的高速球",
    condition: { pitch: "速球", h: ["outside"], v: ["high"], text: "速球・外角高（含帶外一顆球）・壘上無人" },
    tags: ["速差", "引誘"],
    tagNotes: {
      速差: "對照前一球的球速差（實測球速見量測對照）",
      引誘: "關注打者是否對帶外高球出棒",
    },
    focus: ["swing", "whiff", "weak", "hard"],
    points: LURE_POINTS,
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
      引誘: "關注打者是否對外角低滑球出棒、是否打成無效擊球",
    },
    focus: ["swing", "whiff", "weak", "take"],
    points: LURE_POINTS,
    scoutingSources: ["long", "recent", "league", "pitcher"],
    heatMetric: { metric: "la", title: "擊球仰角 AVG" },
  },
];

export const SOURCES: Record<SourceKey, { label: string; period: string; scope: "batter" | "league" | "pitcher" }> = {
  long: { label: "打者長期", period: "2025–2026 例行賽（扣除近 30 出賽日）", scope: "batter" },
  recent: { label: "打者近況", period: "近 30 個出賽日", scope: "batter" },
  league: { label: "聯盟參考", period: "2026 例行賽・全體右打者", scope: "league" },
  pitcher: { label: "投手對右打", period: "2025–2026・投手 B 對右打者", scope: "pitcher" },
};

export const H_ZH: Record<HLoc, string> = { inside: "內角", middle: "中間", outside: "外角" };
export const V_ZH: Record<VLoc, string> = { high: "高", mid: "中", low: "低" };
