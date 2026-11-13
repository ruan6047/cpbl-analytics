// PitchMind 示意頁的資料形狀（#452）。只描述示意頁用到的欄位，不是任何正式 API 契約。

export type HLoc = "inside" | "middle" | "outside";
export type VLoc = "high" | "mid" | "low";
/** 打者反應分類（示意）。各戰術在設定檔裡給每類一個示意點數。 */
export type Reaction = "hard" | "take" | "foul" | "called" | "whiff" | "weak";
export type TacticTag = "共軌" | "速差" | "引誘";
export type ZoneResult = "hit" | "out" | "foul" | "whiff" | "take";

export type Bases = { first: boolean; second: boolean; third: boolean };

/** 「下一球投出前」的已知局面。 */
export type Situation = {
  inning: number;
  half: "top" | "bottom";
  batter: string;
  batterHand: "R" | "L";
  pitcher: string;
  balls: number;
  strikes: number;
  outs: number;
  bases: Bases;
};

type EventBase = { id: string; label: string; after: Situation; /** 展演劇本註記（只在展演控制區顯示） */ script?: string };

/** 打者上場：只改局面，不計入任何累積。 */
export type PaStartEvent = EventBase & { kind: "pa_start" };

/** 一球。投出前局面＝前一事件的 after，故不重複存。 */
export type PitchEvent = EventBase & {
  kind: "pitch";
  seq: number;
  /** 球種（沿用本站球種名稱，供 pitchColor 取色） */
  pitch: string;
  h: HLoc;
  v: VLoc;
  /** 捕手視角座標（示意）：x 正值＝一壘側（右打者的外角），y＝離地高度（近似） */
  x: number;
  y: number;
  speed: number;
  reaction: Reaction;
  zoneResult: ZoneResult;
  resultText: string;
};

export type GameEvent = PaStartEvent | PitchEvent;
