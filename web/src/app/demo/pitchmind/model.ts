// PitchMind 示意頁的資料形狀（#452）。只描述示意頁用到的欄位，不是任何正式 API 契約。

export type HLoc = "inside" | "middle" | "outside";
export type VLoc = "high" | "mid" | "low";
export type ReactionKey = "swing" | "whiff" | "grounder";
export type TacticTag = "共軌" | "速差" | "引誘";
export type SourceKey = "long" | "recent" | "league" | "pitcher";
export type CountKey = `${0 | 1 | 2 | 3}-${0 | 1 | 2}`;
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

type EventBase = {
  id: string;
  label: string;
  after: Situation;
  /** 展演劇本步驟（只在展演控制區顯示，對應裁定的 A–G） */
  script?: string;
};

/** 打者上場：只改局面，不計入任何累積。 */
export type PaStartEvent = EventBase & { kind: "pa_start" };

/** 一球。投出前局面＝前一事件的 after，故不重複存。 */
export type PitchEvent = EventBase & {
  kind: "pitch";
  seq: number;
  /** 球種（沿用本站球種名稱） */
  pitch: string;
  h: HLoc;
  v: VLoc;
  /** 捕手視角座標（示意）：x 正值＝一壘側（右打者的外角），y＝離地高度（近似） */
  x: number;
  y: number;
  speed: number;
  swing: boolean;
  whiff: boolean;
  grounder: boolean;
  zoneResult: ZoneResult;
  resultText: string;
};

export type GameEvent = PaStartEvent | PitchEvent;

/** 基準格：[符合條件來球數 n, 出棒, 揮空, 擊成滾地]；null＝缺值／待補。 */
export type BaselineEntry = readonly [n: number, swing: number, whiff: number, grounder: number] | null;
export type CountTable = Partial<Record<CountKey, BaselineEntry>>;
/** 每個戰術：聯盟與投手各一張表；打者長期／近期依打者分開。 */
export type BaselineTable = Record<string, {
  league: CountTable;
  pitcher: CountTable;
  batters: Record<string, { long: CountTable; recent: CountTable }>;
}>;
