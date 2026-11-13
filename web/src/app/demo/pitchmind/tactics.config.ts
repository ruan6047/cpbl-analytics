// PitchMind 示意頁：戰術清單、參考界線與累積規則（#452）。
//
// 這是**唯一**要改戰術時動的檔案。全部內容都是**示意**：參考值、反應點數、接近區寬度
// 都是為展演手編的數字，不是已驗證的方法或門檻；指標、模型與門檻由 PitchMind 研究另行處理。
//
// ⛔ 兩個值都不是有效率、被識破率或成功機率；尺度是 0–100 的示意點數，不是百分比。
// ⛔ 不在這裡加任何把多個指標合成「戰術分數」的欄位。

import type { HLoc, Reaction, TacticTag, VLoc } from "./model.ts";

export type Tactic = {
  id: string;
  /** 名稱同時含區域與球種 */
  name: string;
  /** 來球條件：球種、水平／垂直位置都符合，且壘上無人，才算一次該戰術的觀察。 */
  condition: { pitch: string; h: readonly HLoc[]; v: readonly VLoc[] };
  /** 隨戰術顯示的說明標籤（不可操作、不代表已量測效果）。 */
  tags: readonly TacticTag[];
  /** 情蒐參考值（示意）：兩好球前／兩好球時各一條界線。 */
  reference: { preTwoStrike: number; twoStrike: number };
  /** 每類反應對「動態累積值」的示意點數：正＝不利反應證據增加，負＝符合預期的反應。 */
  points: Record<Reaction, number>;
};

/** 反應分類的顯示名稱。 */
export const REACTION_ZH: Record<Reaction, string> = {
  hard: "強勁擊球",
  take: "帶外未追",
  foul: "跟上界外",
  called: "看好球",
  whiff: "追打揮空",
  weak: "弱擊球出局",
};

const DEFAULT_POINTS: Record<Reaction, number> = { hard: 12, take: 12, foul: 8, called: 0, whiff: -12, weak: -10 };

export const ALL_TAGS: readonly TacticTag[] = ["共軌", "速差", "引誘"];

/** 示意規則的共用參數。 */
export const DEMO_RULES = {
  /** 尺度上下限（示意點數） */
  min: 0,
  max: 100,
  /** 距參考值這麼近（含）以內算「正在接近」 */
  nearBand: 15,
};

export const TACTICS: readonly Tactic[] = [
  {
    id: "outside-high-fastball",
    name: "外角高速球",
    condition: { pitch: "速球", h: ["outside"], v: ["high"] },
    tags: ["速差", "引誘"],
    reference: { preTwoStrike: 80, twoStrike: 75 },
    points: DEFAULT_POINTS,
  },
  {
    id: "outside-low-slider",
    name: "外角低滑球",
    condition: { pitch: "滑球", h: ["outside"], v: ["low"] },
    tags: ["共軌", "引誘"],
    reference: { preTwoStrike: 70, twoStrike: 65 },
    points: DEFAULT_POINTS,
  },
  {
    id: "inside-high-fastball",
    name: "內角高速球",
    condition: { pitch: "速球", h: ["inside"], v: ["high"] },
    tags: ["速差"],
    reference: { preTwoStrike: 85, twoStrike: 80 },
    points: DEFAULT_POINTS,
  },
];

export const H_ZH: Record<HLoc, string> = { inside: "內角", middle: "中間", outside: "外角" };
export const V_ZH: Record<VLoc, string> = { high: "高", mid: "中", low: "低" };
