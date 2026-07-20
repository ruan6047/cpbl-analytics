// 守備呈現的純邏輯（UX-PLAYER-FIELDVIZ1）：守位分群、每 9 局率、合格判定、球場座標。
// 設計依據 docs/design/UX-PLAYER-FIELDVIZ1-BRIEF.md v2；率值與門檻的理由見
// docs/research/UX-PLAYER-FIELDVIZ1_RESEARCH.md §8。元件不重複這些判斷。

/** 守位分群——每群的守備價值訊號不同，呈現內容也不同。 */
export type PosGroup = "outfield" | "infield" | "first" | "catcher" | "pitcher" | "other";

const GROUP: Record<string, PosGroup> = {
  左外野手: "outfield", 中外野手: "outfield", 右外野手: "outfield",
  二壘手: "infield", 三壘手: "infield", 游擊手: "infield",
  一壘手: "first", 捕手: "catcher", 投手: "pitcher",
};

export const posGroup = (pos: string): PosGroup => GROUP[pos] ?? "other";

/**
 * 每 9 局率（每 9 局 = 每 27 個出局）。outs 為 null（2018 前無局數）或 0 時回 null——
 * 不以出賽數代替分母：實測同守位每場守備局數離散 3.8–8.7，代守型球員會被灌水逾兩倍。
 */
export function per9(count: number | null | undefined, outs: number | null | undefined): number | null {
  if (count == null || outs == null || outs <= 0) return null;
  return (count * 27) / outs;
}

/** 局數（outs / 3），無局數資料時回 null。 */
export const innings = (outs: number | null | undefined): number | null =>
  outs == null ? null : outs / 3;

/** 是否達聯盟對照門檻。未達者仍顯示數值，但不給對照並標示樣本不足。 */
export const isQualified = (outs: number | null | undefined, qualifyOuts: number): boolean =>
  outs != null && outs >= qualifyOuts;

/** 多守位判定：有兩個以上守位真正上場過（出賽數 > 0）。 */
export function isMultiPosition(items: { pos: string; g: number | null }[]): boolean {
  return items.filter((i) => (i.g ?? 0) > 0).length > 1;
}

/** 主守位＝出賽數最多者；並列或全空時回 null（不硬選，避免誤導）。 */
export function primaryPos(items: { pos: string; g: number | null }[]): string | null {
  const played = items.filter((i) => (i.g ?? 0) > 0);
  if (played.length === 0) return null;
  const sorted = [...played].sort((a, b) => (b.g ?? 0) - (a.g ?? 0));
  if (sorted.length > 1 && (sorted[0].g ?? 0) === (sorted[1].g ?? 0)) return null;
  return sorted[0].pos;
}

/** 該守位群要呈現哪些價值指標；空陣列＝不做價值宣稱（一壘、投手）。 */
export function valueMetrics(group: PosGroup): ("a9" | "dp9" | "tc9" | "fpct")[] {
  switch (group) {
    case "outfield": return ["a9"];            // 助殺＝官方計數中少數的阻嚇型價值訊號
    case "infield": return ["dp9", "tc9", "fpct"];
    case "catcher": return ["fpct"];           // CS%／RA9 由既有 SabrSection 呈現，此處不重複
    default: return [];                        // 一壘：守備價值難量化；投手：樣本不足
  }
}

/** 球場示意圖座標（沿用 spray-chart 的極座標慣例：deg 0=中外野、負=左半場；dist 公尺）。 */
export const POS_COORD: Record<string, { deg: number; dist: number }> = {
  捕手: { deg: 0, dist: 3 },
  投手: { deg: 0, dist: 18 },
  一壘手: { deg: 38, dist: 27 },
  二壘手: { deg: 20, dist: 38 },
  游擊手: { deg: -20, dist: 38 },
  三壘手: { deg: -38, dist: 27 },
  左外野手: { deg: -30, dist: 78 },
  中外野手: { deg: 0, dist: 88 },
  右外野手: { deg: 30, dist: 78 },
};

/**
 * 身分圖與價值卡要用哪些列（REVIEW-005 P0 的修正點）。
 *
 * 二軍鏡頭（kind_code='D'）一律不得使用本季守備列——需求方明訂「二軍不算」，
 * 且 `fielding_innings` 只建一軍（實查全表 kind_code='A'），二軍列必然無局數，
 * 率值無從計算。二軍鏡頭下改以一軍生涯列做身分描述，且不給價值卡（`value` 為 null）。
 */
export function vizRows<T>(
  seasonRows: T[], careerRows: T[], isFarmView: boolean,
): { map: T[]; usesSeason: boolean } {
  const usable = isFarmView ? [] : seasonRows;
  return usable.length > 0 ? { map: usable, usesSeason: true } : { map: careerRows, usesSeason: false };
}

/** 身分圖上該守位要顯示的量：有局數用局數，否則退回出賽數（2018 前）。 */
export function posLabel(outs: number | null | undefined, g: number | null | undefined): string {
  const ip = innings(outs);
  if (ip != null) return `${ip.toFixed(0)} 局`;
  return g != null ? `${g} 場` : "—";
}
